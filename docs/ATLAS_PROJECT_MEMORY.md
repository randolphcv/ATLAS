# ATLAS — Project Memory and Decision Ledger

Updated: 2026-08-03
Status: portable cross-machine handoff; verify live Windows state before treating recorded runtime details as current

Use this file for durable, low-noise context. Do not store raw logs, secrets, personal media content, full transcripts, or speculative brainstorming here.

## Current Verified/Reported Baseline

### Beacon 0.22.4 analysis and placement failure repair

- Beacon 0.22.4 is live from
  `C:\Development\ATLAS\dist\releases\0.22.4\ATLAS Beacon\ATLAS Beacon.exe`.
  SHA-256:
  `756a94858f54fee2923cd557bed46bd50dd3da1bba76edbd0936d2fb3ad3a938`.
- Total analysis job `37d94efb-26bb-4701-8efe-782ae9687835` is terminal
  `complete`: 2,896 publishable results, one excluded zero-byte file, zero
  failures, and zero pending items. The empty asset remains cataloged and
  searchable; Qwen was not called during its successful retry.
- Placement errors no longer abort result publication or metadata finalization.
  They create durable Beacon Desk blockers and are isolated by destination for
  the remainder of the finalization pass.
- Managed moves now record directory-creation failures immediately, preflight
  destination directories before expensive source checksum reads, and recover
  interrupted `planned` records without re-reading multi-gigabyte sources.
  The normal move attempt still verifies the full source checksum before its
  atomic rename.
- The verified external cause is StableBit DrivePool mode
  `PoolModeNoCreateDirectories` on `J:`. The volume is online, healthy, and not
  read-only; ACLs grant the interactive account full control. StableBit's
  documentation says this new-folder restriction occurs when its trial/license
  is inactive. Connor must confirm/activate DrivePool in its UI; do not bypass
  the pool by touching underlying pool-part folders.
- This run completed 291 checksum-verified placements into existing Projects
  destinations. Another 2,605 analyzed assets remain cataloged in Inbox. The
  final pass recorded 31 placement failures, deferred 2,574 repeated attempts
  under those blocked destinations, and created 31 durable blockers.
- Pre-repair backup:
  `C:\ProgramData\ATLAS\Beacon\backups\beacon-20260803T195436.918349Z.db`;
  SHA-256
  `8b73b1c80e6f9b0b292a96ee43cbb2cd8b135f47e73f1a51106856112fe6be9a`;
  integrity `ok`.
- Schema 16 integrity is `ok` with zero foreign-key violations. All 123 tests
  pass; two opt-in real-FFprobe tests are skipped when `BEACON_FFPROBE` is not
  supplied. Packaged smoke exits 0 and the capability audit reports zero
  blocked files.
- Release ZIP:
  `C:\Development\ATLAS\dist\ATLAS-Beacon-0.22.4-win64.zip`; SHA-256
  `d9f60fede7f59933e68cd74388d92c56374b87fb50b48f7e6b642c4069f65b5e`.

### Next phase

- Analysis job `c687374f-97c0-4147-8a73-ce9d81623a22` is the current live
  production job. It was still `running` with 128 publishable items complete,
  92 pending, one running, and zero failures when the 0.22.0 candidate was
  packaged. Do not stop Beacon or activate the candidate until this job is
  terminal; re-check durable state rather than relying on this progress count.
- Intake job `43bc6778-69e1-4432-a937-bd367acc0a7e` completed all 157
  snapshotted items with no failures. Two newer intake jobs also completed;
  the latest, `38fc99f1-cc62-41ef-929c-a89b3c1d11c6`, completed 500/500.
- The latest analysis job,
  `ea673da9-6ed6-4e18-a83a-8b4cc9df2e37`, is terminal `complete` with 488
  publishable results, two excluded project files, and zero failures.
- The Ultron/Jarvis Markdown bridge is established. Ultron atomically owns
  `J:\ULTRON_CONTEXT.md`; Jarvis atomically owns
  `J:\JARVIS_CONTEXT.md`. Ultron read and acknowledged
  `JARVIS-20260726-001` without editing Jarvis's file.
- The public GitHub repository is live at
  `https://github.com/randolphcv/ATLAS` with default branch `main`. Connor
  explicitly authorized publishing the full existing history after the path
  exposure audit. Local `main` tracks `origin/main`; do not rewrite the
  published history.
- GitHub CLI 2.96.0 is authenticated as `randolphcv`, `.gitignore` is
  hardened, and the tracked-history audit found no detected secrets, runtime
  databases, executables, model files, archives, or personal-media binaries.
- All 119 tests pass, including real-FFprobe acceptance.
- Run representative live Beacon query testing.
- The canonical starting prompt is
  `docs\NEXT_PHASE_HANDOFF_PROMPT.md`.

### Beacon 0.22.0 scalable one-shot scopes

- Intake and Analysis now share an explicit **Granular / General / Total**
  hierarchy. Total is the visible default for both workflows.
- Total Intake creates an uncapped durable click-time snapshot of every
  regular file currently below the configured approved Inbox root. General
  retains an approved recursive folder and optional cap; Granular retains
  exact multi-file selection.
