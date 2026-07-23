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

## Next — recovery and pilot hardening

- approve an exact non-production pilot scope
- tune stability thresholds with representative copy patterns
- add backup retention policy and a tested restore workflow
- add explicit job records for long-running work
- add signed installer/update analysis
- add thumbnails with recorded lineage

## Later — intelligence and managed intake

- transcription, scene analysis, and replaceable embeddings
- approval-based organization
- audited file operations
- integrations and optional external model adapters
