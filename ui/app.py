import sys
import os
import time
import copy
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from core import branding as B
from core import config, install, rules
from core.branding import COLORS as C
from core.winutil import IS_WINDOWS
from ui.dialogs import AddTimeDialog, PinDialog
from ui.management import ManagementMixin
from ui.widgets import Header, button, card, chip, entry, label

QUICK_SITES = ["youtube.com", "tiktok.com", "instagram.com", "snapchat.com", "facebook.com",
               "x.com", "discord.com", "twitch.tv", "roblox.com", "reddit.com", "netflix.com"]
UNITS = {"Minutes": 60, "Hours": 3600, "Days": 86400}
MAX_PIN_TRIES = 5


class App(ManagementMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title("%s  ·  by %s" % (B.APP_NAME, B.AUTHOR))
        self.configure(bg=C["bg"])
        self.geometry("1160x820")
        self.minsize(1100, 780)
        self.cfg = None
        self.first_run = False
        self._icon_ref = None
        self._ticks = 0
        self._installed = False
        self._saved_cfg = None
        self._style()
        self._icon()

    # ---------------------------------------------------------------- setup
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview", background=C["panel"], fieldbackground=C["panel"],
                    foreground=C["text"], rowheight=34, borderwidth=0, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", background=C["panel2"], foreground=C["muted"],
                    relief="flat", font=("Segoe UI", 9, "bold"), padding=8)
        s.map("Treeview", background=[("selected", C["accent"])],
              foreground=[("selected", "white")])
        s.map("Treeview.Heading", background=[("active", C["panel2"])])
        for k in ("bordercolor", "lightcolor", "darkcolor"):
            s.configure("TNotebook", **{k: C["line"]})
            s.configure("Treeview", **{k: C["panel"]})
        s.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
        s.configure("TNotebook.Tab", background=C["bg"], foreground=C["muted"],
                    padding=(22, 10), font=("Segoe UI", 10, "bold"), borderwidth=0)
        s.map("TNotebook.Tab", background=[("selected", C["panel"])],
              foreground=[("selected", C["text"])])
        s.configure("TCombobox", fieldbackground=C["panel2"], background=C["panel2"],
                    foreground=C["text"], arrowcolor=C["text"], borderwidth=0)
        s.map("TCombobox", fieldbackground=[("readonly", C["panel2"])],
              foreground=[("readonly", C["text"])])
        s.configure("Vertical.TScrollbar", background=C["panel2"], troughcolor=C["panel"],
                    borderwidth=0, arrowcolor=C["muted"])
        self.option_add("*TCombobox*Listbox.background", C["panel2"])
        self.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["accent"])

    def _icon(self):
        try:
            from PIL import ImageTk
            from ui.icon import make_image
            self._icon_ref = ImageTk.PhotoImage(make_image(64))
            self.iconphoto(True, self._icon_ref)
        except Exception:
            pass

    # ----------------------------------------------------------------- auth
    def authenticate(self):
        try:
            self.cfg = config.load_config()
        except Exception as e:
            messagebox.showerror(B.APP_NAME, "The settings file is damaged:\n%s" % e)
            return False

        if not self.cfg.get("pin"):
            pin = PinDialog(self, "Create a parent PIN",
                            "This PIN protects the app. Only you should know it.",
                            confirm=True).show()
            if not pin:
                return False
            self.cfg["pin"] = config.make_pin_record(pin)
            config.save_config(self.cfg)
            self.first_run = True
            return True

        err = ""
        for attempt in range(MAX_PIN_TRIES):
            pin = PinDialog(self, "Parent PIN", "Enter your PIN to open Website Blocker.",
                            error=err).show()
            if pin is None:
                return False
            if config.check_pin(self.cfg, pin):
                return True
            err = "Wrong PIN  (%d tries left)" % (MAX_PIN_TRIES - attempt - 1)
        return False

    # ------------------------------------------------------------------- UI
    def build(self):
        self._saved_cfg = copy.deepcopy(self.cfg)
        Header(self, B.APP_NAME, B.TAGLINE, "v" + B.VERSION).pack(fill="x")
        self._build_status()
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=18, pady=(8, 18))
        tab1 = tk.Frame(nb, bg=C["bg"])
        tab2 = tk.Frame(nb, bg=C["bg"])
        nb.add(tab1, text="  Blocked websites  ")
        tab3 = tk.Frame(nb, bg=C["bg"])
        nb.add(tab3, text="  Lists & diagnostics  ")
        nb.add(tab2, text="  Settings  ")
        self.build_tools(tab3)
        self._build_sites_tab(tab1)
        self._build_settings_tab(tab2)
        self.refresh_all()
        self.after(2000, self._tick)
        if self.first_run:
            self.after(400, self.install_protection)

    def _build_status(self):
        bar = tk.Frame(self, bg=C["panel"], highlightthickness=1, highlightbackground=C["line"])
        bar.pack(fill="x", padx=18, pady=(14, 0))
        self.dot = tk.Canvas(bar, width=14, height=14, bg=C["panel"], highlightthickness=0)
        self.dot.pack(side="left", padx=(16, 8), pady=14)
        self.dot_item = self.dot.create_oval(2, 2, 12, 12, fill=C["muted"], outline="")
        self.status_lbl = label(bar, "Checking…", size=10, bold=True)
        self.status_lbl.pack(side="left")
        self.status_sub = label(bar, "", muted=True, size=9)
        self.status_sub.pack(side="left", padx=(10, 0))
        self.fix_btn = button(bar, "Install protection", self.install_protection, pad=(14, 6))
        self.fix_btn.pack(side="right", padx=14, pady=8)

    def _build_sites_tab(self, tab):
        tab.columnconfigure(0, weight=0)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        # ---- left: add a block
        left = card(tab, "Block a website")
        left.grid(row=0, column=0, sticky="ns", padx=(0, 12), pady=12)
        pad = {"padx": 18}
        label(left, "Website address", muted=True, size=9).pack(anchor="w", **pad)
        self.site_var = tk.StringVar()
        e = entry(left, self.site_var, width=30, font_size=12)
        e.pack(fill="x", ipady=6, pady=(3, 8), **pad)
        e.bind("<Return>", lambda ev: self.add_block())

        grid = tk.Frame(left, bg=C["panel"])
        grid.pack(fill="x", pady=(0, 10), **pad)
        for i, site in enumerate(QUICK_SITES):
            chip(grid, site.split(".")[0], lambda s=site: self.site_var.set(s)).grid(
                row=i // 4, column=i % 4, padx=(0, 5), pady=3, sticky="w")

        label(left, "For how long?", muted=True, size=9).pack(anchor="w", pady=(4, 2), **pad)
        self.mode_var = tk.StringVar(value="forever")
        for val, text in (("forever", "Forever"), ("timer", "For a set time"),
                          ("schedule", "On a daily schedule")):
            tk.Radiobutton(left, text=text, value=val, variable=self.mode_var,
                           command=self._mode_changed, bg=C["panel"], fg=C["text"],
                           selectcolor=C["panel2"], activebackground=C["panel"],
                           activeforeground=C["text"], font=("Segoe UI", 10),
                           highlightthickness=0, bd=0).pack(anchor="w", **pad)

        self.opts = tk.Frame(left, bg=C["panel"])
        self.opts.pack(fill="x", pady=(8, 0), **pad)

        self.timer_row = tk.Frame(self.opts, bg=C["panel"])
        self.amount_var = tk.StringVar(value="2")
        self.unit_var = tk.StringVar(value="Hours")
        entry(self.timer_row, self.amount_var, width=6, font_size=11).pack(side="left", ipady=4)
        ttk.Combobox(self.timer_row, textvariable=self.unit_var, values=list(UNITS),
                     state="readonly", width=9, font=("Segoe UI", 10)).pack(side="left", padx=8)

        self.sched_row = tk.Frame(self.opts, bg=C["panel"])
        t = tk.Frame(self.sched_row, bg=C["panel"])
        t.pack(anchor="w")
        self.start_var, self.end_var = tk.StringVar(value="22:00"), tk.StringVar(value="07:00")
        label(t, "From", muted=True, size=9).pack(side="left")
        entry(t, self.start_var, width=6, font_size=11).pack(side="left", padx=6, ipady=4)
        label(t, "to", muted=True, size=9).pack(side="left")
        entry(t, self.end_var, width=6, font_size=11).pack(side="left", padx=6, ipady=4)
        d = tk.Frame(self.sched_row, bg=C["panel"])
        d.pack(anchor="w", pady=(8, 0))
        self.day_vars = []
        for i, name in enumerate(rules.DAY_NAMES):
            v = tk.BooleanVar(value=True)
            self.day_vars.append(v)
            tk.Checkbutton(d, text=name, variable=v, bg=C["panel"], fg=C["text"],
                           selectcolor=C["panel2"], activebackground=C["panel"],
                           activeforeground=C["text"], font=("Segoe UI", 9),
                           highlightthickness=0, bd=0).grid(row=0, column=i, padx=(0, 2))

        self.related_var = tk.BooleanVar(value=True)
        tk.Checkbutton(left, text="Include related service domains", variable=self.related_var,
                       bg=C["panel"], fg=C["text"], selectcolor=C["panel2"],
                       activebackground=C["panel"], activeforeground=C["text"]).pack(anchor="w", pady=(12, 0), **pad)
        label(left, "Browser rules include all subdomains.\nURLs block the whole domain, not a page.",
              muted=True, size=9, justify="left").pack(anchor="w", **pad)
        button(left, "Block website", self.add_block).pack(fill="x", pady=(18, 6), **pad)
        self.toast = label(left, "", size=9)
        self.toast.pack(anchor="w", pady=(0, 16), **pad)
        self._mode_changed()

        # ---- right: list
        right = card(tab, "Blocked websites")
        right.grid(row=0, column=1, sticky="nsew", pady=12)
        self.search_var = tk.StringVar()
        search = entry(right, self.search_var, font_size=10)
        search.pack(fill="x", padx=18, pady=(0, 8))
        label(right, "Filter by domain", muted=True, size=9).pack(anchor="w", padx=18)
        self.search_var.trace_add("write", lambda *_: self.refresh_rules())
        self.stats_label = label(right, "", muted=True, size=9)
        self.stats_label.pack(anchor="w", padx=18, pady=(0, 8))
        wrap = tk.Frame(right, bg=C["panel"])
        wrap.pack(fill="both", expand=True, padx=18)
        cols = ("site", "rule", "status")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for c, text, w in (("site", "Website", 190), ("rule", "Rule", 210), ("status", "Status", 120)):
            self.tree.heading(c, text=text, anchor="w")
            self.tree.column(c, width=w, minwidth=90, anchor="w", stretch=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda event: self.edit_rule())
        self.tree.tag_configure("on", foreground=C["danger"])
        self.tree.tag_configure("off", foreground=C["muted"])
        self.empty_lbl = label(right, "Nothing blocked yet.\nAdd a website on the left.",
                               muted=True, size=10, justify="center")
        btns = tk.Frame(right, bg=C["panel"])
        btns.pack(fill="x", padx=18, pady=14)
        button(btns, "＋ Add time", self.add_time, "ghost").pack(side="left")
        button(btns, "Pause / resume", self.toggle_rule, "ghost").pack(side="left", padx=6)
        button(btns, "Coverage", self.coverage_details, "ghost").pack(side="left")
        button(btns, "Unblock", self.remove_block, "danger").pack(side="left", padx=8)

    def _build_settings_tab(self, tab):
        tab.columnconfigure(0, weight=1)
        pad = {"padx": 18}

        c1 = card(tab, "Parent PIN")
        c1.grid(row=0, column=0, sticky="ew", pady=(12, 0))
        label(c1, "The PIN is needed every time the app opens.", muted=True).pack(anchor="w", **pad)
        button(c1, "Change PIN", self.change_pin, "ghost").pack(anchor="w", pady=14, **pad)

        c2 = card(tab, "Browser protection")
        c2.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.browser_var = tk.BooleanVar(value=bool(self.cfg.get("browser_blocking", True)))
        tk.Checkbutton(c2, text="Block websites and ALL subdomains using browser policies",
                       variable=self.browser_var, command=self._browser_toggled, bg=C["panel"],
                       fg=C["text"], selectcolor=C["panel2"], activebackground=C["panel"],
                       activeforeground=C["text"]).pack(anchor="w", **pad)
        self.doh_var = tk.BooleanVar(value=bool(self.cfg.get("disable_doh", True)))
        tk.Checkbutton(c2, text="Disable Secure DNS in supported browsers (additional protection)",
                       variable=self.doh_var, command=self._doh_toggled, bg=C["panel"],
                       fg=C["text"], selectcolor=C["panel2"], activebackground=C["panel"],
                       activeforeground=C["text"], font=("Segoe UI", 10),
                       highlightthickness=0, bd=0).pack(anchor="w", **pad)
        label(c2, "Chrome, Edge, Brave, Vivaldi and Firefox will show “managed by your organization”.",
              muted=True, size=9).pack(anchor="w", pady=(2, 14), **pad)

        c3 = card(tab, "Background service")
        c3.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        label(c3, "Closing this window does NOT stop the blocking. The service runs silently from "
                  "Windows startup, on any Wi-Fi.", muted=True, wraplength=820,
              justify="left").pack(anchor="w", **pad)
        row = tk.Frame(c3, bg=C["panel"])
        row.pack(anchor="w", pady=14, **pad)
        button(row, "Repair / reinstall", self.install_protection, "ghost").pack(side="left")
        button(row, "Uninstall completely", self.uninstall, "danger").pack(side="left", padx=8)

        c4 = card(tab, "About")
        c4.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        label(c4, "%s v%s  ·  MIT licensed  ·  made by %s" % (B.APP_NAME, B.VERSION, B.AUTHOR),
              muted=True).pack(anchor="w", **pad)
        link = label(c4, B.REPO_URL, size=10)
        link.configure(fg=C["accent2"], cursor="hand2")
        link.pack(anchor="w", pady=(2, 14), **pad)
        link.bind("<Button-1>", lambda e: webbrowser.open(B.REPO_URL))

    # --------------------------------------------------------------- helpers
    def _mode_changed(self):
        self.timer_row.pack_forget()
        self.sched_row.pack_forget()
        mode = self.mode_var.get()
        if mode == "timer":
            self.timer_row.pack(anchor="w")
        elif mode == "schedule":
            self.sched_row.pack(anchor="w")

    def _say(self, text, ok=True):
        self.toast.configure(text=text, fg=C["ok"] if ok else C["danger"])
        self.after(5000, lambda: self.toast.configure(text=""))

    def _save(self):
        try:
            config.save_config(self.cfg)
            self._saved_cfg = copy.deepcopy(self.cfg)
            return True
        except Exception as e:
            if self._saved_cfg is not None:
                self.cfg = copy.deepcopy(self._saved_cfg)
            messagebox.showerror(B.APP_NAME, "Could not save settings:\n%s" % e)
            return False

    def _selected_rule(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(B.APP_NAME, "Select a website in the list first.")
            return None
        return next((r for r in self.cfg["rules"] if r["id"] == sel[0]), None)

    # --------------------------------------------------------------- actions
    def add_block(self):
        try:
            domain = rules.normalize_domain(self.site_var.get())
        except ValueError as e:
            return self._say(str(e), ok=False)
        mode, extra = self.mode_var.get(), {}
        if mode == "timer":
            try:
                secs = int(float(self.amount_var.get()) * UNITS[self.unit_var.get()])
                if not 0 < secs <= 31536000:
                    raise ValueError
            except (ValueError, OverflowError):
                return self._say("Enter a time from 1 second to 365 days.", ok=False)
            extra = {"duration": secs}
        elif mode == "schedule":
            try:
                rules.parse_hhmm(self.start_var.get())
                rules.parse_hhmm(self.end_var.get())
            except ValueError as e:
                return self._say(str(e), ok=False)
            days = [i for i, v in enumerate(self.day_vars) if v.get()]
            if not days:
                return self._say("Pick at least one day.", ok=False)
            extra = {"start": self.start_var.get().strip(), "end": self.end_var.get().strip(),
                     "days": days}

        extra["include_related"] = self.related_var.get()
        old = [r for r in self.cfg["rules"] if r["domain"] == domain]
        if old and not messagebox.askyesno(B.APP_NAME, "%s is already blocked. Replace the rule?" % domain):
            return
        self.cfg["rules"] = [r for r in self.cfg["rules"] if r["domain"] != domain]
        self.cfg["rules"].append(rules.make_rule(domain, mode, **extra))
        if self._save():
            self.site_var.set("")
            self.refresh_rules()
            self._say("Saved. Check service health; restart browsers.")

    def add_time(self):
        r = self._selected_rule()
        if not r:
            return
        if r["mode"] != "timer":
            return messagebox.showinfo(
                B.APP_NAME, "“Add time” is for timer blocks.\n\nForever blocks never end, and "
                            "scheduled blocks repeat daily.")
        secs = AddTimeDialog(self, r["domain"]).show()
        if not secs:
            return
        used = config.load_state()["used"].get(r["id"], 0.0)
        r["duration"] = max(float(r["duration"]), float(used)) + secs
        if self._save():
            self.refresh_rules()

    def remove_block(self):
        r = self._selected_rule()
        if not r:
            return
        if messagebox.askyesno(B.APP_NAME, "Unblock %s?" % r["domain"]):
            self.cfg["rules"] = [x for x in self.cfg["rules"] if x["id"] != r["id"]]
            if self._save():
                self.refresh_rules()

    def change_pin(self):
        cur = PinDialog(self, "Current PIN", "Enter your current PIN.").show()
        if cur is None:
            return
        if not config.check_pin(self.cfg, cur):
            return messagebox.showerror(B.APP_NAME, "That PIN is wrong.")
        new = PinDialog(self, "New PIN", "Choose a new PIN.", confirm=True).show()
        if new:
            self.cfg["pin"] = config.make_pin_record(new)
            if self._save():
                messagebox.showinfo(B.APP_NAME, "PIN changed.")

    def _browser_toggled(self):
        self.cfg["browser_blocking"] = bool(self.browser_var.get())
        if not self._save():
            self.browser_var.set(self.cfg.get("browser_blocking", True))

    def _doh_toggled(self):
        self.cfg["disable_doh"] = bool(self.doh_var.get())
        if not self._save():
            self.doh_var.set(self.cfg.get("disable_doh", True))

    def install_protection(self):
        if not IS_WINDOWS:
            return messagebox.showinfo(B.APP_NAME, "The background service only works on Windows.")
        try:
            install.install()
        except Exception as e:
            return messagebox.showerror(B.APP_NAME, "Install failed:\n%s" % e)
        self._installed = True
        self.refresh_status()
        messagebox.showinfo(
            B.APP_NAME, "Protection is on.\n\nIt now starts by itself with Windows, runs hidden in the "
                        "background and keeps working on any Wi-Fi.\nYou can close this window.")

    def uninstall(self):
        if not messagebox.askyesno(B.APP_NAME, "Remove Website Blocker completely?\n\nAll blocks will stop "
                                               "and settings will be deleted."):
            return
        try:
            install.uninstall()
        except Exception as e:
            return messagebox.showerror(B.APP_NAME, "Uninstall failed:\n%s" % e)
        messagebox.showinfo(B.APP_NAME, "Website Blocker was removed.")
        self.destroy()

    # --------------------------------------------------------------- refresh
    def refresh_rules(self):
        state = config.load_state()["used"]
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        active_count = sum(rules.is_active(r, state.get(r["id"], 0)) for r in self.cfg["rules"])
        self.stats_label.configure(text=f"{len(self.cfg['rules'])} rules  ·  {active_count} active  ·  Double-click to edit; Coverage shows domains")
        for r in self.cfg["rules"]:
            if self.search_var.get().lower() not in r["domain"]:
                continue
            used = state.get(r["id"], 0.0)
            try:
                active = rules.is_active(r, used)
                values = (r["domain"], rules.describe(r), rules.status_text(r, used))
            except Exception:
                active, values = False, (r.get("domain", "?"), "invalid rule", "")
            self.tree.insert("", "end", iid=r["id"], values=values, tags=("on" if active else "off",))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
        if self.cfg["rules"]:
            self.empty_lbl.place_forget()
        else:
            self.empty_lbl.place(relx=0.5, rely=0.42, anchor="center")

    def refresh_status(self):
        running = install.daemon_running()
        if running:
            self._installed = True
        if running:
            color, text, sub, btn = C["ok"], "Protection is ON", \
                "Running silently · starts with Windows · works on any Wi-Fi", None
        elif self._installed:
            color, text, sub, btn = C["warn"], "Installed, but not running", \
                "Click repair to start it", "Repair"
        else:
            color, text, sub, btn = C["danger"], "Protection is OFF", \
                "Blocks only work once the background service is installed", "Install protection"
        if running:
            try:
                health = config.read_json(os.path.join(config.data_dir(), "health.json"), {})
                if time.time() - health.get("updated", 0) > 20:
                    color, text, sub = C["warn"], "Service starting / unresponsive", "No recent enforcement heartbeat"
                elif not health.get("ok"):
                    color, text, sub = C["danger"], "Protection needs attention", health.get("error", "See diagnostics")[:80]
                else:
                    sub = "%s exact hosts · %s domain roots · browser restart may be needed" % (health.get("hosts", 0), health.get("domains", 0))
            except (OSError, ValueError):
                color, text, sub = C["warn"], "Health unavailable", "Open diagnostics"
        self.dot.itemconfigure(self.dot_item, fill=color)
        self.status_lbl.configure(text=text)
        self.status_sub.configure(text=sub)
        if btn:
            self.fix_btn.configure(text=btn)
            self.fix_btn.pack(side="right", padx=14, pady=8)
        else:
            self.fix_btn.pack_forget()

    def refresh_all(self):
        if self._ticks % 5 == 0 and IS_WINDOWS:
            self._installed = install.is_installed()
        self.refresh_rules()
        self.refresh_status()

    def _tick(self):
        self._ticks += 1
        try:
            self.refresh_all()
        except Exception as exc:
            self.status_lbl.configure(text="Status check failed")
            self.status_sub.configure(text=str(exc)[:90])
            self.dot.itemconfigure(self.dot_item, fill=C["warn"])
        finally:
            self.after(2000, self._tick)


def run_gui():
    app = App()
    if not app.authenticate():
        app.destroy()
        return
    app.build()
    app.deiconify()
    app.mainloop()
