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
- Added schema version 3 with verified, hashed thumbnail-derivative lineage.
- Added idempotent FFmpeg thumbnails for images, video frames, and audio
  waveforms without editing source files.
- Added native Finder-style Space previews with image fit, audio/video playback
  controls, and safe metadata fallback for other file types.
- Added Qt Multimedia to the native bundle while explicitly excluding browser,
  3D, charting, PDF, and virtual-keyboard capabilities.
- Verified Beacon 0.4.0 source and frozen previews against the isolated
  UseTest-01 copies while retaining byte-identical ATLAS sources.
- Corrected the standalone-launch catalog mismatch exposed after 0.4.0:
  verified media had remained in the isolated use-test database while the
  double-clickable app correctly opened its separate live database.
- Backed up the live catalog, cataloged the approved NVMe copies into it, and
  verified the exact no-argument packaged launch shows all expected assets.
- Added explicit Live/Isolated/Custom catalog labels and lightweight automatic
  refresh when the SQLite database or WAL changes.
- Added regression coverage for catalog labeling and externally written catalog
  updates, bringing the suite to 22 tests.
- Added bounded, read-only plain-text previews with common UTF and Windows
  encoding detection, binary rejection, and a 512 KB display cap.
- Promoted Space to an application-level preview shortcut, prevented mouse
  clicks from trapping focus on action buttons, and added a real Qt regression
  test for the focused-button case.
- Added a larger selected-asset thumbnail to the detail header with a branded
  extension tile for files without media derivatives.
- Verified Beacon 0.5.0 source and packaged behavior against the five-asset
  live catalog, bringing the complete suite to 27 tests.
