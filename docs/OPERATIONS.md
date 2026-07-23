# Operations

## Safety mode

The catalog remains synthetic and read-only. Do not point the CLI or dashboard
at `J:\Inbox` or another real-media directory without an explicitly approved
pilot scope.

## Runtime layout

```text
C:\ProgramData\ATLAS\Beacon\
├── beacon.db
├── backups\
├── logs\
├── cache\
├── temp\
└── sandbox\inbox\
```

Tests use isolated temporary directories. `BEACON_FFPROBE` may identify an
explicit FFprobe executable when it is not visible on the process `PATH`.

## Catalog watcher

Run `beacon watch` as a foreground development process. `--once` performs one
polling cycle for diagnostics. No scheduled task or Windows service is created.

## Dashboard

Run from source:

```powershell
.\.venv\Scripts\python.exe -m beacon.app
```

Or double-click:

```text
C:\Development\ATLAS\dist\ATLAS Beacon\ATLAS Beacon.exe
```

The app binds only to `127.0.0.1:8765`. Keep its console window open; closing it
stops the local server. If the port is already occupied, Beacon exits with an
actionable message instead of silently selecting a different network endpoint.

The dashboard can create a verified database backup after explicit
confirmation. Restore and backup deletion are intentionally absent.

## Failure behavior

Directory scans log per-file failures and continue. A file that changes during
hashing is rejected and may be retried later. An unavailable inbox returns a
nonzero CLI result with an actionable error. Missing FFprobe is non-fatal;
corrupt media is cataloged with its probe error so the original remains
discoverable and retryable.