- Total Analysis snapshots every currently eligible unanalyzed catalog asset.
  General can isolate visual, audio-only, camera RAW, or other bounded content;
  Granular targets the current catalog asset. Existing-candidate reanalysis
  remains explicit.
- All scopes preserve deterministic membership, restart/retry behavior,
  project/support-file exclusions, local-only inference, and the existing
  managed-operation boundaries. No schema migration was required.
- Continuous open operation is deliberately separate from scope. Its next
  milestone must add copy stability, burst coalescing, backpressure,
  disconnect/restart recovery, intake-to-analysis orchestration, and an
  explicit foreground/background lifecycle without enlarging active snapshots.
- All 119 tests pass, including real FFprobe acceptance. The rendered native
  Analysis dialog fits at 1360x840 with Total selected by default. Packaged
  0.22.0 isolated smoke exits 0 and the capability audit reports zero blocked
  files.
- Candidate executable:
  `C:\Development\ATLAS\dist\releases\0.22.0\ATLAS Beacon\ATLAS Beacon.exe`.
  SHA-256:
  `54a455fa4c70adba18ade5e23a0aac1f48206c292d5f8c64c65297eacc82116f`.
- Candidate ZIP:
  `C:\Development\ATLAS\dist\ATLAS-Beacon-0.22.0-win64.zip`.
  SHA-256:
  `6831c560870764a872132a91e8d2f507df33e677a044e0de40efb5791e94e23f`.
- The candidate is packaged but not activated because the live 0.21.5 process
  owns an active production analysis job.

### Beacon 0.21.5 analysis failure closure

- Analysis job `ea673da9-6ed6-4e18-a83a-8b4cc9df2e37` completed in place:
  488 publishable results, two excluded editable production project files,
  zero failures, and zero pending items.
- `.aep`, `.aepx`, and `.prproj` assets remain cataloged and searchable but
  are excluded from ordinary contextual-analysis scopes. Targeted jobs also
  exclude them without a model call.
- Qwen now receives a binding evidence contract for decodable abstract visual
  samples and audio-derived spectrograms. Three abstract MP4s completed as
  grounded `visual_content`; one uniformly near-black MP4 correctly completed
  as grounded `audio_content`.
- The existing checksum-verified placement policy moved only the four newly
  analyzed MP4s from their preserved `J:\Inbox\COTR\...` hierarchy to the
  matching `J:\Projects\COTR\...` hierarchy. The excluded project files
  remained cataloged in place.
- Verified pre-retry backup:
  `C:\ProgramData\ATLAS\Beacon\backups\beacon-20260726T175508.834916Z.db`,
  SHA-256
  `7e80a87b721d30badf4ad11a5c29b3b256784fe4af00bb1fd2dce20713785a8c`.
- All 116 tests pass, including real FFprobe acceptance. Packaged 0.21.5
  smoke exits 0. The live desktop is:
  `C:\Development\ATLAS\dist\releases\0.21.5\ATLAS Beacon\ATLAS Beacon.exe`.
  Executable SHA-256:
  `abb116c179318bfe2ca45362032cf01e1cff059d0a4e7b7e57456d8aba67ec0b`.
  ZIP SHA-256:
  `145b8bcaa24d84f2704f7c309a7535c694b078db9b855870e93fcf2102d5a578`.

### Beacon 0.21.4 immediate native video preview

- Ordinary non-Apple 59.94/60 fps H.264 MP4 media now uses native Qt playback
  instead of being falsely routed through the slow-motion compatibility proxy.
- The reported 790 MB Canon MP4 produced its first native frame in 0.266
  seconds during direct acceptance testing.
- When a genuine Apple/high-frame-rate compatibility derivative is required,
  the readable source remains immediately available while a silent,
  GPU-preferred 720p proxy is prepared in the background. A fast CPU fallback
  remains available.
- Video preview shows the stored thumbnail while the first frame buffers and
  preserves playback position when switching to a completed compatibility
  derivative.
- Packaged background FFmpeg, FFprobe, thumbnail, music, and analysis helpers
  use hidden Windows process flags and no longer open console windows.
- All 113 tests pass. Packaged 0.21.4 smoke exits 0. The live desktop is:
  `C:\Development\ATLAS\dist\releases\0.21.4\ATLAS Beacon\ATLAS Beacon.exe`.
  Executable SHA-256:
  `5edb0d43d84990a3259a16b46b96ce3ff3a7c424d4bb88183b36a13d863c32cb`.
  ZIP SHA-256:
  `4b9be2bd514bcc35cce221abc02091a48707111dec5a15bb49722f851dab57ab`.

### Beacon 0.21.3 content-analysis hardening

- Schema 16 separates publishable analysis, confidently excluded generated
  artifacts, and retryable failures. Finalization validates before publishing,
  isolates bad candidates, always reaches a truthful terminal state, and can
  recover interrupted checksum-verified managed placement.
- Known Premiere preview/cache, Auto-Save, and support paths remain cataloged
  but are hidden and excluded from content inference by default.
- Incomplete media metadata is reprobed only after source checksum
  verification. Probe coverage includes AIFF and additional professional,
  mobile, and camera media containers.
