"""Writes the managed block into the Windows hosts file.

The hosts file is consulted *before* DNS, so the block works on any network
(home Wi-Fi, school, hotspot...) and survives Wi-Fi changes.
"""
import os
import re
import time

from . import config
from .winutil import IS_WINDOWS, run_hidden

BEGIN_MARK = "# >>> WEBSITE-BLOCKER BEGIN"
END_MARK = "# <<< WEBSITE-BLOCKER END"
_ENTRY_RE = re.compile(r"^(0\.0\.0\.0|::)\s+\S+$")


def hosts_path():
    override = os.environ.get("WB_HOSTS_PATH")
    if override:
        return override
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(root, "System32", "drivers", "etc", "hosts")


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", errors="surrogateescape")
    except FileNotFoundError:
        return ""


def strip_block(text):
    """Remove our managed block, tolerating a damaged/unterminated one."""
    out, skipping = [], False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(END_MARK):
            skipping = False
            continue
        if s.startswith(BEGIN_MARK):
            skipping = True
            continue
        if skipping:
            if s.startswith(END_MARK):
                skipping = False
                continue
            if _ENTRY_RE.match(s):
                continue
            skipping = False  # damaged block: stop eating user lines
        out.append(line)
    return out


def build_block(hostnames):
    lines = [BEGIN_MARK + " (managed - do not edit) >>>"]
    for h in sorted(set(hostnames)):
        from .rules import normalize_domain
        normalize_domain(h)  # reject newline / hosts injection at the write boundary
        if any(c.isspace() for c in h) or ":" in h or "/" in h:
            raise ValueError("Invalid hosts entry")
        lines.append("0.0.0.0 " + h)
        lines.append(":: " + h)
    lines.append(END_MARK + " <<<")
    return lines


def render(current_text, hostnames):
    """Our block goes first so it wins over any later line for the same name."""
    rest = strip_block(current_text)
    while rest and not rest[0].strip():
        rest.pop(0)
    lines = (build_block(hostnames) + [""] if hostnames else []) + rest
    if not lines:
        return ""
    return "\r\n".join(lines).rstrip("\r\n") + "\r\n"


def _write(path, text):
    data = text.encode("utf-8", errors="surrogateescape")
    last = None
    for _ in range(6):
        try:
            with open(path, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            return
        except PermissionError as e:
            last = e
            time.sleep(0.5)
    raise last


def flush_dns():
    if IS_WINDOWS:
        run_hidden(["ipconfig", "/flushdns"])


def apply(hostnames):
    """Make the hosts file reflect `hostnames`. Returns True if it changed."""
    path = hosts_path()
    current = _read(path)
    new = render(current, sorted(hostnames))
    if new == current:
        return False
    config.ensure_data_dir()
    backup = os.path.join(config.data_dir(), "hosts-before-install.txt")
    try:
        with open(backup, "xb") as f:
            f.write(current.encode("utf-8", errors="surrogateescape"))
    except FileExistsError:
        pass
    _write(path, new)
    flush_dns()
    return True
