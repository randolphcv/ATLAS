# ATLAS Roadmap

## Completed — dependable synthetic catalog

- synthetic read-only intake
- stability detection
- durable identity, checksums, SQLite migrations
- duplicate and restart idempotency
- CLI and structured logs
- unavailable/corrupt-path tests

## Completed — local observatory foundation

- loopback-only FastAPI adapter
- catalog search and asset detail
- visible audit-event ledger
- integrity/foreign-key health
- verified online database backup
- reproducible Windows application bundle

## Completed — native desktop client

- Qt Quick/QML Windows interface with native application lifecycle
- persistent archive navigation and master-detail library
- non-blocking backup controller with explicit confirmation
- no browser launch, embedded web view, or network listener
- icon and Windows version metadata
- rendered source and packaged-executable verification

## Completed — first controlled media use test

- five explicitly supplied media copies staged from ATLAS to NVMe
- source/destination SHA-256 equality before cataloging
- JPEG, WAV, and MP4 technical metadata verified
- renamed checksum duplicate resolved to one asset with two locations
- restart/idempotency and database integrity verified
- ATLAS source hashes verified unchanged after the complete run
- schema-backed image/video/audio thumbnails with recorded source lineage
- native Space preview with image fit, audio waveform/playback, video playback,
  and a safe metadata fallback
- exact default-launch Beacon 0.4.1 library and preview states visually verified
- isolated use-test media promoted to the live catalog only after a verified
  default-database backup

## Next — recovery and pilot hardening

- approve an exact non-production pilot scope
- tune stability thresholds with representative copy patterns
- add backup retention policy and a tested restore workflow
- add explicit job records for long-running work
- add signed installer/update analysis
- add a tested database restore workflow

## Completed — candidate intelligence foundation

- schema-backed, checksum-bound analysis runs and candidate results
- explicit analyzer, policy, execution-location, confidence, and provenance
- external-inference authorization recorded with the run
- native candidate metadata display and candidate search
- approval-only organization suggestions
- bounded five-asset librarian pilot with the active ATLAS inbox excluded

## Completed — durable Beacon conversations

- native Overview-page Beacon Desk with master-detail conversation history
- explicit waiting-for-human and queued-for-Beacon states
- plain-English replies and human-started requests persisted in SQLite
- separate explicit resolution with no conversational file-operation authority
- initial pilot blockers and optional enrichment questions kept distinct

## Implemented on worker_build — grounded Beacon conversation worker

- durable exactly-once thread leases and worker run history
- loopback-only replaceable local-model adapter
- automatic pause while catalog analysis uses the inference lane
- bounded read-only catalog search with no generic filesystem tool
- message-linked grounded asset cards with Library inspection
- explicit native one-thread run and low-frequency foreground watch modes

## Next — near-duplicate and capture-series intelligence

- retain SHA-256 as the exact-duplicate authority
- generate checksum-bound perceptual image fingerprints from verified
  derivatives
- use capture time, camera/lens metadata, dimensions, and folder adjacency to
  propose burst/series candidate groups
- compare only shortlisted neighbors with a local visual embedding or Qwen,
  rather than asking the model to compare every image with the preceding file
- store scored similarity edges and human-correctable series membership
- let analysis reuse shared series context while preserving distinct originals
- expose “representative,” “alternate angle,” and “near duplicate” as
  suggestions, never automatic deletion or identity merging

## Completed — editable context and first managed move

- revisioned, searchable, human-editable contextual metadata in native Library
- strict separation between editable context, AI candidates, and verified facts
- recorded local-AI, external-approval, candidate-storage, and move policies
- checksum-verified, approved-root, non-overwriting managed moves
- exact catalog-location updates, immutable move evidence, and rollback path
- independently stable large-Inbox inventory and one live end-to-end proof

## Completed — resumable archive intake

- schema-7 recursive snapshots with approved-root and reparse-point boundaries
- durable per-file pending, running, complete, and failed states
- native Overview progress, current-path, cancel, resume, and retry controls
- app-close pause and interrupted-session recovery without repeating completed
  items
- bounded representative batches plus uncapped deterministic snapshots
- exact packaged synthetic completion with source hashes unchanged

## Completed — scalable one-shot scope controls

- shared Granular, General, and Total scope language for Intake and Analysis
- Total as the visible default for normal full-scope operation
- uncapped Total Intake against the configured approved Inbox root
- Total Analysis across every currently eligible unanalyzed catalog asset
- General folder/cap Intake and visual, audio, RAW, or other Analysis scopes
- Granular exact-file Intake and current-catalog-asset Analysis
- no schema change, silent dynamic scope growth, cloud fallback, or watcher
- durable snapshot, cancel, retry, restart, and inference-lane boundaries
  preserved

## Next — continuous open operation

- observe only configured approved roots while Beacon remains open
- require copy stability before creating ordinary intake job items
- debounce and coalesce arrival bursts without mutating an existing snapshot
- enforce backpressure and one active intake runner
- start Analysis only after the corresponding Intake scope is terminal and
  the local inference lane is free
- persist watcher checkpoints, drive-disconnected state, retry policy, and
  shutdown/restart recovery
- define foreground, taskbar, and eventual Windows background lifecycle
  separately from filesystem correctness

## Next — repeatable local intelligence

- choose and benchmark replaceable local vision, transcription, and audio
  understanding adapters
- add representative-frame and timecoded evidence records
- add explicit Accept/Reject review without automatic file operations
- define privacy zones, face-analysis policy, rights flags, and production scope
- measure catalog and derivative throughput from the bounded live pilot

## Later — managed intake

- replaceable embeddings and semantic search
- approval-based organization
- audited file operations
- integrations and optional external model adapters
