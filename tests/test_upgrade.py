import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from core import config, policies, rules, transfer, hosts, daemon


class FakeRegistry:
    def __init__(self):
        self.data = {}
        self.writes = 0

    def values(self, path):
        return dict(self.data.get(path, {}))

    def set(self, path, name, value):
        self.data.setdefault(path, {})[name] = value
        self.writes += 1

    def delete(self, path, name):
        self.data.setdefault(path, {}).pop(name, None)
        self.writes += 1


class DomainTests(unittest.TestCase):
    def test_idn_and_wildcard(self):
        self.assertEqual(rules.normalize_domain('*.Example.com'), 'example.com')
        self.assertEqual(rules.normalize_domain('https://bücher.de/page'), 'xn--bcher-kva.de')
        self.assertEqual(rules.normalize_domain('пример.рф'), 'xn--e1afmkfd.xn--p1ai')

    def test_bad_input(self):
        for value in ('127.0.0.1', 'https://[::1]', '*', 'a.*.com', 'example.com:bad',
                      'ftp://example.com', 'x.com\n0.0.0.0 good.com', None, [], 'https://-bad.com'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rules.normalize_domain(value)

    def test_domain_boundaries(self):
        self.assertTrue(rules.matches_domain('a.b.example.com', 'example.com'))
        self.assertFalse(rules.matches_domain('notexample.com', 'example.com'))
        self.assertFalse(rules.matches_domain('example.com.evil.net', 'example.com'))

    def test_related_roots_optional(self):
        self.assertIn('googlevideo.com', rules.domain_roots(rules.make_rule('youtube.com', 'forever')))
        r = rules.make_rule('youtube.com', 'forever', include_related=False)
        self.assertEqual(rules.domain_roots(r), {'youtube.com'})
        self.assertNotIn('google.com', rules.hostnames_for('youtube.com'))
        self.assertIn('x.com', rules.domain_roots(rules.make_rule('twitter.com', 'forever')))

    def test_pause_and_expiry(self):
        r = rules.make_rule('example.com', 'timer', duration=60)
        cfg = {'rules': [r]}
        self.assertEqual(policies.active_roots(cfg, {r['id']: 60}), [])
        r['enabled'] = False
        self.assertFalse(rules.is_active(r))
        self.assertEqual(daemon.compute_hostnames(cfg, {}), set())
        self.assertEqual(rules.status_text(r), 'Paused')

    def test_validation(self):
        for duration in (float('nan'), float('inf'), -1, 0, 31536001, '60', True):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                rules.make_rule('example.com', 'timer', duration=duration)
        with self.assertRaises(ValueError):
            rules.make_rule('example.com', 'schedule', start='22:00', end='07:00', days=[7])

    def test_hosts_injection(self):
        with self.assertRaises(ValueError):
            hosts.build_block(['example.com\n127.0.0.1 other.com'])


class TransferTests(unittest.TestCase):
    def test_text_hosts_import_and_duplicates(self):
        existing = [rules.make_rule('example.com', 'timer', duration=30)]
        result = transfer.import_rules('# comment\n0.0.0.0 example.com www.youtube.com\nreddit.com,reddit.com', existing)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], existing[0])

    def test_atomic_rejection(self):
        original = [rules.make_rule('example.com', 'forever')]
        before = copy.deepcopy(original)
        with self.assertRaises(ValueError):
            transfer.import_rules('youtube.com\nnot-a-domain', original)
        self.assertEqual(before, original)

    def test_roundtrip_new_ids_no_pin(self):
        rule = rules.make_rule('example.com', 'schedule', start='22:00', end='07:00', days=[0, 3])
        text = transfer.export_rules({'rules': [rule], 'pin': {'hash': 'secret'}})
        self.assertNotIn('secret', text)
        result = transfer.import_rules(text, [])
        self.assertNotEqual(result[0]['id'], rule['id'])
        self.assertEqual(result[0]['days'], [0, 3])

    def test_unsupported_format(self):
        for text in ('[]', '{"rules": []}', '{"format":"website-blocker-rules","version":2,"rules":[]}'):
            with self.assertRaises(ValueError):
                transfer.import_rules(text, [])


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.dict(os.environ, {'WB_DATA_DIR': self.temp.name})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.registry = FakeRegistry()
        self.path = os.path.join(self.temp.name, 'journal.json')
        self.manager = policies.PolicyManager(self.registry, self.path)

    def test_patterns(self):
        cfg = {'rules': [rules.make_rule('example.com', 'forever')], 'disable_doh': False}
        lists, scalar = policies.desired_policies(cfg, {})
        self.assertEqual(lists[policies.CHROMIUM[0] + r'\URLBlocklist'], ['example.com'])
        self.assertEqual(lists[policies.FIREFOX + r'\WebsiteFilter\Block'], ['*://*.example.com/*'])
        self.assertEqual(scalar, {})

    def test_preserve_existing_list_and_restore_scalar(self):
        self.registry.set('list', '1', ('corporate.example', 1))
        self.registry.set('browser', 'Dns', ('automatic', 1))
        self.manager.reconcile({'list': ['example.com']}, {('browser', 'Dns'): ('off', 1)})
        self.assertEqual(self.registry.values('list')['1'], ('corporate.example', 1))
        self.assertEqual(self.registry.values('list')['2'], ('example.com', 1))
        self.manager.restore()
        self.assertEqual(self.registry.values('list'), {'1': ('corporate.example', 1)})
        self.assertEqual(self.registry.values('browser')['Dns'], ('automatic', 1))

    def test_idempotent_and_repair(self):
        self.manager.reconcile({'list': ['a.com', 'b.com']}, {})
        count = self.registry.writes
        self.manager.reconcile({'list': ['a.com', 'b.com']}, {})
        self.assertEqual(count, self.registry.writes)
        self.registry.delete('list', '1')
        self.manager.reconcile({'list': ['a.com', 'b.com']}, {})
        self.assertEqual(self.registry.values('list')['1'], ('a.com', 1))
        self.manager.reconcile({'list': ['b.com']}, {})
        self.assertEqual(self.registry.values('list'), {'1': ('b.com', 1)})

    def test_external_changes_survive_restore(self):
        self.manager.reconcile({}, {('browser', 'Dns'): ('off', 1)})
        self.registry.set('browser', 'Dns', ('secure', 1))
        self.manager.restore()
        self.assertEqual(self.registry.values('browser')['Dns'], ('secure', 1))

    def test_recover_after_restart(self):
        self.manager.reconcile({'list': ['example.com']}, {})
        policies.PolicyManager(self.registry, self.path).restore()
        self.assertEqual(self.registry.values('list'), {})

    def test_journal_precedes_registry_mutation(self):
        def fail(*args):
            raise OSError('write failed')
        self.registry.set = fail
        with self.assertRaises(OSError):
            self.manager.reconcile({'list': ['example.com']}, {})
        with open(self.path) as f:
            saved = json.load(f)
        self.assertEqual(saved['values']['list|1']['applied']['value'], 'example.com')
        policies.PolicyManager(self.registry, self.path).restore()

    def test_limits_reject_before_write(self):
        self.registry.set('list', '1', ('corporate.example', 1))
        before = copy.deepcopy(self.registry.data)
        with self.assertRaises(ValueError):
            self.manager.reconcile({'list': [f's{i}.example' for i in range(1000)]}, {})
        self.assertEqual(before, self.registry.data)

    def test_preexisting_identical_not_owned(self):
        self.registry.set('list', '1', ('example.com', 1))
        self.manager.reconcile({'list': ['example.com']}, {})
        self.manager.restore()
        self.assertEqual(self.registry.values('list')['1'], ('example.com', 1))

    def test_corrupt_backup_not_overwritten(self):
        with open(self.path, 'w') as f:
            f.write('{broken')
        with self.assertRaises(ValueError):
            policies.PolicyManager(self.registry, self.path)


if __name__ == '__main__':
    unittest.main()