- Content evidence is adaptive: uniformly low-detail black video samples fall
  through to a valid audio stream. Qwen receives rejected structured output
  on retry so it can correct itself, with a 32K local context window and
  bounded server diagnostics.
- Live job `a6f80068-0b86-42dd-887b-0fc8f5b62265` is terminal `complete`:
  408 publishable results, 177 excluded generated artifacts, zero failures,
  and zero pending items. SQLite schema 16 integrity is `ok` with zero
  foreign-key violations.
- Pre-retry backup:
  `C:\ProgramData\ATLAS\Beacon\backups\beacon-20260726T015647.539560Z.db`,
  SHA-256
  `3a5c9449aee2c36c454e7cfc166ea6218c62b3b2d395a08f30d6c47791cf844e`.
- All 110 tests pass. Packaged 0.21.3 smoke exits 0. The live desktop is:
  `C:\Development\ATLAS\dist\releases\0.21.3\ATLAS Beacon\ATLAS Beacon.exe`.
  Executable SHA-256:
  `800e025f389a9b01e012ae10b4bddce3a234c31ec1c07b8ff29e6cc545843cc`.
  ZIP SHA-256:
  `667948494f79ed2415197487c97c961fcbef38dc25dcd3e49b50cf19210bbd42`.

### Beacon 0.15.3 analysis reliability

- Beacon 0.15.3 packages durable catalog-analysis Cancel and Retry controls.
  Retry operates on the same job and resets only failed items.
- Analysis runners continue after individual asset failures. The live
  180-asset RAW job `d1e28b5c-e63c-4c0b-83f6-e1318bcd1f16` proved this on
  2026-07-24 by advancing beyond a later failed item instead of terminating.
- Overview current-failure counts now reconcile the latest intake and analysis
  jobs. Historical failed audit events remain available in the ledger but do
  not inflate the actionable count.

### Beacon 0.16.0 responsive interface

- The 180-RAW job `d1e28b5c-e63c-4c0b-83f6-e1318bcd1f16` completed all 180
  items in the same durable job after failure-only retry.
- Schema 13 persists truthful analysis pipeline stages and stage-boundary
  timestamps. The filename is derived from the active checksum-bound item.
  Cancel, recovery, retry, and terminal completion clear active state.
- Beacon conversation is now a persistent application-shell surface backed by
  the existing Beacon Desk authority. The active thread, draft, and message
  scroll position survive navigation. Page or asset context attaches only
  through an explicit human action.
- Operations will eventually merge into System. Navigation position 03 will
  become Reports, providing multiple catalog data views alongside the
  persistent Beacon conversation surface.
- Performance policy: reuse Qt/QML, SQLite, existing Beacon Desk storage, and
  replaceable local adapters; do not add a browser engine or bundle model
  weights. Measure the app separately from optional models, derivatives,
  transcripts, and caches.

### Beacon 0.17.0 live conversation worker

- Branch `worker_build` adds schema-14 durable exactly-once worker leases,
  loopback model provenance, failure recovery/backoff, and message-linked
  grounded asset cards.
- The worker automatically pauses before migration or inference while catalog
  analysis is running. It receives bounded history and read-only catalog
  search only; it has no generic filesystem or mutation tool.
- Grounded search covers filename/path, analyzed context, editable metadata,
  and checksum-bound transcript text. Inspect opens the permanent asset in
  Library without copying or changing the source.
- The 500-item job `d020d54c-b39a-42eb-b9d9-6b8cb800b29f` completed 500/500
  before activation. The verified pre-schema-14 backup is
  `beacon-pre-schema14-20260724T212407.964644Z.db`, SHA-256
  `6d6d573a4760a14e9a20281edd23fb463cb87768ddc614f38d0cbc0ae4374fb4`.
- The live schema-14 worker answered the bounded `IMG_0414.CR3` activation
  request in one durable run. The requested asset was grounded at rank one;
  post-run integrity remained `ok` with zero foreign-key errors.
- The packaged 0.17.0 desktop replaced the running 0.16.0 process cleanly.
  A local watch worker then detected and answered a queued follow-up without
  manual invocation. Its runtime PID file is
  `C:\ProgramData\ATLAS\Beacon\conversation-worker.pid`.
- Custom intake now offers both exact multi-file selection and recursive
  selection of one approved folder with the existing optional item limit.
- Near-duplicate/series intelligence is the next analysis-efficiency milestone:
  perceptual fingerprints and capture adjacency shortlist candidates before a
  local visual model reviews relationships.

### Beacon 0.17.1 grounded-delivery correction

- Explicit no-search language bypasses catalog planning and retrieval.
- A single exact filename bypasses planning and defaults to one exact result.
- Generic system/provenance terms are rejected; known live use-test and
  sandbox paths are excluded from ordinary worker retrieval.
- The structured answer identifies evidence it actually used. Only those
  references become durable result cards; ordinary searches default to three
  candidates unless the human asks for a collection.
- Schema 15 retains explicit corrections with the correcting human message and
  prior Beacon response. Memory is thread-scoped and cannot silently become a
  global catalog rule or alter model weights.
