# Operations

## Safety mode

The catalog remains synthetic and read-only. Do not point the CLI or desktop app
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

## Desktop application

Run from source:

```powershell
.\.venv\Scripts\python.exe -m beacon.desktop
```

Or double-click:

```text
C:\Development\ATLAS\dist\ATLAS Beacon\ATLAS Beacon.exe
```

The desktop app has its own Windows window. It does not open a browser, start a
server, or listen on a port. Closing the window stops it.

The System view can create a verified database backup after explicit
confirmation. Restore and backup deletion are intentionally absent.

## Optional API

Run the development API separately when a local integration needs it:

```powershell
.\.venv\Scripts\python.exe -m beacon.app
```

It binds only to `127.0.0.1:8765`. If the port is occupied, the adapter exits
with an actionable message instead of selecting a different network endpoint.
It does not open a browser unless `--browser` is explicitly supplied.

## Failure behavior

Directory scans log per-file failures and continue. A file that changes during
hashing is rejected and may be retried later. An unavailable inbox returns a
nonzero CLI result with an actionable error. Missing FFprobe is non-fatal;
corrupt media is cataloged with its probe error so the original remains
discoverable and retryable.
