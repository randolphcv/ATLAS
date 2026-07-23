# Changelog

## Unreleased

- Established the canonical NVMe repository.
- Added the standard-library Beacon read-only catalog prototype.
- Added synthetic acceptance tests and operational documentation.
- Added foreground synthetic-inbox watching and retained operational logs.
- Verified generated WAV/MP4 metadata through FFprobe.
- Verified duplicate, restart, partial-copy, unavailable-path, and corrupt-media behavior.
- Added schema version 2 with a visible audit-event ledger.
- Added loopback-only FastAPI health, catalog, event, and backup APIs.
- Added verified online SQLite backups with atomic placement and SHA-256.
- Added the branded ATLAS Beacon archive dashboard.
- Added a reproducible PyInstaller Windows application bundle.
- Replaced the primary browser dashboard with a native Qt Quick desktop client.
- Added native archive navigation, master-detail inspection, and system views.
- Moved verified backup execution off the UI thread.
- Removed browser launch, network listeners, and web dependencies from the
  packaged desktop runtime while retaining the API as an optional adapter.
- Added explicit JPEG/PNG/TIFF/WebP image probing after the first real use test.
- Preserved still-image identity and dimensions without displaying FFprobe's
  synthetic single-frame duration.
