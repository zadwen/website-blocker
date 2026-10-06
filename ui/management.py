"""Management controls kept separate from the main window."""
import json
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from core import config, rules, policies, transfer
from core.catalog import PRESETS
from core.branding import COLORS as C
from ui.widgets import card, label, button, entry


class ManagementMixin:
    def build_tools(self, tab):
        c = card(tab, 'Block groups & import lists')
        c.pack(fill='x', pady=12)
        label(c, 'Presets add permanent rules. Existing rules are kept. Timers in imported backups restart.',
              muted=True).pack(anchor='w', padx=18)
        row = tk.Frame(c, bg=C['panel'])
        row.pack(fill='x', padx=18, pady=12)
        for name, domains in PRESETS.items():
            button(row, name, lambda d=domains: self.import_text('\n'.join(d)), 'ghost').pack(side='left', padx=(0, 8))
        self.bulk = tk.Text(c, height=5, bg=C['panel2'], fg=C['text'], insertbackground=C['text'],
                            relief='flat', font=('Consolas', 11), undo=True)
        self.bulk.pack(fill='x', padx=18)
        label(c, 'Paste domains, URLs or hosts-file entries. Invalid input is rejected before saving.',
              muted=True, size=9).pack(anchor='w', padx=18, pady=6)
        row = tk.Frame(c, bg=C['panel'])
        row.pack(fill='x', padx=18, pady=(0, 14))
        button(row, 'Add pasted list', lambda: self.import_text(self.bulk.get('1.0', 'end'))).pack(side='left')
        button(row, 'Import file', self.import_file, 'ghost').pack(side='left', padx=8)
        button(row, 'Export rules', self.export_file, 'ghost').pack(side='left')

        c = card(tab, 'Coverage checker')
        c.pack(fill='x', pady=(0, 12))
        row = tk.Frame(c, bg=C['panel'])
        row.pack(fill='x', padx=18)
        self.check_var = tk.StringVar()
        entry(row, self.check_var, width=45).pack(side='left', ipady=6)
        button(row, 'Check domain', self.check_domain, 'ghost').pack(side='left', padx=10)
        self.coverage_label = label(c, 'Checks configured rules, not live network connectivity.',
                                    muted=True, justify='left', wraplength=870)
        self.coverage_label.pack(anchor='w', padx=18, pady=14)

        c = card(tab, 'Diagnostics')
        c.pack(fill='both', expand=True)
        row = tk.Frame(c, bg=C['panel'])
        row.pack(fill='x', padx=18, pady=(0, 10))
        button(row, 'View service health', self.show_health, 'ghost').pack(side='left')
        button(row, 'View recent errors', self.show_log, 'ghost').pack(side='left', padx=8)
        label(c, 'After policy changes, restart the browser. Check chrome://policy, edge://policy or about:policies.\n'
                 'Browser rules cover subdomains; hosts rules cover only the listed names. VPNs and unsupported apps may bypass hosts.',
              muted=True, size=9, justify='left', wraplength=870).pack(anchor='w', padx=18, pady=(0, 12))

    def import_text(self, text):
        try:
            result = transfer.import_rules(text, self.cfg['rules'])
            count = len(result) - len(self.cfg['rules'])
            if not count:
                return messagebox.showinfo('Import', 'No new domains to add.')
            if not messagebox.askyesno('Import rules', f'Add {count} rules? Existing rules will be kept.'):
                return
            self.cfg['rules'] = result
            if self._save():
                self.refresh_rules()
                messagebox.showinfo('Import', f'Added {count} rules. Restart browsers to refresh policies.')
        except (ValueError, TypeError, KeyError) as exc:
            messagebox.showerror('Import failed', str(exc))

    def import_file(self):
        path = filedialog.askopenfilename(filetypes=[('Blocklists', '*.json *.txt *.hosts'), ('All files', '*.*')])
        if path:
            try:
                if os.path.getsize(path) > 2_000_000:
                    raise ValueError('Import is too large (maximum 2 MB).')
                with open(path, encoding='utf-8-sig') as f:
                    self.import_text(f.read())
            except (OSError, ValueError) as exc:
                messagebox.showerror('Import failed', str(exc))

    def export_file(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='website-blocker-rules.json',
                                          filetypes=[('Rule backup', '*.json')])
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(transfer.export_rules(self.cfg))
                messagebox.showinfo('Export', 'Rules exported. Your PIN and device settings are not included.')
            except OSError as exc:
                messagebox.showerror('Export failed', str(exc))

    def check_domain(self):
        from core.daemon import compute_hostnames
        try:
            host = rules.normalize_domain(self.check_var.get())
            used = config.load_state()['used']
            roots = policies.active_roots(self.cfg, used)
            matches = [root for root in roots if rules.matches_domain(host, root)]
            # normalize_domain treats www as the same website; use the literal hostname for hosts coverage.
            from urllib.parse import urlsplit
            raw = self.check_var.get().strip()
            literal = (urlsplit(raw if '://' in raw else '//' + raw).hostname or host).rstrip('.').lower().encode('idna').decode()
            exact = literal in compute_hostnames(self.cfg, used)
            browser = bool(matches and self.cfg.get('browser_blocking', True))
            self.coverage_label.configure(text=(f'{literal}\nBrowser domain rule: {"covered" if browser else "not covered"}  ·  '
                f'Hosts entry: {"covered" if exact else "not covered"}\n' +
                ('Matched: ' + ', '.join(matches) if matches else 'No active domain rule matches.') +
                '\nConfigured coverage only. Confirm service health and browser policy loading.'))
        except ValueError as exc:
            self.coverage_label.configure(text=str(exc))

    def edit_rule(self):
        rule = self._selected_rule()
        if not rule:
            return
        self.site_var.set(rule['domain'])
        self.mode_var.set(rule['mode'])
        self.related_var.set(rule.get('include_related', True))
        if rule['mode'] == 'timer':
            self.amount_var.set(str(rule['duration'] / 60))
            self.unit_var.set('Minutes')
        elif rule['mode'] == 'schedule':
            self.start_var.set(rule['start'])
            self.end_var.set(rule['end'])
            for i, variable in enumerate(self.day_vars):
                variable.set(i in rule['days'])
        self._mode_changed()
        self._say('Edit on the left, then Block website to replace. Timers restart.')

    def toggle_rule(self):
        rule = self._selected_rule()
        if rule:
            rule['enabled'] = not rule.get('enabled', True)
            if self._save():
                self.refresh_rules()

    def coverage_details(self):
        rule = self._selected_rule()
        if rule:
            self.show_text('Domain coverage — ' + rule['domain'],
                'BROWSER DOMAIN ROOTS (each includes all subdomains)\n' +
                '\n'.join(sorted(rules.domain_roots(rule))) +
                '\n\nEXACT HOSTS ENTRIES\n' + '\n'.join(rules.hostnames_for(rule['domain'], rule.get('include_related', True))) +
                '\n\nRelated domains are an offline curated list, not automatic discovery.\n'
                'Shared service features may also be affected. Browser blocking must be enabled.')

    def show_text(self, title, text):
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry('760x480')
        box = tk.Text(window, wrap='word', bg=C['panel'], fg=C['text'], padx=18, pady=18)
        box.pack(fill='both', expand=True)
        box.insert('1.0', text)
        box.configure(state='disabled')

    def show_health(self):
        try:
            health = config.read_json(os.path.join(config.data_dir(), 'health.json'), {})
            age = time.time() - health.get('updated', 0)
            text = ('No recent service heartbeat. Install or repair protection.\n' if age > 20 else '')
            text += json.dumps(health, indent=2)
            text += '\n\nThis reports successful system writes, not confirmation that browsers loaded policies.\n'
            text += 'Browser policy errors or existing allowlists can affect enforcement. See README troubleshooting.'
            self.show_text('Service health', text)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Diagnostics', str(exc))

    def show_log(self):
        try:
            with open(config.log_path(), encoding='utf-8') as f:
                self.show_text('Recent service log', f.read()[-30000:] or 'No entries.')
        except FileNotFoundError:
            messagebox.showinfo('Service log', 'No service log yet.')
        except OSError as exc:
            messagebox.showerror('Service log', str(exc))
