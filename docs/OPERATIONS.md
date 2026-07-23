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
├── derivatives\thumbnails\
├── logs\
├── cache\
├── temp\
└── sandbox\inbox\
```

Tests use isolated temporary directories. `BEACON_FFPROBE` may identify an
explicit FFprobe executable when it is not visible on the process `PATH`.
`BEACON_FFMPEG` does the same for thumbnail generation.

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
C:\Development\ATLAS\dist\releases\0.6.0\ATLAS Beacon\ATLAS Beacon.exe
```

The desktop app has its own Windows window. It does not open a browser, start a
server, or listen on a port. Closing the window stops it.

A normal double-click opens the **Live catalog** at
`C:\ProgramData\ATLAS\Beacon\beacon.db`. An explicitly supplied `--db` path is
visibly labeled **Isolated use test** or **Custom catalog**. Beacon checks for
database/WAL changes every five seconds and refreshes only after a change.

In Library, select an asset and press Space or click **Preview**. Image, audio,
and video previews stay inside Beacon. Press Space or Escape to close; playback
stops immediately. Text files are shown as bounded, read-only plain text inside
Beacon. Binary and unsupported formats display metadata instead of being opened
in an editor.

Beacon analysis appears separately from technical facts and is visibly labeled
`CANDIDATE`. The card records confidence and whether inference ran locally or
externally. Organization paths are suggestions only; Beacon 0.6.0 has no UI or
worker that moves an original.

An explicitly approved analysis manifest can be imported with:

```powershell
.\.venv\Scripts\python.exe -m beacon.cli analysis-import `
  C:\ProgramData\ATLAS\Beacon\analysis-runs\<manifest>.json `
  --db C:\ProgramData\ATLAS\Beacon\beacon.db
```

The complete manifest is rejected if an asset is missing, a source SHA-256 has
changed, required provenance is absent, or external inference lacks a recorded
authorization note. Re-importing the same manifest returns the existing run.

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
discoverable and retryable. Missing FFmpeg skips thumbnail generation; a failed
thumbnail is recorded as an operation failure without invalidating the cataloged
asset.
