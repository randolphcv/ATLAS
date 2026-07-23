# Native Desktop Verification

Verified on the Windows ATLAS host on 2026-07-23.

## Outcome

Beacon 0.5.0 is a native Qt Quick/QML desktop application. It uses the existing
read-only catalog, repository, audit, health, and verified-backup modules
directly. The desktop process does not open a browser, embed a web view, start
FastAPI, or listen on a network port.

The current client also uses Qt Multimedia for local temporary previews. It
loads verified thumbnail derivatives in Library and opens a selected asset with
Space. Plain-text files render in a bounded read-only viewer; binary formats
retain the metadata-only fallback. Playback stops when the modal preview
closes.

## Automated verification

- Python compilation: passed
- Unit and integration tests with real FFprobe and FFmpeg: 27 passed
- Native catalog model, search, detail, and health tests: passed
- Non-blocking verified-backup controller test: passed
- QML window offscreen load test: passed
- Application-level Space shortcut with a focused action button: passed
- Dependency check: passed

## Rendered verification

The actual Qt window was rendered against the synthetic acceptance catalog.
The following states were visually reviewed:

- overview metrics, recent assets, audit signals, and local-only state;
- master-detail asset library with video/audio technical facts;
- system health, explicit backup action, and recovery-point history;
- packaged-executable asset library.
- image fit-to-window preview;
- audio waveform, playback, and scrubber;
- video playback and scrubber.
- exact no-argument packaged launch against the labeled Live catalog;
- automatic refresh after an external catalog transaction.
- larger image and text-fallback tiles in the selected-asset header;
- selectable read-only text preview with encoding and truncation status.

Screenshots:

- [`images/desktop-overview.png`](images/desktop-overview.png)
- [`images/desktop-library.png`](images/desktop-library.png)
- [`images/desktop-system.png`](images/desktop-system.png)
- [`images/desktop-packaged.png`](images/desktop-packaged.png)

## Executable verification

Artifact:

```text
C:\Development\ATLAS\dist\releases\0.5.0\ATLAS Beacon\ATLAS Beacon.exe
```

Package:

```text
C:\Development\ATLAS\dist\ATLAS-Beacon-0.5.0-win64.zip
```

The frozen executable passed smoke-test and screenshot modes against the
schema-3 live database without a `--db` override. Windows file and product
versions are both `0.5.0`.

Executable SHA-256:

```text
8FE700C5020B0C6C3D4B0FDD7546F3561E222A7BEB990376284034ACDFDF1F8E
```

Package SHA-256:

```text
74E009141DC001BB2A73518AC3824377B1600DB5A261028E8526D443021F59D9
```

The one-folder bundle contains 1,748 files and 178,039,289 bytes. Its packaging
filter excludes FastAPI, Uvicorn, Pydantic, Qt WebEngine, Qt Quick 3D, charting,
PDF, and virtual-keyboard capabilities.

This private development build is not Authenticode-signed, so Windows may
identify the publisher as unknown.

## Safety boundary

- No production path was observed or indexed
- No cloud call, service, scheduled task, or watcher was added
- No original file was moved, renamed, edited, or deleted
- Backup remains the only state-changing desktop action
- Preview remains read-only; thumbnail writes stay in the runtime derivative tree
- Backup requires explicit confirmation and is integrity-checked before success
- Restore and backup deletion remain absent