- The verified pre-schema-15 backup is
  `beacon-pre-schema15-20260724T220248.319996Z.db`, SHA-256
  `eaffcec837eae9b81e1279525f38c456c63337696b26aafd2b61bb72df078d96`.
- All 83 tests passed. Isolated real-Qwen acceptance returned exactly one card
  for `Beacon-exact-test.mov` and zero cards for an explicit no-search request.
- Packaged 0.17.1 smoke exited 0; the release is 417,607,625 bytes, the ZIP is
  160,930,913 bytes, and the capability audit found zero blocked files.
- The live catalog migrated to schema 15 with integrity `ok` and zero
  foreign-key errors. The 0.17.1 desktop and replacement watch worker are
  running.

### Beacon 0.17.2 positive retrieval trigger hotfix

- Qwen incorrectly planned `Find me an image of Connor and Jules` as no
  search even though one live asset contained both names.
- `Find`, `Show`, `Locate`, `Pull up`, `Retrieve`, and `Get` media requests now
  force deterministic catalog retrieval.
- Conjoined multi-person targets use all-terms matching, so one asset must
  match every requested name instead of unioning unrelated individual matches.
- The live proof resolves exactly one asset:
  `Connor and Jules in Colorado Springs`.
- All 84 tests pass. Packaged 0.17.2 smoke exited 0; the release is
  417,608,838 bytes, the ZIP is 160,930,625 bytes, and the capability audit
  found zero blocked files.

### Beacon 0.18.0 Qwen-led conversation agent

- The fixed conversational phrase router is removed from the primary flow.
  Qwen formalizes the active human goal, including catalog need, count, media
  type, constraints, and correction intent, then controls a bounded iterative
  search/inspect/respond loop.
- Catalog code is a read-only tool and safety boundary, not the conversational
  decision-maker. Hard limits cover loopback inference, history/context,
  agent steps, search/inspection counts, and observed asset IDs. Beacon still
  receives no generic filesystem, cloud, or mutation tool.
- Qwen chooses search concepts and refinement, can inspect accepted contextual
  analysis and transcripts, asks focused questions when needed, selects the
  exact grounded cards, and composes its own answer.
- Exploratory query buckets and likely filename series are interleaved.
  `potential_series_hint` helps Qwen avoid adjacent captures when the human
  requests distinct results. This does not replace future perceptual
  near-duplicate analysis.
- Thread-scoped correction memory remains schema 15, but Qwen now identifies
  actual corrections from context rather than a fixed correction-phrase list.
- All 87 tests pass. Isolated real-Qwen acceptance passed exact
  Connor-and-Jules retrieval, explicit no-search conversation, and three
  distinct food-image selection with exactly three cards.
- Packaged 0.18.0 smoke exited 0. The release is 417,616,746 bytes; the ZIP is
  160,939,571 bytes. Executable SHA-256:
  `0c236690208069283e57522e4942c9be797bf4b78abb033bfd41233044f62631`.
  ZIP SHA-256:
  `67a5db721412ba2f29a7294af244e3c12f27d92ca13a8cb9030f9f8201370b57`.
- The verified pre-activation backup is
  `beacon-20260724T225332.693652Z.db`, SHA-256
  `048b0dc111d199591f1c64fb20f7d38cf227412f62f5d40f683d1999e1c9f492`.
- The live 0.18.0 worker returned a guacamole-preparation photo, an event food
  presentation, and a dark-chocolate close-up for the three-unique-food-images
  acceptance request. The acceptance thread was resolved afterward. Live
  schema 15 integrity is `ok` with zero foreign-key violations.

### Beacon 0.18.1 goal-reconciliation hotfix

- Qwen's initial request goal is now a revisable working interpretation. A
  conflicting later Qwen tool decision triggers a focused Qwen reconciliation
  against the active human request instead of a code veto.
- The exact prior failure was reproduced: the initial Qwen pass marked the
  typo-containing food request as not requiring catalog evidence, while the
  later Qwen pass requested a food search. Reconciliation revised the goal to
  catalog evidence required and returned 16 candidates.
- Explicit no-search instructions remain protected: a regression test forces a
  contradictory search action and verifies that Qwen reconciliation preserves
  the no-search goal.
- Initial and reconciled goals persist as `beacon_conversation_goal` events
  with prior/current values and a changed flag.
- All 89 tests pass. Packaged 0.18.1 smoke exited 0. The release is
  417,618,345 bytes; the ZIP is 160,940,977 bytes. Executable SHA-256:
  `2b9b7c178ca474ff58756b66f8b8aa877b0ffc3de8ee982f5a600bae6023baca`.
  ZIP SHA-256:
  `eb9719dc6cf11657d578bde19ccd6a7b13ee5f5f1b58a140af0e7cd2f8fe657a`.
- The 0.18.1 desktop and watch worker are live on schema 15. A live
  typo-containing three-food-image acceptance returned exactly three cards;
  the acceptance thread was resolved afterward.

### Identity

- Project: **ATLAS — Adaptive Topological Library & Archive System**
- AI librarian: **Beacon**
- Mission: preserve, organize, and make searchable Connor's creative archive.
- Core boundary: AI observes and catalogs; it does not own or destructively alter originals.

