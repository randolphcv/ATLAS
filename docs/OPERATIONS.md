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
C:\Development\ATLAS\dist\releases\0.9.0\ATLAS Beacon\ATLAS Beacon.exe
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
externally. Candidate organization paths remain suggestions until an editable
organization directory and managed-move policy authorize a separate operation.

The Overview includes **Beacon Desk**. Questions, approval requests, blockers,
clarifications, and human-started requests persist in the live SQLite catalog.
Replying changes an open thread to `queued_for_beacon`; it does not execute a
scan, upload, rename, move, delete, or metadata promotion. **Resolve** is a
separate explicit action.

Beacon Desk is currently a durable handoff surface, not a continuously running
AI worker. The UI says `SAVED LOCALLY`; queued messages are reviewed when a
Beacon analysis session is deliberately run. The active `J:\Inbox` transfer is
not inspected by opening the Desk.

## Archive intake

The Overview includes **Archive Intake** for explicit recursive catalog jobs.
**New intake** defaults to `J:\Inbox` and a 25-file representative scope.
Creating a snapshot does not start it. Review the displayed root, file count,
byte count, and snapshot prefix, then choose **Start**.

During a run, progress and the current path are written to SQLite. **Cancel**
stops between files. **Resume** continues pending items without repeating
completed ones. **Retry failures** resets only failed items. Closing the app
pauses at the same safe boundary; a hard interruption is recovered as Paused at
the next launch.

Leave the maximum-files field blank only when a full recursive snapshot is
intended. Intake is catalog-only and does not invoke managed moves.

## Editable metadata and managed moves

Library exposes revisioned contextual fields for title, description, category,
tags, people, date, place, client, project, rights, notes, and approved
organization directory. These fields are searchable and editable; saving never
writes into the media file. SHA-256, byte size, codec, duration, dimensions, and
other verified facts remain locked evidence.

**Move file** is enabled after an approved organization directory is recorded.
The operation:

1. requires the exact selected asset and observed source path;
2. checks the recorded managed-moves policy;
3. re-hashes the source against the catalog;
4. permits only `J:\Library`, `J:\Assets`, or `J:\Projects`;
5. rejects reparse-point traversal and silent overwrite/duplicate merging;
6. performs a same-volume move and verifies the destination hash;
7. updates the location and audit records only after verification;
8. attempts rollback if a post-move check fails.

The original filename is preserved. Other duplicate locations are never
silently removed.

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
