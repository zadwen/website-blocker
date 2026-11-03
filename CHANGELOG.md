## 3.0.1 — Blocking reliability

- Preserve existing Windows protection when both the primary settings and recovery backup are missing or invalid; report a health error until valid settings are restored.
- Reject URL fragments, credentials, wildcards, control characters, and other non-hostname syntax at the hosts-file write boundary. URL and international-domain input remain supported through normal rule entry.
- Retry failed macOS DNS cache refreshes even when managed files already match the desired state.
- Reject duplicate macOS rule IDs and malformed Windows configuration objects.
- Restore the documented Windows EXE build workflow, including tests before packaging and a downloadable Actions artifact.
- Add six regression tests covering validation, recovery, and DNS-refresh retries.

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
