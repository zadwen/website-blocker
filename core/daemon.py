"""The silent background worker. Runs as SYSTEM from Task Scheduler at boot.

Every few seconds it:
  * counts down timer blocks (using the monotonic clock, so changing the
    Windows clock can't cheat a timer),
  * works out which sites should be blocked right now,
  * re-writes the hosts file if anything (or anyone) changed it.
"""
import logging
import os
import logging.handlers
import sys
import time

from . import config, hosts, rules, policies
from .winutil import IS_WINDOWS

MUTEX_NAME = "Global\\WebsiteBlockerDaemon"
TICK = 3.0
STATE_SAVE_EVERY = 15.0
DOH_EVERY = 60.0


def _acquire_single_instance():
    if not IS_WINDOWS:
        return True
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    handle = k32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return False
    _acquire_single_instance.handle = handle  # keep alive for process lifetime
    return True


def _setup_logging():
    try:
        config.ensure_data_dir()
        h = logging.handlers.RotatingFileHandler(
            config.log_path(), maxBytes=200_000, backupCount=1, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log = logging.getLogger("wb")
        log.setLevel(logging.INFO)
        log.addHandler(h)
        return log
    except Exception:
        return logging.getLogger("wb")


def compute_hostnames(cfg, used):
    names = set()
    for r in cfg.get("rules", []):
        try:
            if rules.is_active(r, used.get(r.get("id"), 0.0)):
                names.update(rules.hostnames_for(r["domain"], r.get("include_related", True)))
        except Exception:
            continue
    return names


def run():
    if not _acquire_single_instance():
        return
    log = _setup_logging()
    log.info("service started")

    state = config.load_state()
    try:
        last_good_cfg = config.validate_config(config.read_json(
            os.path.join(config.data_dir(), "last-good-config.json"), config.DEFAULT_CONFIG))
    except Exception:
        last_good_cfg = None
    last_tick = time.monotonic()
    last_save = last_doh = 0.0
    dirty = False
    policy_signature = None
    last_health = 0.0

    while True:
        try:
            now = time.monotonic()
            # Cap the step so a sleeping laptop doesn't burn the whole timer.
            delta = min(max(now - last_tick, 0.0), TICK * 3)
            last_tick = now

            config_warning = ""
            try:
                if not os.path.exists(config.config_path()):
                    raise ValueError("Settings file missing")
                cfg = config.load_config()
                last_good_cfg = cfg
            except Exception as e:  # corrupt/being written: keep enforcing last good
                log.warning("config unreadable (%s); using last known good", e)
                config_warning = "Settings unreadable; enforcing last saved rules: " + str(e)
                if last_good_cfg is None:
                    raise RuntimeError("No valid configuration; leaving existing protection untouched")
                cfg = last_good_cfg

            used = state["used"]
            ids = set()
            for r in cfg["rules"]:
                rid = r.get("id")
                ids.add(rid)
                if r.get("mode") == "timer" and r.get("enabled", True):
                    cur = float(used.get(rid, 0.0))
                    if cur < float(r.get("duration", 0)):
                        used[rid] = min(cur + delta, float(r["duration"]))
                        dirty = True
            for stale in [k for k in used if k not in ids]:
                del used[stale]
                dirty = True

            if dirty and now - last_save >= STATE_SAVE_EVERY:
                config.save_state(state)
                dirty, last_save = False, now

            hosts.apply(compute_hostnames(cfg, used))

            signature = repr(policies.desired_policies(cfg, used))
            if signature != policy_signature or now - last_doh >= DOH_EVERY:
                policies.apply(cfg, used)
                policy_signature, last_doh = signature, now

            if now - last_health >= 5:
                config._atomic_write_json(os.path.join(config.data_dir(), "health.json"),
                    {"updated": time.time(), "ok": not bool(config_warning), "hosts": len(compute_hostnames(cfg, used)),
                     "domains": len(policies.active_roots(cfg, used)), "error": config_warning})
                last_health = now

        except Exception as exc:
            log.exception("tick failed")
            try:
                config._atomic_write_json(os.path.join(config.data_dir(), "health.json"),
                    {"updated": time.time(), "ok": False, "error": str(exc)})
            except Exception:
                log.exception("health report failed")
        time.sleep(TICK)


if __name__ == "__main__":
    run()
    sys.exit(0)
