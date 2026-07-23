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

## Next — repeatable local intelligence

- choose and benchmark replaceable local vision, transcription, and audio
  understanding adapters
- add representative-frame and timecoded evidence records
- add explicit Accept/Reject review without automatic file operations
- define privacy zones, face-analysis policy, rights flags, and production scope
- add durable queued jobs for large stable snapshots

## Later — managed intake

- replaceable embeddings and semantic search
- approval-based organization
- audited file operations
- integrations and optional external model adapters
