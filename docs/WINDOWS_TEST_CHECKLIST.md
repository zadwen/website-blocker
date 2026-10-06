# Windows acceptance checklist

Run on a disposable Windows 10/11 VM or your own administered PC. Preserve existing hosts and policies first.
These checks are required before calling a release production-tested; the automated suite mocks registry access.

- Build EXE using GitHub Actions or build.bat. Start it, accept UAC and create a PIN.
- Verify startup task runs as SYSTEM from Program Files, with a recent healthy heartbeat.
- Add example.com and verify both hosts address families, Chrome/Edge URLBlocklist and Firefox WebsiteFilter.
- Verify example.com and www.example.com navigation is blocked after restarting browsers.
- Confirm an unrelated website still loads. Confirm domain suffix collisions do not match in coverage checker.
- Block youtube.com with related domains; inspect Coverage and policies. Disable related domains by editing;
  verify unrelated service roots are removed. Do not expect already-buffered media to stop immediately.
- Pause/resume a rule. Verify hosts and policy removal/addition and browser refresh behavior.
- Test a short timer and weekday/overnight schedule. Verify elapsed time resumes after reboot.
- Add an existing URLBlocklist value before install; verify it remains during install and uninstall.
- Set a non-default Secure DNS policy before install; verify uninstall restores it.
- Verify existing browser URL allowlists/exceptions are retained; report their overrides to the administrator.
- Make config.json unreadable or invalid with the service running; confirm last-good rules and degraded health.
- Close GUI and restart Windows. Verify protection starts on battery as well as AC.
- Test a standard-user Windows account; verify it cannot modify ProgramData settings or installed EXE.
- Upgrade v1 using Repair / reinstall without deleting data; verify existing PIN, rules and timers.
- Uninstall. Verify task/process gone, unrelated hosts lines and policies retained, owned policies removed.
- Simulate a registry restoration failure and verify recovery files are retained and an error is shown.

## Verification performed for this source delivery

Core regression suite: 31 tests passed on Linux; Python compilation and `git diff --check` passed.
A GUI smoke test is included in the Windows CI workflow but could not run in the delivery environment,
which has no display server. No Windows EXE was built here. No live Windows registry, startup task,
browser enforcement, or uninstall acceptance tests were performed here.
