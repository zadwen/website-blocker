## 3.0.0 — macOS and mobile companion

- Add macOS launchd service, installer/recovery CLI and Applications launcher.
- Add suffix-aware split DNS plus IPv4/IPv6 hosts blocking, preserving unrelated resolver and hosts entries.
- Add private phone dashboard, control keys, exact origin/host validation, timers, schedules, presets and live health status.
- Document Tailscale HTTPS access, setup, recovery, uninstall and real-device verification limits.
- Add isolated HTTP/DNS/enforcement tests and Linux/macOS CI.

# 2.0.0

Added browser domain/subdomain policies, related service bundles, optional domain expansion,
bulk import/export, presets, pause/resume, filtering, editing, coverage inspection and service health.
Replaced destructive browser policy cleanup with per-value write-ahead backup/restoration.
Added validation, last-good configuration, hosts snapshot, bounded imports and policy-limit checks.
Fixed Windows mutex signatures, surfaced task startup errors, protected uninstall recovery data,
and disallowed privileged tasks pointing at source-mode Python projects.
Added automated domain/registry regression tests, GUI smoke test and Windows build workflow.

Known verification limit: Windows-native enforcement and browser behavior need the acceptance checklist.