### Cross-Machine Naming Convention

- **Jarvis** — Codex on Connor's MacBook.
- **Ultron** — Codex on the Windows ATLAS PC.
- **Beacon** — the AI librarian/software subsystem inside ATLAS.

Jarvis and Ultron are conversational handles for distinct Codex environments. Beacon remains the technical product/module name. Do not rename code, services, packages, paths, databases, schemas, or APIs from Beacon to Ultron unless Connor explicitly requests that separate technical change.

- Current Windows hostname verified on 2026-07-23: `DESKTOP-8B4OJIR`.
- Connor has requested the Windows hostname `Ultron`; the rename is pending a
  Windows restart later on 2026-07-23. Do not record it as completed until
  `$env:COMPUTERNAME` verifies the new value after restart.

### Windows and Storage

- Host is a Windows desktop with an Intel Core i9, 64 GB RAM, and an MSI Tomahawk motherboard.
- An NVIDIA GeForce RTX 3060 with 12,288 MiB VRAM and driver 610.74 was
  observed through `nvidia-smi` on 2026-07-23; re-check before selecting or
  benchmarking local models.
- Local-analysis measurement on 2026-07-23 showed audio transcription as the
  dominant cost: 11 completed audio items consumed about 43.5 processing
  minutes (4.0 minutes average), versus about 1 minute for three videos.
  Qwen occupied about 9.9 GiB of 12 GiB VRAM while faster-whisper ran CPU
  INT8. The workstation's 64 GB system RAM provides headroom for model caches,
  transcript/derivative caching, and staged pipelines, but does not by itself
  replace CPU/GPU compute throughput.
- ATLAS uses StableBit DrivePool.
- Reported pooled drive: `J:\`
- Reported raw usable capacity: approximately 15.5 TB.
- Pool members reported at setup:
  - `ATLAS1` — 4 TB
  - `ATLAS2` — 4 TB
  - `ATLAS3` — 5 TB
  - `ATLAS4` — 4 TB
- DrivePool duplication was reported off.
- No parity layer was reported configured.
- SMART was reported clean at setup.
- SMB share name: `ATLAS`.
- The Mac mounted the share at `/Volumes/ATLAS`; that Mac path is not a Windows runtime path.

These are setup-time facts. Re-check current capacity, drive health, pool status, backup state, and drive letter on the Windows host before relying on them.

### Path Contract

```text
Source repository:
C:\Development\ATLAS\

Active runtime:
C:\ProgramData\ATLAS\Beacon\
├── beacon.db
├── logs\
├── cache\
└── temp\

Protected managed storage:
J:\

Portable ATLAS documentation:
J:\System\Documentation\ATLAS\

Beacon backup destination:
J:\System\Backups\Beacon\
```

- Source code and dependencies belong on NVMe.
- Live database, cache, logs, and temporary work belong on NVMe during development.
- Originals and long-term managed assets belong on the ATLAS pool.
- A backup on the same pooled system is useful for recovery/versioning but is not a complete independent disaster-recovery strategy.

### Existing ATLAS Root

The root was observed from the Mac with:

```text
J:\
├── Inbox\
├── Library\
│   ├── Clients\
│   ├── Personal\
│   ├── Stock\
│   ├── Drone\
│   └── Legacy\
├── Assets\
│   ├── Music\
│   ├── SFX\
│   ├── Graphics\
│   ├── LUTs\
│   └── Templates\
├── Projects\
├── Exports\
├── Beacon\
│   ├── Database\
│   ├── Metadata\
│   ├── Embeddings\
│   ├── Proxies\
│   ├── Thumbnails\
│   ├── Transcripts\
│   └── Logs\
└── System\
```

The fuller proposed structure in `ATLAS_CODEX_HANDOFF.md` is provisional. Existing folders must not be reorganized simply to match a diagram.

### Current Content Caution

- At least one image was observed in `J:\Inbox\` from the Mac.
- Its presence does not make it an approved prototype fixture.
- The first prototype must use generated/synthetic test data in a clearly named sandbox.

## Locked Principles

These are stable unless Connor explicitly changes them:

1. ATLAS is the platform, not a particular set of disks.
2. Beacon is modular and replaceable.
3. Originals remain ordinary accessible files.
4. AI is non-destructive by default.
5. Every managed asset should eventually have a permanent `atlas://asset/<uuid>` identity.
6. Managed intake is controlled and auditable.
7. Reliability precedes intelligence.
8. Core operation is local-first.
9. Source, runtime state, derivatives, metadata, backups, and originals remain distinguishable.
10. Successful analysis authorizes an audited move from Inbox when Beacon can
    infer an unambiguous final home from established hierarchy. Ambiguous files
    remain in place pending a focused clarification.

## Current Phase

