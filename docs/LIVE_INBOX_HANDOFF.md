# Live Inbox Pilot Handoff

## Paste into a fresh Codex task

```text
Continue the ATLAS project from C:\Development\ATLAS on branch main.

First read, in order:
1. C:\Development\ATLAS\AGENTS.md
2. C:\Development\ATLAS\CODEX_CONTEXT.md
3. C:\Development\ATLAS\docs\ATLAS_PROJECT_MEMORY.md
4. C:\Development\ATLAS\docs\ATLAS_CODEX_HANDOFF.md
5. C:\Development\ATLAS\docs\INTAKE_JOBS.md
6. C:\Development\ATLAS\docs\LIVE_INBOX_HANDOFF.md

Goal: perform the first bounded live Archive Intake reliability pilot against
J:\Inbox using Beacon 0.9.0.

Safety and scope:
- Use one primary agent; do not spawn subagents unless I explicitly ask.
- Stay local. Do not upload media or invoke external inference.
- Confirm Git main is clean and contains merge commit 7166de8.
- Read-only checks may inspect J:\Inbox, but do not move, rename, edit, delete,
  deduplicate, or reorganize any Inbox file.
- Do not leave the intake item limit blank. The first live job is exactly 25
  files.
- Intake is catalog-only. Do not begin AI analysis or managed moves.
- The verified pre-schema-7 database backup is
  C:\ProgramData\ATLAS\Beacon\backups\beacon-pre-schema7-20260723T192234.940229Z.db
- Stop on drive instability, unexpected reparse traversal, changed-source
  errors, database-integrity failure, or evidence that an original changed.

Pilot procedure:
1. Recheck the current live database and J:\Inbox structural state without
   hashing the full Inbox.
2. Launch the exact Beacon 0.9.0 release from:
   C:\Development\ATLAS\dist\releases\0.9.0\ATLAS Beacon\ATLAS Beacon.exe
3. Confirm the live database migrates cleanly from schema 6 to schema 7.
4. Create one J:\Inbox intake snapshot with a 25-file limit. Record its job ID,
   snapshot SHA-256, item count, byte count, and chosen paths.
5. Start the job, allow several files to finish, request Cancel, and verify it
   stops between files with completed and pending counts preserved.
6. Resume that same job and let it finish. Do not create a replacement job.
7. Verify all 25 items are complete, no completed item was repeated, catalog
   asset/location deltas reconcile, source paths still exist, catalog SHA-256
   values match the current source bytes, and SQLite integrity/foreign keys are
   healthy.
8. Capture the native completed state and write a concise evidence report.
9. Stop and report. Do not expand beyond 25 files and do not begin contextual
   AI analysis until I approve the pilot.

Keep updates concise because account usage is limited.
```

## Expected starting state

- Repository: `C:\Development\ATLAS`
- Branch: `main`
- Beacon feature commit: `72e27ea`
- Merge commit: `7166de8`
- Release: Beacon 0.9.0
- Live catalog before first 0.9.0 launch: healthy schema 6
- Prior post-move Inbox inventory: 7,092 files, 744,696,445,768 bytes
- No live schema-7 intake job exists yet

The 25 paths selected by deterministic lexical order are a reliability pilot,
not a representative media sample. After the lifecycle proof is accepted,
create separate bounded cohorts across top-level collections and formats before
full-corpus processing.
