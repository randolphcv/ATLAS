# Phase 1 Verification

Verified on the Windows ATLAS host on 2026-07-22.

## Scope

This verification used generated fixtures under:

```text
C:\ProgramData\ATLAS\Beacon\acceptance-20260722-231828\
```

No path on `J:\` was watched, indexed, moved, renamed, edited, or deleted.

## Toolchain

- Python 3.12.10
- Git 2.55.0.windows.3
- FFmpeg and FFprobe 8.1.2
- Python standard library only for Beacon runtime code

## Automated results

- Python compilation: passed
- Unit/acceptance tests: 10 passed
- Real FFprobe WAV extraction: passed
- Corrupt-media probe handling: passed
- FFprobe timeout handling: passed
- File-change-during-hash rejection: passed
- Unavailable-inbox behavior: passed
- Per-file scan-error isolation: passed
- Foreground watcher detection: passed

## End-to-end results

The acceptance inbox contained:

- two text files with identical bytes;
- one generated PCM WAV;
- one generated H.264 MP4;
- one intentionally corrupt WAV.

Two independent watcher processes cataloged the same inbox. Both exited 0.
The final database contained four content assets and five observed locations.
The duplicate text files shared one asset identity and retained two locations.
SQLite `PRAGMA integrity_check` returned `ok`.

FFprobe recorded:

- `h264` for the generated MP4;
- `pcm_s16le` for the generated WAV;
- an actionable probe error for the corrupt WAV.

Scanning a missing inbox exited 1 and retained an error log without crashing.
The operational log contained asset IDs and paths and matched no common secret
patterns. SHA-256 hashes for every source fixture matched before and after both
watcher runs.

## Runtime evidence

```text
Database:
C:\ProgramData\ATLAS\Beacon\acceptance-20260722-231828\beacon.db

Log:
C:\ProgramData\ATLAS\Beacon\acceptance-20260722-231828\beacon.log
```

These are synthetic development artifacts, not backups or production state.

## Deferred by design

- No production or personal media has been indexed.
- No Windows service or scheduled task has been created.
- No cloud or external AI service is used.
- Production stability thresholds remain unapproved and untuned.
- Database backup/restore policy and independent archive protection remain open.
