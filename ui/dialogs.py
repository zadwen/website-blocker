import tkinter as tk
from tkinter import ttk

from core.branding import COLORS as C
from ui.widgets import button, entry, label


class _Modal(tk.Toplevel):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.result = None
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())
        self.attributes("-topmost", True)

    def _cancel(self):
        self.result = None
        self.destroy()

    def show(self):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 3
        self.geometry("+%d+%d" % (x, y))
        self.deiconify()
        self.wait_visibility()
        self.grab_set()
        self.focus_force()
        self.wait_window(self)
        return self.result


class PinDialog(_Modal):
    def __init__(self, parent, title, prompt, confirm=False, error=""):
        super().__init__(parent, title)
        self.confirm = confirm
        body = tk.Frame(self, bg=C["panel"], padx=28, pady=22,
                        highlightthickness=1, highlightbackground=C["line"])
        body.pack(padx=14, pady=14)
        label(body, title, size=14, bold=True).pack(anchor="w")
        label(body, prompt, muted=True, wraplength=320, justify="left").pack(anchor="w", pady=(4, 12))
        self.e1 = entry(body, show="•", width=28, font_size=13)
        self.e1.pack(fill="x", ipady=6)
        self.e2 = None
        if confirm:
            label(body, "Repeat PIN", muted=True).pack(anchor="w", pady=(10, 2))
            self.e2 = entry(body, show="•", width=28, font_size=13)
            self.e2.pack(fill="x", ipady=6)
        self.err = label(body, error, size=9)
        self.err.configure(fg=C["danger"])
        self.err.pack(anchor="w", pady=(8, 0))
        row = tk.Frame(body, bg=C["panel"])
        row.pack(fill="x", pady=(12, 0))
        button(row, "Cancel", self._cancel, "ghost").pack(side="right", padx=(8, 0))
        button(row, "Continue", self._ok).pack(side="right")
        self.bind("<Return>", lambda e: self._ok())
        self.e1.focus_set()

    def _ok(self):
        pin = self.e1.get()
        if self.confirm:
            if len(pin) < 4:
                return self.err.configure(text="Use at least 4 characters.")
            if pin != self.e2.get():
                return self.err.configure(text="The two PINs don't match.")
        elif not pin:
            return
        self.result = pin
        self.destroy()


class AddTimeDialog(_Modal):
    UNITS = {"Minutes": 60, "Hours": 3600, "Days": 86400}

    def __init__(self, parent, domain):
        super().__init__(parent, "Add time")
        body = tk.Frame(self, bg=C["panel"], padx=28, pady=22,
                        highlightthickness=1, highlightbackground=C["line"])
        body.pack(padx=14, pady=14)
        label(body, "Add time", size=14, bold=True).pack(anchor="w")
        label(body, "Keep %s blocked for longer." % domain, muted=True).pack(anchor="w", pady=(4, 12))
        row = tk.Frame(body, bg=C["panel"])
        row.pack(fill="x")
        self.amount = tk.StringVar(value="1")
        self.unit = tk.StringVar(value="Hours")
        entry(row, self.amount, width=6, font_size=12).pack(side="left", ipady=5)
        ttk.Combobox(row, textvariable=self.unit, values=list(self.UNITS), state="readonly",
                     width=9, font=("Segoe UI", 11)).pack(side="left", padx=(8, 0))
        self.err = label(body, "", size=9)
        self.err.configure(fg=C["danger"])
        self.err.pack(anchor="w", pady=(8, 0))
        btns = tk.Frame(body, bg=C["panel"])
        btns.pack(fill="x", pady=(12, 0))
        button(btns, "Cancel", self._cancel, "ghost").pack(side="right", padx=(8, 0))
        button(btns, "Add", self._ok).pack(side="right")
        self.bind("<Return>", lambda e: self._ok())

    def _ok(self):
        try:
            secs = int(float(self.amount.get()) * self.UNITS[self.unit.get()])
            if secs <= 0:
                raise ValueError
        except ValueError:
            return self.err.configure(text="Enter a number greater than 0.")
        self.result = secs
        self.destroy()
