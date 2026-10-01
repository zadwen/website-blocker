"""Turn off browser 'Secure DNS' (DNS-over-HTTPS) so it can't skip the hosts file."""
from .winutil import IS_WINDOWS

_CHROMIUM = [("DnsOverHttpsMode", "off", "sz")]
POLICIES = [
    (r"SOFTWARE\Policies\Google\Chrome", _CHROMIUM),
    (r"SOFTWARE\Policies\Microsoft\Edge", _CHROMIUM),
    (r"SOFTWARE\Policies\BraveSoftware\Brave", _CHROMIUM),
    (r"SOFTWARE\Policies\Vivaldi", _CHROMIUM),
    (r"SOFTWARE\Policies\Mozilla\Firefox\DNSOverHTTPS",
     [("Enabled", 0, "dword"), ("Locked", 1, "dword")]),
]


def apply(disable_doh):
    if not IS_WINDOWS:
        return
    import winreg
    access = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY
    for path, values in POLICIES:
        if disable_doh:
            key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0, access)
            with key:
                for name, val, kind in values:
                    typ = winreg.REG_SZ if kind == "sz" else winreg.REG_DWORD
                    try:
                        cur, cur_t = winreg.QueryValueEx(key, name)
                        if cur == val and cur_t == typ:
                            continue
                    except FileNotFoundError:
                        pass
                    winreg.SetValueEx(key, name, 0, typ, val)
        else:
            try:
                key = winreg.OpenKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0, access)
            except FileNotFoundError:
                continue
            with key:
                for name, _v, _k in values:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
