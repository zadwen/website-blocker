# macOS + phone control · by zadwen

The Mac runs Website Blocker in the background. Your iPhone or Android phone controls it through a responsive web app. It can be added to the phone's Home Screen. The included **Website Blocker.app** opens the same dashboard on the Mac. This is a browser-based companion, not an App Store app or an iOS VPN.

## What is included

- System hosts blocking (IPv4/IPv6) plus macOS split DNS for entire blocked suffixes, including random subdomains.
- YouTube, gaming and social presets; custom websites; service-related domain bundles.
- Permanent rules, wall-clock focus timers, weekly schedules (including overnight), per-rule pause, and pause/resume all.
- Root-owned persistent settings, launchd startup, a random 256-bit control key, loopback-only API, exact Host/Origin checks, and enforcement health reporting.
- Private HTTPS phone access through Tailscale, including from a different Wi-Fi or cellular network.
- Key rotation, preserved hosts backup, resolver conflict detection, and an uninstall command that removes only our managed blocks.

**Scope:** controls websites on the Mac. It does not block websites on the phone or other computers. The Mac must be awake and connected for remote control. Rules continue without the phone. This is not tamper-proof against a Mac administrator.

## 1. Install on the Mac

Target: macOS 12 or newer, Apple Silicon or Intel, with **Python 3.11+ from [python.org](https://www.python.org/downloads/macos/)**. No pip packages are needed for the macOS service. Homebrew/user-writable Python is deliberately rejected because the background service runs as root. Native installation and blocking need verification on your actual Mac; the project has automated controller/backend tests.

Download the repository ZIP using **Code → Download ZIP**, extract it, and open Terminal in its folder. Or:

```bash
git clone https://github.com/zadwen/website-blocker.git
cd website-blocker
sudo python3 -I macos/manage.py install
```

Alternatively run `bash macos/Install.command` from the repository root. The password prompt is your **Mac administrator password**. The installer:

1. Copies the Python service into `/Library/Application Support/WebsiteBlocker/app` with a root-only parent directory.
2. Registers `/Library/LaunchDaemons/com.zadwen.websiteblocker.plist`.
3. Installs `/Applications/Website Blocker.app`.
4. Checks that the service is healthy, then displays your random **control key**.

Open **Website Blocker** from Applications or visit `http://127.0.0.1:8765` on the Mac. Paste the key. Add YouTube, then test a new browser session. The launcher is a shell-based unsigned `.app`, not a signed/notarized standalone binary; the localhost address is an equivalent fallback if macOS declines to open it. Do not disable Gatekeeper globally.

To retrieve the key later, from the repository folder:

```bash
sudo python3 -I macos/manage.py key
```

Installing again updates the code while preserving the existing key, rules, timers and backup. Windows settings are separate; there is no automatic Windows PIN/config migration.

## 2. Connect your phone, including away from home

1. Install [Tailscale on your Mac and phone](https://tailscale.com/download) and sign them into the same private tailnet. Connect both devices. Ensure your tailnet access policy permits the phone to reach the Mac on HTTPS/443.
2. On the Mac, run:

   ```bash
   tailscale serve --bg http://127.0.0.1:8765
   ```

   If the CLI is not in PATH, see [Tailscale's macOS CLI instructions](https://tailscale.com/kb/1080/cli). Enable HTTPS when Tailscale prompts you. If you already use Serve on port 443 for another application, resolve that configuration first; do not overwrite an unrelated service.
3. Copy the **exact HTTPS URL** printed by Tailscale. Register it locally (replace the example):

   ```bash
   sudo python3 -I macos/manage.py phone-url https://your-mac.your-tailnet.ts.net
   ```

4. Open that HTTPS URL in Safari on your iPhone (or Chrome on Android). Paste the control key. Use Safari's Share menu → **Add to Home Screen** for an app-like shortcut.
5. Try adding/removing `youtube.com` from the phone while checking it on the Mac. Then repeat with the phone on cellular to verify away-from-home access.

Use **Tailscale Serve**, not Funnel. No router port forwarding is required. The HTTP API binds only to `127.0.0.1`; direct LAN-IP access intentionally does not work. Tailscale supplies the private network and HTTPS. The app additionally requires the control key. Anyone holding the key and network access can change rules, so only share it with your intended controller.

The key stays in page memory, never in a URL, localStorage or a cookie. Reopening/reloading the page requires pasting it again. **Disconnect** clears it from the current page. Home Screen launch does not provide offline remote control.

## 3. Daily use

- **YouTube / Gaming / Social:** adds permanent rules for that bundle. Adding an existing website replaces its previous rule/timer/schedule.
- **Add website:** paste a domain or HTTPS URL. Rules apply to the whole hostname and its subdomains, not just one URL path.
- **Focus timer:** expires at a fixed time, including while the Mac sleeps, reboots, or blocks are paused. Resume does not restart a timer; re-add the site for a new one.
- **Weekly schedule:** uses the Mac's local clock/timezone. Choose the days the window starts. A Monday 22:00–07:00 rule ends Tuesday morning. Equal times mean all day on each selected day.
- **Pause all:** temporarily removes every managed block; rules remain saved until you resume them.
- **Needs attention:** settings may be saved but enforcement failed. Read the error before relying on protection.
- **Mac unreachable:** displayed status is stale. Reconnect before assuming a remote action succeeded. The UI refreshes every ten seconds; the enforcement worker checks rules every three seconds.

## 4. Blocking limits and troubleshooting

Hosts files cannot match arbitrary subdomains. On macOS this edition adds one `/etc/resolver/<domain>` file per active service root. The system resolver directs that suffix to a loopback DNS responder on UDP/TCP **5354**, which replies NXDOMAIN. Unrelated DNS stays with the Mac's existing settings. Known hosts also get IPv4/IPv6 hosts entries.

Applications with their own resolver, browser Secure DNS/DoH, VPNs, proxies, and iCloud Private Relay may bypass this mechanism. For testing, disable those features in the affected browser/network and retry. This version does not install MDM profiles, change browser policies, inspect HTTPS traffic, or claim universal app/game blocking. Existing video streams and cached connections may continue; close the browser fully and reopen it. Blocking game stores does not stop offline games.

A pre-existing resolver with the same name is preserved, and the dashboard reports a conflict. Do not delete corporate/VPN resolver files blindly. More-specific third-party resolver entries can also affect routing; inspect `scutil --dns` if results differ by app. Existing connections and applications' negative DNS caches can delay both blocking and unblocking.

Useful checks:

```bash
sudo launchctl print system/com.zadwen.websiteblocker
sudo tail -n 40 '/Library/Application Support/WebsiteBlocker/errors.log'
sudo tail -n 40 '/Library/Application Support/WebsiteBlocker/service.log'
scutil --dns
dscacheutil -q host -a name www.youtube.com
```

`dig youtube.com` normally queries its own DNS server and is not a reliable test of macOS split resolver behavior. For the local responder specifically use `dig @127.0.0.1 -p 5354 random.youtube.com`; test real blocking in Safari as well.

If corrupted settings prevent startup, existing blocks are left in place rather than silently cleared. Restore your settings from your own backup, or run the uninstall command below to recover normal browsing. The saved original hosts file is for inspection; restoring it wholesale could discard unrelated changes made since installation.

## 5. Revoke phone access / uninstall

Lost control key or lost phone? Rotate the key on the Mac; the old key immediately stops working after the service restarts:

```bash
sudo python3 -I macos/manage.py rotate-key
```

To uninstall:

```bash
sudo python3 -I macos/manage.py uninstall
```

This stops the service, removes its managed resolver/hosts entries, flushes macOS DNS, and removes the launch daemon and launcher. Settings, key and backup remain in the protected data folder for recovery. If you configured Tailscale Serve solely for this app, remove that Serve configuration as well (see the Tailscale CLI documentation); do not reset Serve if it also hosts other services.

## Verification checklist on a real Mac

- Install, confirm healthy API, and reopen the dashboard from Applications.
- Enable YouTube from the phone; verify `youtube.com`, `music.youtube.com`, `youtu.be` and a fresh video fail in Safari while unrelated sites work.
- Test a gaming preset and a custom site. Check browser Secure DNS/Private Relay separately.
- Pause/resume, remove, expire a timer, and test a weekly schedule boundary.
- Reboot: verify service returns, rules persist and remote access returns once Tailscale connects.
- Test from phone cellular, rotate the key, and confirm the old key is rejected.
- Uninstall: verify normal browsing returns and unrelated hosts/resolver settings remain.

## Technical references

- [Apple: Creating launchd jobs](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
- macOS's local `man 5 resolver` and `man 5 hosts` describe system resolver and hosts behavior.
- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve) and [Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve)

## Development tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --check macos/web/app.js
```

Tests use temporary hosts/resolver fixtures and real loopback HTTP/DNS sockets. They do not modify the test machine's system DNS or install a launch daemon. Passing them is not the same as validating native installation or browser behavior.