Phase 0, the Phase 1 synthetic read-only catalog, the Phase 2 local observatory
foundation, the native desktop client, and the first controlled media use test
are verified complete through Beacon 0.9.0, including verified thumbnail
derivatives, native temporary media and text previews, an application-level
Space shortcut, a checksum-bound candidate-analysis schema, and a five-asset
Beacon librarian pilot. Schema 5 adds the durable native Beacon Desk with
explicit waiting-for-human, queued-for-Beacon, and resolved conversation states.
Schema 6 adds revisioned editable context and policy-gated checksum-verified
managed moves. Schema 7 adds explicit recursive intake snapshots, durable
per-file state, progress, cancel, resume, failure-only retry, and recovery.
Schema 8 adds durable local-only contextual-analysis jobs, per-asset recovery,
explicit local endpoint/model provenance, and a native scope-and-policy dialog.
The exact packaged 0.9.0 application completed a three-file nested synthetic
intake without changing source hashes. The first 0.9.0 launch migrated the
production catalog cleanly to schema 7; it is healthy with no intake jobs. A
verified pre-schema-7 online backup exists. The prior packaged launch was
checked against the schema-6 live
catalog. A completed 7,093-file Inbox transfer received a stable read-only
inventory; one known-checksum Inbox location completed the bounded
catalog-to-managed-location proof. The resumable intake milestone is complete;
the next gate is a bounded 25-file live-Inbox reliability pilot.

The first implementation target is a read-only vertical slice against synthetic fixtures:

1. detect a file only after it is stable;
2. assign a stable UUID;
3. calculate SHA-256;
4. capture filesystem metadata;
5. capture ffprobe metadata for supported media;
6. store the record in SQLite;
7. recognize checksum duplicates;
8. survive restart without duplicate asset rows;
9. expose a CLI list/inspect flow;
10. leave the source file byte-identical.

## Decisions Already Made

