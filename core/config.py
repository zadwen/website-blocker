"""Persistent settings + timer state, stored where standard users can't touch them."""
import copy
import hashlib
import hmac
import json
import os
import secrets

from .winutil import IS_WINDOWS, run_hidden

DEFAULT_CONFIG = {
    "version": 1,
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
    run_hidden([
        "icacls", path, "/inheritance:r",
        "/grant:r", "*S-1-5-18:(OI)(CI)F",
        "/grant:r", "*S-1-5-32-544:(OI)(CI)F",
    ])


def ensure_data_dir():
    d = data_dir()
    fresh = not os.path.isdir(d)
    os.makedirs(d, exist_ok=True)
    if fresh:
        lock_down(d)
    return d


def _atomic_write_json(path, data):
    ensure_data_dir()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


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
    return cfg


def save_config(cfg):
    _atomic_write_json(config_path(), cfg)


def load_state():
    try:
        with open(state_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("used"), dict):
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
