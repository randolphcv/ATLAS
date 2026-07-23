# Operations

## Safety mode

Phase 1 is synthetic and read-only. Do not point the CLI at `J:\Inbox` or any
other real-media directory.

## Runtime layout

```text
C:\ProgramData\ATLAS\Beacon\
├── beacon.db
├── logs\
├── cache\
├── temp\
└── sandbox\inbox\
```

The runtime layout is not created automatically during tests. Tests use isolated
temporary directories.

Set `BEACON_FFPROBE` to an explicit executable path when FFprobe is not visible
on the process `PATH`. Use `--log-file` before the CLI subcommand to retain an
operational log.

Run `beacon watch` as a foreground development process. `--once` performs one
polling cycle for diagnostics. No scheduled task or Windows service is created
in Phase 1.

## Failure behavior

Directory scans log per-file failures and continue. A file that changes during
hashing is rejected and may be retried later. An unavailable inbox returns a
nonzero CLI result with an actionable error. Missing `ffprobe` is non-fatal;
corrupt media is cataloged with its probe error so the original remains
discoverable and retryable.
