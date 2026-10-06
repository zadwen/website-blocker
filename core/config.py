"""Persistent settings + timer state, stored where standard users can't touch them."""
import copy
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import math

from .winutil import IS_WINDOWS, run_hidden

DEFAULT_CONFIG = {
    "version": 2,
    "browser_blocking": True,
    "pin": None,          # {"salt","hash","iter"}
    "rules": [],          # see core/rules.py
    "disable_doh": True,  # stop browsers bypassing the block with Secure DNS
}
PBKDF2_ITER = 200_000


def data_dir():
    override = os.environ.get("WB_DATA_DIR")
    if override:
        return override
    return os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "WebsiteBlocker")


def config_path():
    return os.path.join(data_dir(), "config.json")


def state_path():
    return os.path.join(data_dir(), "state.json")


def log_path():
    return os.path.join(data_dir(), "service.log")


def lock_down(path):
    """Only SYSTEM and Administrators may read/write the data folder."""
    if not IS_WINDOWS:
        return
    result = run_hidden([
        "icacls", path, "/inheritance:r",
        "/grant:r", "*S-1-5-18:(OI)(CI)F",
        "/grant:r", "*S-1-5-32-544:(OI)(CI)F",
    ])
    if result.returncode:
        raise OSError("Could not secure settings directory: " + (result.stderr or result.stdout))


def ensure_data_dir():
    d = data_dir()
    fresh = not os.path.isdir(d)
    os.makedirs(d, exist_ok=True)
    if fresh:
        lock_down(d)
    return d


def _atomic_write_json(path, data):
    ensure_data_dir()
    fd, tmp = tempfile.mkstemp(prefix=".wb-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return copy.deepcopy(default)


def validate_config(cfg):
    from .rules import validate_rule, domain_roots
    if cfg.get("version", 1) not in (1, 2):
        raise ValueError("Unsupported settings version.")
    if not isinstance(cfg.get("rules"), list) or len(cfg["rules"]) > 500:
        raise ValueError("At most 500 rules are supported.")
    ids, domains, roots = set(), set(), set()
    for rule in cfg["rules"]:
        validate_rule(rule)
        if rule["id"] in ids or rule["domain"] in domains:
            raise ValueError("Duplicate rule ID or domain.")
        ids.add(rule["id"])
        domains.add(rule["domain"])
        roots.update(domain_roots(rule))
    if len(roots) > 900:
        raise ValueError("Too many expanded domains (maximum 900).")
    pin = cfg.get("pin")
    if pin is not None:
        if not isinstance(pin, dict):
            raise ValueError("Invalid PIN record.")
        try:
            if len(bytes.fromhex(pin["salt"])) != 16 or len(bytes.fromhex(pin["hash"])) != 32:
                raise ValueError("Invalid PIN record.")
            if type(pin["iter"]) is not int or not 100000 <= pin["iter"] <= 2000000:
                raise ValueError("Invalid PIN work factor.")
        except (KeyError, TypeError) as exc:
            raise ValueError("Invalid PIN record.") from exc
    for key in ("disable_doh", "browser_blocking"):
        if key in cfg and not isinstance(cfg[key], bool):
            raise ValueError(key + " must be true or false.")
    return cfg


def load_config():
    """Raises ValueError if the file is corrupt (callers decide what to do)."""
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(data, dict):
        raise ValueError("config is not an object")
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(data)
    if not isinstance(cfg["rules"], list):
        raise ValueError("rules must be a list")
    return validate_config(cfg)


def save_config(cfg):
    validate_config(cfg)
    _atomic_write_json(config_path(), cfg)
    _atomic_write_json(os.path.join(data_dir(), "last-good-config.json"), cfg)


def load_state():
    try:
        with open(state_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("used"), dict):
            data["used"] = {k: v for k, v in data["used"].items()
                            if isinstance(v, (int, float)) and math.isfinite(v) and v >= 0}
            return data
    except (FileNotFoundError, ValueError):
        pass
    return {"used": {}}


def save_state(state):
    _atomic_write_json(state_path(), state)


# ---- PIN -------------------------------------------------------------------
def make_pin_record(pin):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PBKDF2_ITER)
    return {"salt": salt.hex(), "hash": digest.hex(), "iter": PBKDF2_ITER}


def check_pin(cfg, pin):
    rec = cfg.get("pin")
    if not rec:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), bytes.fromhex(rec["salt"]), int(rec["iter"])
    )
    return hmac.compare_digest(digest.hex(), rec["hash"])
