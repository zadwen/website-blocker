"""Regression checks use temporary paths and mocked system integrations."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from core import config, daemon, hosts, rules
from macos.backend import Backend
from macos.service import validate


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'WB_DATA_DIR': str(self.root)})
        env.start()
        self.addCleanup(env.stop)

    def test_hosts_writer_rejects_url_syntax_and_noncanonical_names(self):
        for name in ('example.com#comment', 'example.com?x', 'user@example.com',
                     '*.example.com', 'example.com.', 'Example.com', 'bücher.de',
                     'example.com/path', 'example.com\x00'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                hosts.build_block([name])
        block = hosts.build_block(['www.example.com', 'xn--bcher-kva.de'])
        self.assertIn('0.0.0.0 www.example.com', block)
        self.assertIn(':: xn--bcher-kva.de', block)

    def test_invalid_config_objects_raise_validation_errors(self):
        for value in (None, [], 'settings', {'version': True, 'rules': []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                config.validate_config(value)

    def run_one_tick(self):
        with patch.object(daemon, '_acquire_single_instance', return_value=True), \
             patch.object(daemon, '_setup_logging', return_value=Mock()), \
             patch.object(daemon.hosts, 'apply') as apply_hosts, \
             patch.object(daemon.policies, 'apply'), \
             patch.object(daemon.time, 'sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                daemon.run()
        return apply_hosts

    def test_missing_settings_and_backup_leave_existing_protection_untouched(self):
        self.run_one_tick().assert_not_called()
        health = json.loads((self.root / 'health.json').read_text())
        self.assertFalse(health['ok'])
        self.assertIn('No valid configuration', health['error'])

    def test_valid_backup_still_enforces_when_primary_missing(self):
        backup = copy.deepcopy(config.DEFAULT_CONFIG)
        backup['rules'] = [rules.make_rule('example.com', 'forever')]
        (self.root / 'last-good-config.json').write_text(json.dumps(backup))
        call = self.run_one_tick()
        self.assertIn('example.com', call.call_args.args[0])

    @unittest.skipIf(os.name == "nt", "macOS backend requires POSIX file modes")
    def test_mac_dns_flush_retried_after_files_already_written(self):
        path = self.root / 'hosts'
        path.write_text('127.0.0.1 localhost\n')
        backend = Backend(self.root, path, self.root / 'resolver')
        for failed_command in (0, 1):
            with self.subTest(failed_command=failed_command):
                roots = {f'site{failed_command}.example'}
                outcomes = [None] * failed_command + [subprocess.CalledProcessError(1, 'flush')]
                with patch('macos.backend.subprocess.run', side_effect=outcomes):
                    with self.assertRaises(subprocess.CalledProcessError):
                        backend.apply(roots, roots)
                with patch('macos.backend.subprocess.run') as run:
                    self.assertFalse(backend.apply(roots, roots))
                    self.assertEqual(run.call_count, 2)
                    backend.apply(roots, roots)
                    self.assertEqual(run.call_count, 2)

    def test_mac_duplicate_rule_ids_rejected(self):
        first = rules.make_rule('example.com', 'forever')
        second = rules.make_rule('other.com', 'forever', id=first['id'])
        with self.assertRaisesRegex(ValueError, 'Duplicate rule ID'):
            validate({'version': 1, 'paused': False, 'rules': [first, second]})
