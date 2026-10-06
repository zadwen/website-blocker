"""Portable rule backups: no PIN, device paths, or browser recovery data."""
import json
from . import rules, config


def export_rules(cfg):
    return json.dumps({'format': 'website-blocker-rules', 'version': 1,
                       'rules': cfg['rules']}, indent=2, ensure_ascii=False)


def import_rules(text, existing):
    if len(text.encode('utf-8')) > 2_000_000:
        raise ValueError('Import is too large (maximum 2 MB).')
    if text.lstrip().startswith(('{', '[')):
        data = json.loads(text)
        if not isinstance(data, dict) or data.get('format') != 'website-blocker-rules' or data.get('version') != 1:
            raise ValueError('Not a Website Blocker rule backup.')
        if not isinstance(data.get('rules'), list):
            raise ValueError('Backup rules must be a list.')
        incoming = []
        for rule in data['rules']:
            rules.validate_rule(rule)
            extra = {key: rule[key] for key in ('duration', 'start', 'end', 'days', 'enabled', 'include_related') if key in rule}
            incoming.append(rules.make_rule(rule['domain'], rule['mode'], **extra))
    else:
        incoming = [rules.make_rule(d, 'forever') for d in rules.parse_domain_list(text)]
    domains = {r['domain'] for r in existing}
    result = list(existing)
    for rule in incoming:
        if rule['domain'] not in domains:
            result.append(rule)
            domains.add(rule['domain'])
    config.validate_config({'rules': result})
    return result
