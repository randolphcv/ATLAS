# Beacon 0.9.0 Live Inbox Pilot Evidence

Date: 2026-07-23  
Scope: first bounded, catalog-only reliability pilot against `J:\Inbox`

## Outcome

The pilot passed. Beacon created one 25-file snapshot, cataloged 13 files,
honored Cancel between files with 12 files still pending, resumed the same job,
and completed all 25 files without repeating a completed item. No source file
was moved, renamed, edited, deleted, deduplicated, or reorganized. No external
inference, contextual AI analysis, or managed move was started.

Completed native UI capture:
`C:\Users\rando\.codex\visualizations\2026\07\23\019f907e-ab13-7923-9bb5-1fc74d987f8c\beacon_live_inbox_pilot_complete.png`

## Preflight

- Repository: `C:\Development\ATLAS`, clean `main`, HEAD `f993bf7`;
  merge commit `7166de8` is an ancestor of HEAD.
- Executable:
  `C:\Development\ATLAS\dist\releases\0.9.0\ATLAS Beacon\ATLAS Beacon.exe`
- Executable SHA-256:
  `1BC9B4E5376537FC46B0DBC714ED6DC3A50D3E059F74F3800EFFE5C81BE262FB`
- Live database: healthy schema 7, WAL mode, zero foreign-key errors, and zero
  existing intake jobs.
- Verified pre-schema-7 backup:
  `C:\ProgramData\ATLAS\Beacon\backups\beacon-pre-schema7-20260723T192234.940229Z.db`
- Backup SHA-256:
  `F66387248420BB7C3B2B1FF4D7E9A0B5C8CC8EE3358C05921DBD08FEC614CA57`
- Inbox structural inventory: 7,092 regular files, 744,696,445,768 bytes,
  zero detected reparse points. This check did not hash the full Inbox.
- Baseline database counts: 5 assets, 7 locations, 39 system events.

## Job and lifecycle

- Job ID: `7c3b4fdf-af1b-4578-a8b3-d7e4164463c2`
- Source root: `J:\Inbox`
- Mode: `catalog_only`
- Item limit: 25
- Snapshot SHA-256:
  `c1b9d0f349235f07dee9fe29f00ce7b8f408e2239f4e1bee65288ca6bc86fb17`
- Snapshot totals: 25 files, 10,436,261,715 bytes
- Created: `2026-07-23T19:44:29.873250+00:00`
- Started: `2026-07-23T19:44:43.571906+00:00`
- Cancel boundary: 13 complete, 12 pending, 0 running, 0 failed; completed
  attempts were 1 and pending attempts were 0.
- Resumed the same job; no replacement job was created.
- Completed: `2026-07-23T19:46:40.384733+00:00`
- Final state: 25 complete, 0 pending, 0 running, 0 failed; every item has
  exactly one attempt and a unique asset ID.

## Selected paths

1. `.DS_Store`
2. `Anna King/.DS_Store`
3. `Anna King/2021 Naked Retreat/.DS_Store`
4. `Anna King/2021 Naked Retreat/AUDIO/Alisha Yoga Class.wav`
5. `Anna King/2021 Naked Retreat/AUDIO/Anna Yoga Intro.wav`
6. `Anna King/2021 Naked Retreat/AUDIO/Audio_06_27_2021_16_48_21.wav`
7. `Anna King/2021 Naked Retreat/AUDIO/Audio_06_27_2021_16_48_47.wav`
8. `Anna King/2021 Naked Retreat/AUDIO/Audio_06_27_2021_17_00_13.wav`
9. `Anna King/2021 Naked Retreat/AUDIO/Beth 2.wav`
10. `Anna King/2021 Naked Retreat/AUDIO/Beth.wav`
11. `Anna King/2021 Naked Retreat/AUDIO/Evening Ritual.wav`
12. `Anna King/2021 Naked Retreat/AUDIO/Final Sesh.wav`
13. `Anna King/2021 Naked Retreat/AUDIO/Questions.wav`
14. `Anna King/2021 Naked Retreat/AUDIO/Tapping V2.wav`
15. `Anna King/2021 Naked Retreat/AUDIO/Tapping.mp3`
16. `Anna King/2021 Naked Retreat/DAY 1/.DS_Store`
17. `Anna King/2021 Naked Retreat/DAY 1/C100/MVI_0314.MP4`
18. `Anna King/2021 Naked Retreat/DAY 1/C100/MVI_0315.MP4`
19. `Anna King/2021 Naked Retreat/DAY 1/C100/MVI_0316.MP4`
20. `Anna King/2021 Naked Retreat/DAY 1/C100/MVI_0317.MP4`
21. `Anna King/2021 Naked Retreat/DAY 1/C100/MVI_0318.MP4`
22. `Anna King/2021 Naked Retreat/DAY 1/C100/MVI_0319.MP4`
23. `Anna King/2021 Naked Retreat/DAY 1/C100/MVI_0320.MP4`
24. `Anna King/2021 Naked Retreat/DAY 1/C100/MVI_0321.MP4`
25. `Anna King/2021 Naked Retreat/DAY 1/C100/MVI_0322.MP4`

## Reconciliation

- Final database counts: 30 assets, 32 locations, 89 system events.
- Deltas: +25 assets, +25 locations, +50 system events.
- The event delta reconciles to 25 catalog completions, 21 local thumbnail
  completions, and four intake lifecycle events: queued, running, cancelled,
  and complete.
- All 25 source paths still exist.
- Current size and nanosecond modification time match each snapshot item.
- Current SHA-256 values for all 25 source files match their catalog asset
  hashes.
- Each intake item resolves to its expected source location row.
- SQLite `integrity_check`: `ok`.
- SQLite `foreign_key_check`: zero errors.
- Final live database: healthy schema 7, WAL mode.

## Gate

Stop here for approval. Do not expand beyond this 25-file job and do not begin
contextual AI analysis or managed moves.
