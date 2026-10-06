"""Browser domain policies with per-value write-ahead recovery journal.

Keep pre-existing policies; only remove values owned by Website Blocker.
The journal is written BEFORE changing the registry so interrupted writes recover.
"""
import base64
import os
from . import config, rules
from .winutil import IS_WINDOWS

CHROMIUM = (
    r'SOFTWARE\Policies\Google\Chrome',
    r'SOFTWARE\Policies\Microsoft\Edge',
    r'SOFTWARE\Policies\BraveSoftware\Brave',
    r'SOFTWARE\Policies\Vivaldi',
)
FIREFOX = r'SOFTWARE\Policies\Mozilla\Firefox'
LIMIT = 1000


def active_roots(cfg, used, now=None):
    roots = set()
    for rule in cfg['rules']:
        if rules.is_active(rule, used.get(rule['id'], 0), now):
            roots.update(rules.domain_roots(rule))
    return sorted(roots)


def desired_policies(cfg, used, now=None):
    roots = active_roots(cfg, used, now) if cfg.get('browser_blocking', True) else []
    lists = {path + r'\URLBlocklist': roots for path in CHROMIUM}
    lists[FIREFOX + r'\WebsiteFilter\Block'] = ['*://*.' + root + '/*' for root in roots]
    scalars = {}
    if cfg.get('disable_doh', True):
        for path in CHROMIUM:
            scalars[(path, 'DnsOverHttpsMode')] = ('off', 1)  # REG_SZ
        scalars[(FIREFOX + r'\DNSOverHTTPS', 'Enabled')] = (0, 4)
        scalars[(FIREFOX + r'\DNSOverHTTPS', 'Locked')] = (1, 4)
    return lists, scalars


class WindowsRegistry:
    def __init__(self):
        import winreg
        self.reg = winreg
        self.access = winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY

    def values(self, path):
        w = self.reg
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, path, 0, self.access) as key:
                result = {}
                for index in range(w.QueryInfoKey(key)[1]):
                    name, value, kind = w.EnumValue(key, index)
                    result[name] = (value, kind)
                return result
        except FileNotFoundError:
            return {}

    def set(self, path, name, record):
        w = self.reg
        with w.CreateKeyEx(w.HKEY_LOCAL_MACHINE, path, 0, self.access) as key:
            w.SetValueEx(key, name, 0, record[1], record[0])

    def delete(self, path, name):
        w = self.reg
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, path, 0, self.access) as key:
                w.DeleteValue(key, name)
        except FileNotFoundError:
            pass


def pack(record):
    if record is None:
        return None
    value, kind = record
    return {'value': base64.b64encode(value).decode('ascii') if isinstance(value, bytes) else value,
            'kind': kind, 'binary': isinstance(value, bytes)}


def unpack(record):
    if record is None:
        return None
    value = base64.b64decode(record['value']) if record.get('binary') else record['value']
    return value, record['kind']


class PolicyManager:
    def __init__(self, registry=None, journal_path=None):
        self.registry = registry or WindowsRegistry()
        self.path = journal_path or os.path.join(config.data_dir(), 'policy-backup.json')
        self.journal = config.read_json(self.path, {'version': 1, 'values': {}})
        if self.journal.get('version') != 1 or not isinstance(self.journal.get('values'), dict):
            raise ValueError('Invalid policy backup; recovery requires administrator review.')

    def save(self):
        config._atomic_write_json(self.path, self.journal)

    def put(self, path, name, record):
        identity = path + '|' + name
        current = self.registry.values(path).get(name)
        entry = self.journal['values'].get(identity)
        if entry is None:
            entry = {'path': path, 'name': name, 'original': pack(current)}
            self.journal['values'][identity] = entry
        if entry.get('applied') != pack(record):
            entry['applied'] = pack(record)
            self.save()
        if current != record:
            self.registry.set(path, name, record)

    def release(self, identity):
        entry = self.journal['values'][identity]
        path, name = entry['path'], entry['name']
        # Preserve values another administrator changed after our last write.
        if self.registry.values(path).get(name) == unpack(entry['applied']):
            original = unpack(entry['original'])
            if original is None:
                self.registry.delete(path, name)
            else:
                self.registry.set(path, name, original)
        del self.journal['values'][identity]
        self.save()

    def reconcile(self, lists, scalars):
        wanted = dict(scalars)
        owned = self.journal['values']
        # Plan all list slots and check browser limits before any registry change.
        for path, patterns in lists.items():
            existing = self.registry.values(path)
            external = {k: v for k, v in existing.items() if path + '|' + k not in owned}
            external_values = {v[0] for v in external.values() if v[1] == 1}
            additions = [v for v in dict.fromkeys(patterns) if v not in external_values]
            if len(external) + len(additions) > LIMIT:
                raise ValueError('Browser policy limit exceeded: reduce domain rules or existing policies.')
            slots = (str(i) for i in range(1, LIMIT + 1) if str(i) not in external)
            for value in additions:
                wanted[(path, next(slots))] = (value, 1)
        wanted_ids = {p + '|' + n for p, n in wanted}
        for (path, name), record in wanted.items():
            self.put(path, name, record)
        for identity in list(owned):
            if identity not in wanted_ids:
                self.release(identity)

    def restore(self):
        for identity in list(self.journal['values']):
            self.release(identity)


def apply(cfg, used):
    if IS_WINDOWS:
        PolicyManager().reconcile(*desired_policies(cfg, used))


def restore():
    if IS_WINDOWS:
        PolicyManager().restore()
