# Native Desktop Verification

Verified on the Windows ATLAS host on 2026-07-23.

## Outcome

Beacon 0.3.0 is a native Qt Quick/QML desktop application. It uses the existing
read-only catalog, repository, audit, health, and verified-backup modules
directly. The desktop process does not open a browser, embed a web view, start
FastAPI, or listen on a network port.

## Automated verification

- Python compilation: passed
- Unit and integration tests with real FFprobe: 17 passed
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

Screenshots:

- [`images/desktop-overview.png`](images/desktop-overview.png)
- [`images/desktop-library.png`](images/desktop-library.png)
- [`images/desktop-system.png`](images/desktop-system.png)
- [`images/desktop-packaged.png`](images/desktop-packaged.png)

## Executable verification

Artifact:

```text
C:\Development\ATLAS\dist\ATLAS Beacon\ATLAS Beacon.exe
```

Package:

```text
C:\Development\ATLAS\dist\ATLAS-Beacon-0.3.0-win64.zip
```

The frozen executable passed smoke-test and screenshot modes against the
synthetic schema-2 acceptance database. Windows file and product versions are
both `0.3.0`.

Executable SHA-256:

```text
E061A2EDE6B69BF36CD0163A23BFDDC0C3F3EBFE978124E306F690064607706D
```

Package SHA-256:

```text
3B37799CD081073A6980C6CCEA8B211981C5B46241D74E62EA1013598E63A430
```

The one-folder bundle contains 1,967 files and 164,355,615 bytes. It contains no
FastAPI, Uvicorn, Pydantic, or Qt WebEngine files. No process was listening on
Beacon's prior development ports after the packaged checks.

This private development build is not Authenticode-signed, so Windows may
identify the publisher as unknown.

## Safety boundary

- No production path was observed or indexed
- No cloud call, service, scheduled task, or watcher was added
- No original file was moved, renamed, edited, or deleted
- Backup remains the only state-changing desktop action
- Backup requires explicit confirmation and is integrity-checked before success
- Restore and backup deletion remain absent
