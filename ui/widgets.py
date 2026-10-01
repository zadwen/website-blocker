"""Small themed widget helpers."""
import tkinter as tk

from core.branding import COLORS as C


def lerp(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def button(parent, text, command, kind="primary", width=None, pad=(16, 9)):
    colors = {
        "primary": (C["accent"], C["accent_hover"], "white"),
        "danger": (C["danger"], C["danger_hover"], "white"),
        "ghost": (C["panel2"], C["line"], C["text"]),
    }
    bg, hover, fg = colors[kind]
    b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
                  activeforeground=fg, relief="flat", bd=0, cursor="hand2",
                  font=("Segoe UI", 10, "bold"), padx=pad[0], pady=pad[1], width=width)
    b.bind("<Enter>", lambda e: b.configure(bg=hover))
    b.bind("<Leave>", lambda e: b.configure(bg=bg))
    return b


def chip(parent, text, command):
    b = tk.Button(parent, text=text, command=command, bg=C["panel2"], fg=C["muted"],
                  activebackground=C["accent"], activeforeground="white", relief="flat", bd=0,
                  cursor="hand2", font=("Segoe UI", 9), padx=8, pady=3)
    b.bind("<Enter>", lambda e: b.configure(bg=C["line"], fg=C["text"]))
    b.bind("<Leave>", lambda e: b.configure(bg=C["panel2"], fg=C["muted"]))
    return b


def entry(parent, textvariable=None, width=24, show=None, font_size=11):
    e = tk.Entry(parent, textvariable=textvariable, width=width, show=show, bg=C["panel2"],
                 fg=C["text"], insertbackground=C["text"], relief="flat", bd=0,
                 highlightthickness=1, highlightbackground=C["line"],
                 highlightcolor=C["accent"], font=("Segoe UI", font_size))
    return e


def label(parent, text, muted=False, size=10, bold=False, **kw):
    return tk.Label(parent, text=text, bg=kw.pop("bg", C["panel"]),
                    fg=C["muted"] if muted else C["text"],
                    font=("Segoe UI", size, "bold" if bold else "normal"), **kw)


def card(parent, title=None):
    f = tk.Frame(parent, bg=C["panel"], highlightthickness=1, highlightbackground=C["line"])
    if title:
        tk.Label(f, text=title, bg=C["panel"], fg=C["text"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=18, pady=(14, 6))
    return f


class Header(tk.Canvas):
    HEIGHT = 86

    def __init__(self, parent, title, subtitle, right_text=""):
        super().__init__(parent, height=self.HEIGHT, highlightthickness=0, bd=0, bg=C["bg"])
        self.title_text, self.subtitle, self.right_text = title, subtitle, right_text
        self.bind("<Configure>", self._draw)

    def _draw(self, event):
        self.delete("all")
        w = max(event.width, 1)
        for x in range(0, w, 3):
            self.create_rectangle(x, 0, x + 3, self.HEIGHT, outline="",
                                  fill=lerp(C["accent"], C["accent2"], x / w))
        # monogram
        self.create_oval(24, 20, 68, 64, fill="#ffffff", outline="")
        self.create_text(46, 42, text="Z", fill=C["accent"], font=("Segoe UI", 20, "bold"))
        self.create_text(84, 33, anchor="w", text=self.title_text, fill="white",
                         font=("Segoe UI", 20, "bold"))
        self.create_text(86, 60, anchor="w", text=self.subtitle, fill="#e6f7f7",
                         font=("Segoe UI", 10))
        self.create_text(w - 22, 43, anchor="e", text=self.right_text, fill="#e6f7f7",
                         font=("Segoe UI", 10))
