# 2.0.0

Added browser domain/subdomain policies, related service bundles, optional domain expansion,
bulk import/export, presets, pause/resume, filtering, editing, coverage inspection and service health.
Replaced destructive browser policy cleanup with per-value write-ahead backup/restoration.
Added validation, last-good configuration, hosts snapshot, bounded imports and policy-limit checks.
Fixed Windows mutex signatures, surfaced task startup errors, protected uninstall recovery data,
and disallowed privileged tasks pointing at source-mode Python projects.
Added automated domain/registry regression tests, GUI smoke test and Windows build workflow.

Known verification limit: Windows-native enforcement and browser behavior need the acceptance checklist.
