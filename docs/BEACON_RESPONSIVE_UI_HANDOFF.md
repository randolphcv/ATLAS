# Beacon Responsive UI and Persistent Conversation Handoff

Updated: 2026-07-24

## Fresh-thread objective

Continue ATLAS from `C:\Development\ATLAS` on branch
`ops/overnight-250-tranche`. Use one primary agent. First verify that the live
RAW analysis job described below has finished. Do not migrate the live database
or interrupt that job while it is running.

Build the next small Beacon interface pass around two product goals:

1. add truthful, durable analysis-stage status beneath the catalog-analysis
   progress bar;
2. design and begin the lean shell-level Beacon conversation interface that
   persists while the user navigates among pages.

Stay local. Do not upload catalog media or introduce a cloud requirement.

## Current verified state

- Branch: `ops/overnight-250-tranche`
- Working tree was clean when this handoff was written.
- Current packaged release: Beacon 0.15.4
- Latest commits:
  - `c6480f3` — keep catalog controls inside operation card
  - `52b1b30` — make catalog analysis failures resumable
  - `b238d9e` — add RAW reanalysis scope and Finder metadata cleanup
- Release executable:
  `C:\Development\ATLAS\dist\releases\0.15.4\ATLAS Beacon\ATLAS Beacon.exe`
- Release directory size: 417,563,170 bytes
- ZIP size: 160,903,695 bytes
- Live database:
  `C:\ProgramData\ATLAS\Beacon\beacon.db`
- Live database was healthy at schema 12, WAL mode, with SQLite integrity
  `ok` and zero foreign-key errors.

### Live RAW job at handoff

- Job ID: `d1e28b5c-e63c-4c0b-83f6-e1318bcd1f16`
- Model: `qwen2.5vl:7b`, local Ollama loopback endpoint
- Scope: exactly 180 RAW assets
- Scope SHA-256:
  `21c33ad6af3723f4e780721add04a7f56b580ee19b1ac9cc2ba9b1f40bf6a9d2`
- State at 2026-07-24 13:10 local time:
  168 complete, 1 failed, 10 pending, 1 running
- The runner is deliberately non-fail-fast and has already proved it continues
  after an individual malformed-model-response failure.
- Runner PID file:
  `C:\ProgramData\ATLAS\Beacon\raw-reanalysis.pid`
- Log:
  `C:\ProgramData\ATLAS\Beacon\raw-reanalysis-d1e28b5c-e63c-4c0b-83f6-e1318bcd1f16.log`
- Do not create a replacement job. After the current pass finishes, use
  Beacon 0.15.4’s **Retry analysis failures** control or
  `retry_local_analysis_failures` to retry only failed items in this job.

## Immediate acceptance criteria: live status line

Add a compact line immediately beneath the analysis progress bar. It must
report the real current pipeline stage and current filename, not simulated
“thinking.” Representative labels:

- `PREPARING RAW PREVIEW · IMG_4821.CR3`
- `VISUALLY OBSERVING · IMG_4821.CR3`
- `TRANSCRIBING AUDIO · interview_take_03.wav`
- `ANALYZING MUSIC · cue_07.flac`
- `WRITING METADATA · C0008.MP4`
- `MOVING TO ARCHIVE · C0008.MP4`

Requirements:

- persist stage and display-safe filename in the durable analysis job state;
- survive refreshes, app restarts, cancellation, and recovery;
- update only at meaningful pipeline boundaries;
- clear or show an accurate terminal state when no item is active;
- never expose model chain-of-thought or fabricate internal activity;
- use negligible polling and rendering overhead;
- retain the existing responsive, lightweight feel;
- add the schema migration, recovery behavior, tests, package build, and
  visual validation only after the live job is terminal.

The smallest suitable schema is likely nullable `current_stage` plus a
timestamp on `local_analysis_jobs`; `current_asset_id` already exists. Prefer
deriving the filename from the durable item/source record rather than storing
duplicated path data.

## Persistent Beacon conversation direction

