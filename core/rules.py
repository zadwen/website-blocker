"""Block rules: parsing, scheduling logic and hostname expansion."""
import datetime
import re
import time
import uuid

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# hosts files have no wildcards, so we add the usual subdomains automatically.
COMMON_SUBS = ("www", "m", "mobile")
ALIASES = {
    "youtube.com": ["youtu.be", "music.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"],
    "x.com": ["twitter.com", "www.twitter.com", "t.co"],
    "twitter.com": ["x.com", "www.x.com", "t.co"],
    "facebook.com": ["fb.com", "www.fb.com", "fb.watch", "messenger.com", "www.messenger.com"],
    "instagram.com": ["i.instagram.com"],
    "tiktok.com": ["vm.tiktok.com", "vt.tiktok.com"],
    "discord.com": ["discord.gg", "discordapp.com", "www.discordapp.com"],
    "reddit.com": ["old.reddit.com", "new.reddit.com"],
    "roblox.com": ["web.roblox.com"],
    "snapchat.com": ["web.snapchat.com"],
}


def normalize_domain(text):
    t = (text or "").strip().lower()
    t = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", t)
    t = re.split(r"[/?#]", t, maxsplit=1)[0]
    t = t.split("@")[-1].split(":")[0]
    if t.startswith("www."):
        t = t[4:]
    t = t.strip(".")
    try:
        t = t.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValueError("That doesn't look like a valid website.")
    if not DOMAIN_RE.match(t):
        raise ValueError("Enter a website like  youtube.com")
    return t


def hostnames_for(domain):
    names = [domain] + ["%s.%s" % (s, domain) for s in COMMON_SUBS]
    names += ALIASES.get(domain, [])
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def make_rule(domain, mode, **extra):
    rule = {"id": uuid.uuid4().hex, "domain": domain, "mode": mode, "created": time.time()}
    rule.update(extra)
    return rule


def parse_hhmm(text):
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", text or "")
    if not m:
        raise ValueError("Use 24-hour time like 22:00")
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        raise ValueError("Use 24-hour time like 22:00")
    return h * 60 + mi


def is_active(rule, used=0.0, now=None):
    """Is this rule blocking right now?  `used` = seconds of timer already consumed."""
    mode = rule.get("mode")
    if mode == "forever":
        return True
    if mode == "timer":
        return float(used) < float(rule.get("duration", 0))
    if mode == "schedule":
        dt = datetime.datetime.fromtimestamp(now if now is not None else time.time())
        start, end = parse_hhmm(rule["start"]), parse_hhmm(rule["end"])
        days = rule.get("days", list(range(7)))
        cur = dt.hour * 60 + dt.minute
        today, yesterday = dt.weekday(), (dt.weekday() - 1) % 7
        if start == end:
            return today in days
        if start < end:
            return today in days and start <= cur < end
        # overnight window (e.g. 22:00 -> 07:00)
        if cur >= start:
            return today in days
        return cur < end and yesterday in days
    return False


def _fmt_secs(s):
    s = int(max(0, s))
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return "%dd %dh" % (d, h)
    if h:
        return "%dh %dm" % (h, m)
    return "%dm" % max(m, 1) if s else "0m"


def describe(rule):
    mode = rule.get("mode")
    if mode == "forever":
        return "Forever"
    if mode == "timer":
        return "Timer · " + _fmt_secs(rule.get("duration", 0))
    if mode == "schedule":
        days = rule.get("days", [])
        dtxt = "every day" if len(days) == 7 else ", ".join(DAY_NAMES[d] for d in sorted(days))
        return "Daily %s–%s (%s)" % (rule["start"], rule["end"], dtxt)
    return mode or "?"


def status_text(rule, used=0.0, now=None):
    mode = rule.get("mode")
    if mode == "forever":
        return "Blocked"
    if mode == "timer":
        left = float(rule.get("duration", 0)) - float(used)
        return ("%s left" % _fmt_secs(left)) if left > 0 else "Expired"
    if mode == "schedule":
        return "Blocked now" if is_active(rule, used, now) else "Allowed now"
    return ""
