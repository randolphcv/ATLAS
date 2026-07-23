# Native Desktop Verification

Verified on the Windows ATLAS host on 2026-07-23.

## Outcome

Beacon 0.4.1 is a native Qt Quick/QML desktop application. It uses the existing
read-only catalog, repository, audit, health, and verified-backup modules
directly. The desktop process does not open a browser, embed a web view, start
FastAPI, or listen on a network port.

The current client also uses Qt Multimedia for local temporary previews. It
loads verified thumbnail derivatives in Library and opens a selected asset with
Space. Playback stops when the modal preview closes.

## Automated verification

- Python compilation: passed
- Unit and integration tests with real FFprobe and FFmpeg: 22 passed
- Native catalog model, search, detail, and health tests: passed
- Non-blocking verified-backup controller test: passed
- QML window offscreen load test: passed
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

Screenshots:

- [`images/desktop-overview.png`](images/desktop-overview.png)
- [`images/desktop-library.png`](images/desktop-library.png)
- [`images/desktop-system.png`](images/desktop-system.png)
- [`images/desktop-packaged.png`](images/desktop-packaged.png)

## Executable verification

Artifact:

```text
C:\Development\ATLAS\dist\releases\0.4.1\ATLAS Beacon\ATLAS Beacon.exe
```

Package:

```text
C:\Development\ATLAS\dist\ATLAS-Beacon-0.4.1-win64.zip
```

The frozen executable passed smoke-test and screenshot modes against the
schema-3 live database without a `--db` override. Windows file and product
versions are both `0.4.1`.

Executable SHA-256:

```text
914F42EF383B4F1B738986BB0F06FB29AC4241B9D043B8D7A6B5D7CFF352DAA5
```

Package SHA-256:

```text
B0E0F961BD4D3D5CEE22FD7D668D2F1D2E715691BE9F8800010895ED995A0018
```

The one-folder bundle contains 1,748 files and 178,030,027 bytes. Its packaging
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