| Decision | State | Rationale |
|---|---|---|
| Active repository on NVMe | Decided | Fast Git, dependencies, builds, and separation from pool maintenance |
| Initial database is SQLite | Starting direction | Simple, local, inspectable, and sufficient for the first catalog |
| Core API direction is Python/FastAPI | Starting direction | Modular local service with typed schemas |
| First intake pass is read-only | Decided | Prove safety and identity before managed moves |
| Originals remain ordinary files | Locked principle | Avoid lock-in and preserve access |
| Cloud is optional for core operation | Locked principle | Privacy and availability |
| Vector search comes after dependable catalog/search | Decided sequence | Reliability before intelligence |
| Phase 1 runs as an ordinary foreground CLI | Decided for Phase 1 | Easy to stop, inspect, and recover; no service lifecycle yet |
| Phase 1 metadata lives in SQLite | Decided for Phase 1 | One inspectable transactional authority; sidecars remain an open later policy |
| Phase 1 UUID is deterministic from SHA-256 | Provisional | Stable retries and duplicate recognition; edit/version semantics remain open |
| Phase 2 browser dashboard | Superseded by Beacon 0.3.0 | Preserved as an optional development surface, not the product UI |
| Phase 2 binds only to `127.0.0.1` | Decided | No LAN or remote exposure without a separate security design |
| Primary interface is a native Qt Quick/QML desktop app | Decided for current builds | Develop and verify the UI in the same Windows application context that ships |
| Desktop app starts no API, browser, or network listener | Decided | Keep the user application local and self-contained; API remains an explicit optional adapter |
| Windows build is a PyInstaller one-folder bundle | Decided for current builds | Easier diagnosis and no per-launch temporary extraction |
| Database backups remain on local NVMe for now | Decided for Phase 2 | Verified recovery artifacts without treating same-pool copies as disaster recovery |
| Portable Markdown documentation lives under `J:\System\Documentation\ATLAS\` | Decided | Keep the storage root limited to operational folders while retaining one discoverable context bundle |
| Common raster images use explicit FFprobe handling | Decided in Beacon 0.3.1 | Preserve image kind and dimensions while suppressing meaningless single-frame duration |
| Current thumbnail derivatives live under the local runtime tree with schema-backed lineage | Decided in Beacon 0.4.0 | Keep generated data separate from originals and make it safe to regenerate |
| Space opens a native temporary preview | Decided in Beacon 0.4.0 | Borrow Finder's low-friction inspection pattern without opening an editor or changing the source |
| A normal standalone launch opens and labels the live catalog | Decided in Beacon 0.4.1 | Prevent isolated test databases from being mistaken for the user's working library |
| Plain text renders inside the native temporary preview | Decided in Beacon 0.5.0 | Make scripts, notes, logs, and metadata inspectable without launching an editor; cap displayed content at 512 KB and reject binary control-heavy input |
| Space is an application-level preview shortcut | Decided in Beacon 0.5.0 | Keep the selected asset action stable even when a button previously held keyboard focus |
| AI output lives separately from verified asset facts | Decided in Beacon 0.6.0 | Preserve provenance and prevent probabilistic output from silently becoming canonical technical metadata |
| Analysis imports are checksum-bound, atomic, and idempotent | Decided in Beacon 0.6.0 | Reject stale or partial result sets and attach intelligence to asset identity rather than filename/location |
| Every AI result begins as a reviewable candidate | Decided in Beacon 0.6.0 | Keep human judgment over titles, tags, privacy, rights, and archive meaning |
| Analysis completion commits unambiguous Inbox placement | Supersedes the Beacon 0.6.0 suggestion-only rule in Beacon 0.12.0 | Remove routine approval friction while retaining checksum, collision, root, reparse, audit, and rollback safeguards |
| Music models run in an isolated Python 3.11 runtime | Decided in Beacon 0.13.0 | Preserve Beacon's Python 3.12 package while supporting Basic Pitch and CUDA-enabled Demucs |
| Music analysis is gated by tonal stability before MIDI or stems | Decided in Beacon 0.13.0 | Avoid expensive false-positive processing of speech and weakly musical recordings |
| Essentia remains an optional uninstalled adapter | Decided in Beacon 0.13.0 | Its AGPL license and Windows packaging need a deliberate distribution decision |
| External inference requires explicit recorded authorization and execution labeling | Decided in Beacon 0.6.0 | Keep local/cloud boundaries visible and auditable |
| Beacon questions and human replies persist as ordered SQLite conversations | Decided in Beacon 0.7.0 | Make blockers and context durable across app restarts and analysis sessions |
| Human replies queue a conversation but do not resolve it automatically | Decided in Beacon 0.7.0 | Preserve an explicit handshake between supplied context and Beacon review |
| Conversation never directly authorizes a file operation | Decided in Beacon 0.7.0 | Keep plain-English guidance separate from consequential audited execution |
| The UI labels the Desk as saved locally rather than implying an always-online worker | Decided in Beacon 0.7.0 | Make actual execution state honest and legible |
| Human/contextual asset metadata is revisioned, searchable, and editable in Library | Decided in Beacon 0.8.0 | Keep titles, descriptions, people, dates, places, project/client, rights, tags, notes, and destinations correctable without rewriting source media |
| Verified technical facts remain locked outside the editable context record | Decided in Beacon 0.8.0 | Preserve checksum and probe evidence while allowing librarian judgment to evolve |
| Managed moves require recorded policy, exact catalog location, approved root, and source/destination checksum verification | Decided in Beacon 0.8.0 | Make organization consequential but recoverable, bounded, non-overwriting, and auditable |
| A completed managed location is preferred as the current path while every duplicate location remains visible | Decided in Beacon 0.8.0 | Present the durable archive location without erasing provenance or silently deduplicating |
| Recursive intake is an explicit snapshot and never an automatic production watcher | Decided in Beacon 0.9.0 | Keep large-folder work reviewable, bounded, and user-started |
| Intake persists item-level states and resumes without repeating completed items | Decided in Beacon 0.9.0 | Make cancel, app closure, crash recovery, and failure-only retry dependable |
| The first live Inbox run is limited to 25 files | Decided for the Beacon 0.9.0 pilot | Prove the real storage path and lifecycle before full-corpus work |
| Contextual analysis is local-first behind replaceable adapters | Decided for Beacon 0.10.0 | Preserve privacy and provenance while allowing separately approved external adapters later |
| Analyze Catalog opens a scope-and-policy dialog | Decided for Beacon 0.10.0 | Show scope, runtime, model, limitations, and authority before starting work |

## Decisions Still Open

Do not silently resolve these:

- production background run mode: scheduled task, Windows service, or container;
- exact copy-stability algorithm and time thresholds;
- metadata split between SQLite and sidecar files;
- asset identity rules across moves, renames, edits, and true duplicates;
- independent backup/parity strategy for original media;
- database backup schedule, retention, and tested restore workflow;
- privacy zones and default indexing exclusions;
- which AI models are local versus optional external adapters;
- which root conventions are fixed versus configurable;
- whether derivatives live only under `J:\Beacon\` or may be colocated by policy;
- long-term ATLAS visual-token and brand refinements.

## Required Acceptance Evidence

Before declaring Phase 1 complete, retain evidence for:

- test results;
- database schema and migrations;
- two restart/idempotency passes;
- duplicate-detection cases;
- interrupted/partial-copy cases;
- unavailable-path behavior;
- unsupported/corrupt media behavior;
- proof that source fixtures remain byte-identical;
- logs containing useful job and asset identifiers without secrets;
- CLI output for list and inspect;
- current documentation matching actual behavior.

## Durable Failure Notes

Add entries only when a failure produces a reusable lesson:

```text
Date: 2026-07-23
Symptom: JPEGs were cataloged safely but appeared as generic files without dimensions.
Cause: The FFprobe allowlist covered audio/video extensions but not still images.
Fix: Added explicit common-raster probing, an image-kind marker, and duration suppression.
Verification: Controlled media copies, source/packaged UI review, and 19 passing tests.
Prevention: Include representative real format copies in controlled tests before expanding scope.
```

```text
Date: 2026-07-23
Symptom: Adding Qt Multimedia initially pulled unrelated virtual-keyboard files into the Windows bundle.
Cause: PyInstaller's stock QtQml hook collects every QML module installed by the PySide6 Addons wheel.
Fix: Added a Beacon-specific QML allowlist, a post-analysis capability filter, and a build-time bundle audit.
Verification: Final bundle contains required multimedia files and zero browser, 3D, charting, PDF, or virtual-keyboard files.
Prevention: Make the capability audit a required part of every packaged build.
```

```text
Date: 2026-07-23
Symptom: The standalone app appeared to lose the media library and showed only the synthetic note.
Cause: Verification used an explicit isolated UseTest-01 database, while a normal double-click correctly opened the separate live database; promotion to the live catalog had not been performed or communicated.
Fix: Verified both databases and all source hashes, backed up the live database, cataloged the approved NVMe copies into it, labeled catalog context in the UI, and added change-triggered refresh.
Verification: Exact no-argument Beacon 0.4.1 launch shows five live assets with thumbnails; preview works; schema 3 is healthy with zero failures; 22 tests pass.
Prevention: Every release involving representative data must verify the exact no-argument standalone launch in addition to isolated test profiles.
```

```text
Date: 2026-07-23
Symptom: After an action button received focus, Space could activate that button instead of previewing the currently selected asset.
Cause: The preview shortcut used the default window context and primary action buttons accepted click focus.
Fix: Promoted Space to an application-level, non-repeating shortcut; limited primary buttons to tab focus; returned focus to the asset list when preview closed.
Verification: A real offscreen Qt test force-focuses the Preview button and confirms Space opens and closes the selected asset; source and packaged live-catalog renders passed; 27 tests pass.
Prevention: Treat Finder-style preview as an application command and retain focused-control regression coverage.
```

```text
Date:
Symptom:
Cause:
Fix:
Verification:
Prevention:
```

## Decision Record Template

```text
### YYYY-MM-DD — Decision title