Connor wants Beacon to feel continuously attentive and responsive without
becoming a heavyweight always-running application. The conversation surface
should belong to the application shell, not to any individual page.

Recommended interaction model:

- a compact persistent composer/dock available from every page;
- one active conversation continues while Overview, Library, Reports, and
  System content changes behind it;
- expandable conversation history, with a collapsed state that consumes very
  little space;
- navigation must not destroy draft text, selected thread, scroll position, or
  response state;
- Beacon may receive explicit, inspectable page context such as the selected
  asset, report, or operation, but changing pages must not silently rewrite the
  conversation;
- show local model/runtime state and active work honestly;
- preserve the existing schema-5 Beacon Desk threads/messages as the durable
  conversation authority instead of inventing a second chat database;
- keep model integration behind a replaceable adapter. Conversation,
  analysis, and command execution are related but distinct capabilities;
- conversational requests that mutate files or operations must pass through
  explicit typed commands and existing policy/audit boundaries, never free-form
  model side effects.

Start with architecture and a thin interactive shell. Do not attempt a full
autonomous Beacon agent, semantic-report system, and command router in one
pass.

## Navigation roadmap

- Operations will eventually merge into System.
- Navigation position 03 will become **Reports**.
- Reports will provide multiple data views for understanding catalog contents.
- Reports will include the persistent Beacon composer so users can converse
  with Beacon while inspecting analyzed data.
- The persistent composer is a shell feature, so Reports may emphasize it but
  must not own or duplicate it.

## Performance and footprint rules

- Beacon must remain fast to open, light while idle, and responsive during
  background analysis.
- Do not preload every report, asset record, transcript, or conversation.
  Query and paginate on demand.
- Avoid embedding additional model weights in the Beacon application bundle.
  Ollama models and specialized runtimes remain separately managed local
  dependencies.
- Avoid a browser engine or heavyweight web runtime for chat.
- Reuse Qt/QML, SQLite, the existing refresh/signaling paths, and Beacon Desk.
- Prefer event-driven updates or the existing low-cost database signature
  refresh over aggressive polling.
- Track packaged application size independently from optional local model,
  derivative, transcript, and cache storage.
- Treat unexplained startup, idle CPU/RAM, package-size, or database-query
  regressions as release blockers.

## Suggested sequence

1. Read `AGENTS.md`, `CODEX_CONTEXT.md`, project memory, this handoff, and the
   relevant local-analysis/desktop/QML code.
2. Verify Git, Beacon version, live job state, runner, database integrity, and
   foreign keys.
3. If the live job is still running, stop before schema or runtime changes.
4. Once terminal, retry only its failures and verify all possible items finish.
5. Back up the healthy live database before the next schema migration.
6. Implement durable analysis-stage state and the compact status line.
7. Test cancel/recovery/refresh and visually validate the native interface.
8. Write a concise shell-level persistent-conversation architecture proposal,
   then implement only the agreed thin first slice.
9. Package a new release, update durable documentation, and keep the branch
   recoverable before considering a merge to `main`.

## Fresh-thread starter

```text
Continue ATLAS from C:\Development\ATLAS on branch
ops/overnight-250-tranche. Use one primary agent.

Read, in order:
1. AGENTS.md
2. CODEX_CONTEXT.md
3. docs\ATLAS_PROJECT_MEMORY.md
4. docs\ATLAS_CODEX_HANDOFF.md
5. docs\BEACON_RESPONSIVE_UI_HANDOFF.md

First verify whether RAW analysis job
d1e28b5c-e63c-4c0b-83f6-e1318bcd1f16 has finished and confirm SQLite
integrity/foreign keys. Do not create a replacement job. If it is still
running, do not migrate or interrupt the live database.

Once it is terminal, complete the failed-item retry in the same job, then
implement the truthful durable analysis-stage status line described in the
handoff. After that, develop the lean shell-level persistent Beacon
conversation interface direction without adding cloud requirements or a
heavyweight runtime.
```
