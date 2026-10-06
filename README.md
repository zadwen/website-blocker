# Website Blocker 2.0 · by zadwen

A Windows desktop tool for restricting websites and their domains. Local-only configuration,
parent/admin PIN, scheduled blocking, and a background startup task. No browsing history collection,
cloud account, subscription, or remote blocklist downloads.

## What's new

- **Domain-wide browser blocking:** Chrome and Edge `URLBlocklist`, Firefox `WebsiteFilter`.
  A rule for `example.com` includes `a.b.example.com` in supported browsers, without enumerating subdomains.
  Policies are also written for Brave and Vivaldi; verify support in your installed browser's policy page.
- **Hosts fallback:** IPv4 and IPv6 entries for the domain, common subdomains, known aliases, and related service roots.
- **Optional related service domains:** curated offline bundles for YouTube, Instagram, TikTok, X,
  Facebook, Discord, Reddit, Snapchat, Twitch, Roblox, and Netflix. Coverage shows the exact list.
- **Management:** permanent rules, active-runtime timers, overnight weekday schedules, pause/resume,
  search, double-click editing, category presets, bulk text/hosts imports, portable JSON export/import.
- **Diagnostics:** active rule totals, URL coverage check, service heartbeat, last error, and local logs.
- **Recovery:** validate all rules before saving, atomic JSON writes, last-good configuration,
  original hosts backup, write-ahead per-value registry backup, and safe policy restoration on removal.
- **Build pipeline:** Windows EXE artifact on push or manual GitHub Actions run; tests run before packaging.

## Get the Windows EXE (no local Python required)

1. Put these updated files in your repository, including **`.github/workflows/build.yml`**.
2. Open **Actions → Build Windows EXE → Run workflow** (or let a push trigger it).
3. Open the successful run. Under **Artifacts**, download **WebsiteBlocker-Windows**.
4. Extract the ZIP **on Windows**, then run `WebsiteBlocker.exe` and approve UAC.
5. Create your PIN on first run. The packaged application installs its startup task.
6. Add a domain, choose the time rule, and select whether related service domains should be included.
7. Close and reopen your browser; verify the policy loaded. The desktop window can then be closed.

The executable is unsigned unless you sign it yourself. No EXE is included in the source archive.
Updating repository files does not itself publish a GitHub Release; the workflow produces an artifact.

### Build locally on Windows

Install Python 3.12 (including Tcl/Tk), then run `build.bat` from the extracted project.
Output: `dist\WebsiteBlocker.exe`. Dependencies are bounded in the requirements files.

### Upgrade an existing installation

Keep `C:\ProgramData\WebsiteBlocker` and its settings. Close the old control panel.
Run the newly built EXE, enter your existing PIN, then choose **Settings → Repair / reinstall**.
**Do not uninstall the old version first:** uninstall removes settings.
Version 1 configurations load without manual migration. Restart browsers after the upgrade.
Version 1 did not save prior Secure DNS values; v2 can only preserve the values present at the time of upgrade.

## How domain coverage works

| Layer | Covers | Important limits |
| --- | --- | --- |
| Browser policy | Domain plus all subdomains in supported browsers | Requires browser policy refresh/restart; existing allowlists or enterprise management can override rules |
| Hosts file | Explicit names displayed in Coverage | No wildcard matching; apps using external resolution, cached connections, IPs or proxies may bypass |
| Service bundles | Selected related service/CDN domains | Offline starting lists, not exhaustive discovery; other features of the service can be affected |

For example, a YouTube rule can include `youtube.com`, `youtu.be`, `youtube-nocookie.com`,
`googlevideo.com`, `ytimg.com`, and `youtubei.googleapis.com`. It deliberately does not block all of
`google.com` or `googleapis.com`. You can turn related domains off for a narrower rule.
Blocking a URL blocks its **domain**, not just that page. `www.example.com` is normalized to `example.com`.
`*.example.com` is accepted as shorthand. Individual subdomains such as `school.example.com` can be added.
Internationalized domain names are converted to ASCII IDNA form. IP address rules are rejected.

The tool is for Windows 10/11 administration and focus/parental control. It does not filter other devices,
inspect HTTPS traffic, block every VPN/proxy, or prevent an administrator from changing the system.
Use a **standard Windows account** for the person subject to restrictions and keep admin credentials private.

## Rules and timing

