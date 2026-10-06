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
    """Accept a hostname or HTTP(S) URL, but never an IP or arbitrary wildcard."""
    from urllib.parse import urlsplit
    import ipaddress
    if not isinstance(text, str):
        raise ValueError("Enter a domain name as text.")
    t = text.strip().lower()
    if not t or any(c.isspace() for c in t):
        raise ValueError("Enter a website like youtube.com")
    if t.startswith("*."):
        t = t[2:]
    try:
        parsed = urlsplit(t if "://" in t else "//" + t)
        if parsed.scheme and parsed.scheme not in ("http", "https"):
            raise ValueError("Only HTTP(S) URLs and domain names are supported.")
        _ = parsed.port
        host = (parsed.hostname or "").rstrip(".")
        if host.startswith("www."):
            host = host[4:]
        host = host.encode("idna").decode("ascii")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("Use a domain name, not an IP address.")
        labels = host.split(".")
        if (len(host) > 253 or len(labels) < 2 or labels[-1].isdigit()
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels)):
            raise ValueError("Enter a valid domain like youtube.com")
        return host
    except (UnicodeError, TypeError) as exc:
        raise ValueError("That doesn't look like a valid website.") from exc


def domain_roots(rule):
    from .catalog import related_domains
    domain = normalize_domain(rule["domain"])
    return related_domains(domain) if rule.get("include_related", True) else {domain}


def hostnames_for(domain, include_related=True):
    roots = domain_roots({"domain": domain, "include_related": include_related})
    names = set()
    for root in roots:
        names.add(root)
        names.update(s + "." + root for s in COMMON_SUBS)
        names.update(ALIASES.get(root, []) if include_related else [])
    return sorted(names)


def matches_domain(host, root):
    return host == root or host.endswith("." + root)


def parse_domain_list(text):
    """Plain lines, URLs, comma-separated domains, or hosts-file lists."""
    domains, errors = set(), []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.replace(",", " ").split()
        if parts[0] in ("0.0.0.0", "127.0.0.1", "::", "::1"):
            parts = parts[1:]
        for part in parts:
            try:
                domains.add(normalize_domain(part))
            except ValueError:
                errors.append("Line %d: %s" % (number, part))
    if errors:
        raise ValueError("Invalid entries (nothing imported):\n" + "\n".join(errors[:12]))
    if not domains:
        raise ValueError("No domains found.")
    return sorted(domains)


def validate_rule(rule):
    import math
    if not isinstance(rule, dict):
        raise ValueError("Each rule must be an object.")
    if not isinstance(rule.get("id"), str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", rule["id"]):
        raise ValueError("Invalid rule ID.")
    if normalize_domain(rule.get("domain")) != rule["domain"]:
        raise ValueError("Rule domains must be normalized.")
    if rule.get("mode") not in ("forever", "timer", "schedule"):
        raise ValueError("Invalid rule mode.")
    for key in ("enabled", "include_related"):
        if key in rule and not isinstance(rule[key], bool):
            raise ValueError(key + " must be true or false.")
    if rule["mode"] == "timer":
        duration = rule.get("duration")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 < duration <= 31536000:
            raise ValueError("Timer duration must be between 1 second and 365 days.")
    if rule["mode"] == "schedule":
        parse_hhmm(rule.get("start"))
        parse_hhmm(rule.get("end"))
        days = rule.get("days")
        if not isinstance(days, list) or not days or any(type(d) is not int or d not in range(7) for d in days):
            raise ValueError("Choose valid schedule days.")
    return rule


def make_rule(domain, mode, **extra):
    rule = {"id": uuid.uuid4().hex, "domain": normalize_domain(domain), "mode": mode, "created": time.time(), "enabled": True, "include_related": True}
    rule.update(extra)
    return validate_rule(rule)


def parse_hhmm(text):
    if not isinstance(text, str):
        raise ValueError("Use 24-hour time like 22:00")
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", text)
    if not m:
        raise ValueError("Use 24-hour time like 22:00")
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        raise ValueError("Use 24-hour time like 22:00")
    return h * 60 + mi


def is_active(rule, used=0.0, now=None):
    """Is this rule blocking right now?  `used` = seconds of timer already consumed."""
    if not rule.get("enabled", True):
        return False
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
    if not rule.get("enabled", True):
        return "Paused"
    mode = rule.get("mode")
    if mode == "forever":
        return "Blocked"
    if mode == "timer":
        left = float(rule.get("duration", 0)) - float(used)
        return ("%s left" % _fmt_secs(left)) if left > 0 else "Expired"
    if mode == "schedule":
        return "Blocked now" if is_active(rule, used, now) else "Allowed now"
    return ""
