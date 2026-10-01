import datetime
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tmp = tempfile.mkdtemp()
os.environ["WB_DATA_DIR"] = os.path.join(tmp, "data")
os.environ["WB_HOSTS_PATH"] = os.path.join(tmp, "hosts")

from core import config, daemon, hosts, rules  # noqa: E402


def ts(y, mo, d, h, mi):
    return datetime.datetime(y, mo, d, h, mi).timestamp()


class RuleTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(rules.normalize_domain("https://www.YouTube.com/watch?v=1"), "youtube.com")
        self.assertEqual(rules.normalize_domain("  tiktok.com  "), "tiktok.com")
        self.assertEqual(rules.normalize_domain("http://user@site.co.uk:8080/x"), "site.co.uk")
        for bad in ("", "localhost", "not a site", "a..com", "-x.com"):
            with self.assertRaises(ValueError):
                rules.normalize_domain(bad)

    def test_timer(self):
        r = {"mode": "timer", "duration": 100}
        self.assertTrue(rules.is_active(r, 99))
        self.assertFalse(rules.is_active(r, 100))

    def test_schedule_same_day(self):
        r = {"mode": "schedule", "start": "09:00", "end": "17:00", "days": [0]}  # Mondays
        mon = ts(2026, 10, 5, 12, 0)   # Monday
        self.assertTrue(rules.is_active(r, now=mon))
        self.assertFalse(rules.is_active(r, now=ts(2026, 10, 5, 18, 0)))
        self.assertFalse(rules.is_active(r, now=ts(2026, 10, 6, 12, 0)))

    def test_schedule_overnight(self):
        r = {"mode": "schedule", "start": "22:00", "end": "07:00", "days": [0]}  # starts Monday night
        self.assertTrue(rules.is_active(r, now=ts(2026, 10, 5, 23, 0)))   # Mon 23:00
        self.assertTrue(rules.is_active(r, now=ts(2026, 10, 6, 6, 30)))   # Tue 06:30 (still Monday's window)
        self.assertFalse(rules.is_active(r, now=ts(2026, 10, 6, 23, 0)))  # Tue night not selected
        self.assertFalse(rules.is_active(r, now=ts(2026, 10, 5, 6, 30)))  # Mon morning (Sunday's window)

    def test_hostnames(self):
        names = rules.hostnames_for("youtube.com")
        self.assertIn("www.youtube.com", names)
        self.assertIn("youtu.be", names)
        self.assertEqual(len(names), len(set(names)))


class HostsTests(unittest.TestCase):
    def setUp(self):
        self.path = hosts.hosts_path()
        with open(self.path, "w", newline="") as f:
            f.write("# my hosts\r\n127.0.0.1 localhost\r\n")

    def read(self):
        with open(self.path, newline="") as f:
            return f.read()

    def test_apply_and_idempotent(self):
        self.assertTrue(hosts.apply(["a.com", "www.a.com"]))
        txt = self.read()
        self.assertIn("0.0.0.0 a.com", txt)
        self.assertIn("127.0.0.1 localhost", txt)
        self.assertTrue(txt.index("WEBSITE-BLOCKER BEGIN") < txt.index("localhost"))
        self.assertFalse(hosts.apply(["a.com", "www.a.com"]))  # no rewrite

    def test_restores_after_tamper(self):
        hosts.apply(["a.com"])
        with open(self.path, "w", newline="") as f:
            f.write("127.0.0.1 localhost\r\n")  # kid deleted our block
        self.assertTrue(hosts.apply(["a.com"]))
        self.assertIn("0.0.0.0 a.com", self.read())

    def test_remove_all(self):
        hosts.apply(["a.com"])
        hosts.apply([])
        txt = self.read()
        self.assertNotIn("WEBSITE-BLOCKER", txt)
        self.assertIn("127.0.0.1 localhost", txt)

    def test_damaged_block_keeps_user_lines(self):
        with open(self.path, "w", newline="") as f:
            f.write("# >>> WEBSITE-BLOCKER BEGIN\r\n0.0.0.0 a.com\r\n10.0.0.5 nas.local\r\n")
        hosts.apply([])
        self.assertIn("10.0.0.5 nas.local", self.read())


class ConfigTests(unittest.TestCase):
    def test_pin(self):
        cfg = {"pin": config.make_pin_record("1234")}
        self.assertTrue(config.check_pin(cfg, "1234"))
        self.assertFalse(config.check_pin(cfg, "1235"))

    def test_roundtrip_and_daemon_selection(self):
        cfg = config.load_config()
        cfg["rules"] = [
            rules.make_rule("a.com", "forever"),
            rules.make_rule("b.com", "timer", duration=60),
        ]
        config.save_config(cfg)
        back = config.load_config()
        used = {back["rules"][1]["id"]: 61}
        names = daemon.compute_hostnames(back, used)
        self.assertIn("a.com", names)
        self.assertNotIn("b.com", names)  # expired timer


if __name__ == "__main__":
    unittest.main()