- **Forever:** active until paused or removed.
- **Timer:** 1 second to 365 days of background-service runtime. Pause freezes the remaining time.
  Shutdown does not consume time. Sleep intervals are capped; this is not a wall-clock deadline.
  State checkpoints every 15 seconds, so a crash/restart can add up to about 15 seconds.
- **Schedule:** local Windows clock and selected start days. Monday 22:00–07:00 includes Tuesday morning.
  Equal start/end means the entire selected calendar day. Clock/timezone changes affect schedules.
- Hosts changes are checked about every 3 seconds. Browser policy writes occur on rule transitions and
  are rechecked at least every 60 seconds. **Actual browser reload can lag behind writes.**
- Double-click to edit a rule; replacing a timer starts it again. “Add time” extends the timer.

## Bulk lists and backups

Under **Lists & diagnostics**, paste one domain or URL per line, comma-separated domains, or a hosts list.
`#` comments and the usual `0.0.0.0`, `127.0.0.1`, `::`, `::1` prefixes are accepted.
Adblock filter syntax is not supported. Every entry is validated before any rule is imported.
Existing domain rules are kept; duplicates are skipped. Text and presets create permanent rules.
JSON backups preserve rule options but generate fresh IDs; imported timers restart.
PINs, elapsed timer state, registry backups and machine paths are not exported.
Limits: 2 MB import, 500 rules, 900 expanded roots. Browser lists also have a 1,000-entry ceiling;
existing machine policies count toward that limit and excess is reported, not silently truncated.

## Diagnostics and troubleshooting

1. The status bar must show recent successful enforcement, not just a running process.
2. Open **Lists & diagnostics → View service health / View recent errors**.
3. Use **Check domain** for configured coverage. This is an offline rule check, not a network probe.
4. Restart the browser. Open `chrome://policy`, `edge://policy`, `brave://policy`,
   `vivaldi://policy`, or Firefox `about:policies`. Confirm `URLBlocklist` / `WebsiteFilter` and its values.
5. Existing URL allowlists, Firefox exceptions, higher-priority enterprise policy, and unsupported
   browsers can change the result. Website Blocker does not erase these policies.
6. Already-loaded pages/media and existing connections may continue temporarily. Close existing tabs/apps.
7. Click **Repair / reinstall** if the task is absent or not running.

Do not run multiple control-panel windows editing the same settings simultaneously.
Do not manually delete recovery files while protection is installed.

## Recovery and uninstall

**Settings → Uninstall completely** stops and removes the task, removes only the managed hosts section,
and restores journaled browser settings. Unrelated list entries are retained. Values modified externally
after our last write are left intact. If restoration fails, the tool keeps its recovery data and reports the error.
The application/data folders are removed only after successful cleanup.

Files in `C:\ProgramData\WebsiteBlocker` (SYSTEM and Administrators only):

- `config.json`: PIN hash and rules.
- `last-good-config.json`: last saved configuration used if the main file becomes unreadable.
- `state.json`: elapsed timer values.
- `policy-backup.json`: original and applied registry values, saved before registry writes.
- `hosts-before-install.txt`: original hosts snapshot for manual recovery (never blindly restored).
- `health.json`, `service.log`: local health and rotating operational errors; not browsing logs.

Forgot the PIN? As the PC administrator, back up the data folder and set only the `pin` field in
`config.json` to `null`, then reopen the application to set a new PIN. Do not delete the entire folder:
that would destroy the browser policy recovery journal. Administrator access always overrides the app.

## Development and verification

```console
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python tests/gui_smoke.py
python main.py
```

Source mode is a GUI preview; it intentionally cannot register user-writable Python source as a SYSTEM task.
Build the packaged EXE to install enforcement. Linux/macOS can run core tests; they are not blocking targets.
The GUI smoke test needs a desktop display (on Linux: `xvfb-run -a python tests/gui_smoke.py`).
Automated registry tests use an in-memory adapter. Real Windows installation, browser loading, UAC,
startup, ACLs and uninstall must be acceptance-tested on a Windows PC; see `docs/WINDOWS_TEST_CHECKLIST.md`.

## Technical references

- [Chromium URLBlocklist matching](https://www.chromium.org/administrators/url-blocklist-filter-format/)
- [Chrome website blocking and limits](https://support.google.com/chrome/a/answer/7532419)
- [Firefox WebsiteFilter policy](https://firefox-admin-docs.mozilla.org/reference/policies/websitefilter/)
- [Mozilla match patterns](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Match_patterns)

MIT licensed. Original project: [zadwen/website-blocker](https://github.com/zadwen/website-blocker).
