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

## Failure behavior

Directory scans log per-file failures and continue. A file that changes during
hashing is rejected and may be retried later. Missing `ffprobe` is non-fatal.

