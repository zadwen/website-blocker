"""The silent background worker. Runs as SYSTEM from Task Scheduler at boot.

Every few seconds it:
  * counts down timer blocks (using the monotonic clock, so changing the
    Windows clock can't cheat a timer),
  * works out which sites should be blocked right now,
  * re-writes the hosts file if anything (or anyone) changed it.
"""
import logging
import logging.handlers
import sys
import time

from . import config, doh, hosts, rules
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
    handle = k32.CreateMutexW(None, False, MUTEX_NAME)
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
                names.update(rules.hostnames_for(r["domain"]))
        except Exception:
            continue
    return names


def run():
    if not _acquire_single_instance():
        return
    log = _setup_logging()
    log.info("service started")

    state = config.load_state()
    last_good_cfg = None
    last_tick = time.monotonic()
    last_save = last_doh = 0.0
    dirty = False

    while True:
        try:
            now = time.monotonic()
            # Cap the step so a sleeping laptop doesn't burn the whole timer.
            delta = min(max(now - last_tick, 0.0), TICK * 3)
            last_tick = now

            try:
                cfg = config.load_config()
                last_good_cfg = cfg
            except Exception as e:  # corrupt/being written: keep enforcing last good
                log.warning("config unreadable (%s); using last known good", e)
                cfg = last_good_cfg or {"rules": [], "disable_doh": True}

            used = state["used"]
            ids = set()
            for r in cfg["rules"]:
                rid = r.get("id")
                ids.add(rid)
                if r.get("mode") == "timer":
                    cur = float(used.get(rid, 0.0))
                    if cur < float(r.get("duration", 0)):
                        used[rid] = cur + delta
                        dirty = True
            for stale in [k for k in used if k not in ids]:
                del used[stale]
                dirty = True

            hosts.apply(compute_hostnames(cfg, used))

            if now - last_doh >= DOH_EVERY:
                doh.apply(bool(cfg.get("disable_doh", True)))
                last_doh = now

            if dirty and now - last_save >= STATE_SAVE_EVERY:
                config.save_state(state)
                dirty, last_save = False, now
        except Exception:
            log.exception("tick failed")
        time.sleep(TICK)


if __name__ == "__main__":
    run()
    sys.exit(0)
