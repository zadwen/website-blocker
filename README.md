# Website Blocker  ·  by zadwen

A parental-control tool for Windows. Pick the websites you want blocked, choose **forever**,
a **timer**, or a **daily schedule**, and it enforces the block silently in the background,
from startup, on any Wi-Fi network. It only blocks sites. It does not record or monitor anything.

## How it works
- **Hosts-file blocking**: blocked sites are pointed at `0.0.0.0` in the Windows hosts file, which is
  checked before DNS, so it works on every network and survives Wi-Fi changes.
- **Hidden SYSTEM service**: a Task Scheduler task (boot + every 5 min, restart on failure) runs
  `WebsiteBlocker.exe --daemon` as SYSTEM. It has no window or tray icon, and a standard user
  cannot end it.
- **Self-healing**: every 3 seconds the service checks the hosts file and puts the block back if it
  was edited.
- **Timers use a monotonic clock**, so changing the Windows clock can't cheat a timer.
- **Browser Secure-DNS (DoH) is switched off by policy** so browsers can't skip the hosts file.
- **Parent PIN** (PBKDF2) protects the app; settings live in `C:\ProgramData\WebsiteBlocker`,
  readable only by SYSTEM and Administrators.

## Install
1. Build `WebsiteBlocker.exe` (`build.bat` on Windows, or push a `v*` tag and let GitHub Actions do it).
2. **Make the kids' Windows accounts "Standard" (not Administrator).** This is what makes it hard to
   close or remove. Keep your own account as the Administrator.
3. Run `WebsiteBlocker.exe` from your admin account, approve the UAC prompt, and create your PIN.
   Protection installs automatically. You can then close the window.

Dev run: `pip install pillow` then `python main.py`.

## Limitations (be honest with yourself)
- If a child has an **Administrator** account, nothing can stop them. Use a Standard account.
- VPNs, proxy sites, and non-Chrome/Edge/Firefox browsers can bypass hosts-file blocking.
- The hosts file has no wildcards. Common subdomains (www, m, mobile) and a few aliases are
  included. Add other subdomains as separate entries.
- Scheduled blocks use the Windows clock. Standard users can change the clock by default; you can
  remove that right in *Local Security Policy → User Rights → Change the system time*.
- Forgot your PIN? Delete `C:\ProgramData\WebsiteBlocker\config.json` as Administrator
  (this clears your rules too).

## Tests
`python tests/test_logic.py`

MIT licensed.