Status: proposed | accepted | superseded

Context:
Decision:
Consequences:
Evidence:
Supersedes:
```

## Session Handoff Template

Keep only the latest concise handoff here. Move detailed history into repository documentation or version control.

```text
### Current handoff

Last verified:
Working branch/commit:
Current milestone:
Verified complete:
In progress:
Blocked:
Files changed:
Tests/live checks:
Unverified assumptions:
Next smallest step:
```

## Current Handoff

- Last verified: 2026-07-24 on the Windows ATLAS host
- Working branch: `C:\Development\ATLAS`, `main`
- Current milestone: Beacon 0.18.1 Qwen goal reconciliation
- Verified complete: the exact 250-file, 98.72-GB production intake completed;
  242 unique identities were cataloged and the final one-item contextual retry
  completed. Beacon 0.14 adds independently scrollable Recents/Explorer Library
  panels, catalog-backed folder navigation, file-type filters, brass/cyan
  analysis-state rails, Microsoft Raw Image Extension, and packaged
  rawpy/Pillow camera-RAW derivatives. Beacon 0.15 fixes analysis-state rails,
  uses an explicit vertical Flickable for Library detail scrolling, adds exact
  multi-file Inbox selection, requires a RAW visual derivative before
  contextual claims, and moves every unambiguous analyzed Inbox location.
  Beacon 0.16 adds schema-13 truthful durable pipeline stages and the
  persistent shell-level Beacon Desk conversation dock.
- In progress: user-directed conversational search testing; Beacon 0.18.1 and
  its local watch worker are running.
- Blocked: none for the current bounded release.
- Files changed: revisable Qwen working goals, focused contradiction
  reconciliation, durable goal audit events, tests, packaging, and docs.
- Tests/live checks: all 89 tests passed, including real ffprobe acceptance;
  live schema 15 integrity is `ok` with zero foreign-key errors; the verified
  pre-activation and older backups are retained. Packaged 0.18.1 isolated
  smoke exited 0 and the canonical capability audit found no blocked desktop
  capability files.
- Unverified assumptions: post-restart Windows hostname, physical SMART state,
  DrivePool duplication/parity, independent archive backup strategy, code
  signing, production chord/key accuracy, acceptable stem storage policy,
  Essentia licensing, face-analysis policy, rights taxonomy, and canonical
  sidecar-versus-SQLite metadata policy
- Live reconciliation: seven `.DS_Store` contextual results were rejected as
  non-media OS metadata; the eight remaining analyzed duplicate video
  locations were checksum-verified and moved from Inbox into their preserved
  `J:\Projects\...\C3` hierarchy. No analyzed locations remain in Inbox.
- Finder metadata policy: `.DS_Store` is irrelevant, explicitly disposable
  metadata. Beacon sends encountered copies to the Windows Recycle Bin before
  freezing a new intake snapshot and records an audit event. The seven prior
  live copies and their obsolete catalog identities were removed on 2026-07-24
  after a verified database backup.
- Storage: C: had 52.4 GB free. Fixed consumers were approximately 7.8 GB music
  runtime, 9.0 GB Ollama models/runtime, 4.7 GB release builds, and 1.0 GB
  Whisper. Corpus analysis does not copy source media to C:; sampled frames are
  temporary and cleaned. New live thumbnails route to
  `J:\Beacon\Thumbnails`; Demucs stems remain disabled by default.
- Next smallest step: run user-directed Beacon questions that exercise exact
  filenames, no-search replies, ambiguous concepts, collections, follow-up
  context, and corrections; improve Qwen prompts/tool evidence from observed
  failures without restoring fixed conversational trigger logic.
- Deferred until the new Personal-files analysis finishes: diagnose missing
  HEIC support and Apple slow-motion video playback that freezes visually on
  the first frame while audio continues. Do not interrupt the live analysis
  for these media-runtime fixes.
