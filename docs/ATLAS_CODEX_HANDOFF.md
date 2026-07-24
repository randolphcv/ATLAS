# ATLAS — Codex Project Handoff

## 2026-07-24 Beacon 0.17.1 corrected grounded delivery

Beacon now treats search intent as a policy boundary rather than relying on
the planning model alone. Explicit no-search requests produce no catalog
query. A single exact filename produces one exact card by default. Generic
system/provenance terms and known live test/sandbox paths are excluded, and
only evidence references actually used by the answer become durable cards.

Schema 15 adds thread-scoped correction memory linked to the correcting human
message and prior Beacon response. Corrections survive bounded history but do
not silently become global rules, alter catalog metadata, or train weights.

All 83 tests and isolated real-Qwen exact/no-search acceptance passed. A
verified schema-14 backup was retained before the healthy live schema-15
migration. Packaged Beacon 0.17.1 and its watch worker are running.

## 2026-07-24 Beacon 0.17.0 live conversation worker

Branch `worker_build`, created from local `main` commit `4180872`, adds the
lean local Beacon conversation worker. Schema 14 provides durable worker leases and message-linked grounded
catalog result cards. The worker uses only a loopback model endpoint, bounded
conversation history, and read-only catalog search; it has no generic
filesystem or catalog-mutation tool.

The 500-item contextual-analysis job completed 500/500 before activation.
A verified schema-13 backup was created and hashed, the live catalog migrated
to schema 14, and one bounded Qwen request returned the requested asset as its
rank-one grounded card. Post-run integrity is `ok` with zero foreign-key
errors. The worker still returns `analysis_running` before migration or
inference whenever a future catalog-analysis job owns the inference lane.

Grounded result cards resolve the current preferred path and can be inspected
in Library. They do not copy, move, delete, or otherwise change source files.
Custom intake now provides both exact multi-file selection and recursive
selection of one approved folder with the existing optional file limit.
Near-duplicate and capture-series intelligence is recorded as the next
analysis-efficiency milestone in `ROADMAP.md`.

## 2026-07-24 Beacon 0.16.0 responsive shell update

The 180-RAW job `d1e28b5c-e63c-4c0b-83f6-e1318bcd1f16` is complete in the
same durable job: all 180 items completed, including the prior malformed Qwen
response on its failure-only retry. The live catalog migrated from schema 12
to schema 13 after a verified online backup and remains healthy in WAL mode
with SQLite integrity `ok` and zero foreign-key errors.

Schema 13 adds truthful durable analysis-stage boundaries and derives the
display-safe current filename from the active checksum-bound job item. The
native Overview shows the stage immediately beneath analysis progress.

Beacon 0.16.0 also adds a compact application-shell conversation dock backed
by the existing Beacon Desk tables and controller models. The active thread,
draft, and message scroll state survive page navigation. Context attachment is
explicit and inspectable; conversation still cannot directly execute a file
operation. No cloud, browser engine, second chat database, or bundled model was
added.

## 2026-07-24 Beacon 0.15.3 reliability update

Catalog analysis is no longer fail-fast. Individual failures remain retryable
while the durable job continues through pending assets. Native Cancel resolves
the latest running analysis job even when it was started outside the current
app process, and Retry resets only failed items in that same job. The Overview
reports current retryable intake/analysis failures rather than lifetime failed
audit-event history.

The next responsive-interface phase is specified in
`docs/BEACON_RESPONSIVE_UI_HANDOFF.md`: finish the current 180-RAW job, add
truthful durable pipeline-stage status, and establish a lightweight
application-shell Beacon conversation surface that persists across pages.

## Project Identity

**ATLAS**  
**Adaptive Topological Library & Archive System**

ATLAS is a modular, long-term media storage and intelligence platform designed to manage personal memories, professional media, reusable assets, project files, and future integrations.

**Beacon** is the AI librarian inside ATLAS. Beacon observes, analyzes, indexes, organizes, and retrieves files without owning or modifying the originals.

### Environment names

- **Ultron** is Codex on the Windows ATLAS workstation.
- **Jarvis** is Codex on Connor's MacBook.
- **Beacon** is the product/runtime and future persistent local agent, not a
  Codex subagent and not another name for Ultron.

The Windows hostname was still `DESKTOP-8B4OJIR` when verified on 2026-07-23.
Connor intends to rename it to `Ultron`, effective only after a later restart.

> Current implementation note (2026-07-24): Beacon 0.16.0 is a packaged native
> Windows app, not a browser-first dashboard. Schema 12 adds persistent,
> checksum-bound full transcripts to the existing recursive
> Archive Intake snapshots, durable item-level progress, cancel-between-files,
> resume, retry-only-failures, and interrupted-session recovery. Intake remains
> catalog-only. Successful contextual analysis triggers checksum-verified
> placement when the Inbox hierarchy provides an unambiguous final home; only
> unclear placement produces a clarification. See
> `ATLAS_PROJECT_MEMORY.md` for the current verified runtime and release state.
> Music intelligence runs through a separate Python 3.11 environment with
> CUDA Demucs, ONNX Basic Pitch, and librosa DSP. Essentia is intentionally not
> distributed pending an explicit AGPL licensing decision.
> The Library now has independently scrollable Recents and catalog-backed
> Explorer views, direct folder navigation, file-type filters, and brass/cyan
> cataloged-versus-analyzed rails. Microsoft Raw Image Extension plus Beacon's
> packaged rawpy/Pillow fallback provides non-destructive CR2, CR3, and common
> camera-RAW previews.
> RAW contextual analysis now requires a verified local visual derivative;
> Beacon will fail safely rather than infer image contents from a filename.
> New Intake can create either a bounded recursive snapshot or an exact
> human-selected multi-file batch. Analysis placement commits every
> unambiguous Inbox location for a content identity, not only the first copy.

## Immediate Next Task

Beacon 0.16 is merged to local `main`. Begin the next explicitly bounded intake
session and monitor durable progress, failures, and available storage.

---

## Current Hardware and Storage State

### Host Machine
- Windows desktop
- Intel Core i9 CPU
- 64 GB RAM
- MSI Tomahawk motherboard
- Four internal SATA archive drives
- Samsung 970 EVO Plus 500 GB NVMe boot drive
- Existing external 2 TB WD drive

### ATLAS Storage Pool
- StableBit DrivePool
- Pool drive: `J:`
- Approximate usable raw capacity: 15.5 TB
- Physical drives:
  - `ATLAS1` — 4 TB
  - `ATLAS2` — 4 TB
  - `ATLAS3` — 5 TB
  - `ATLAS4` — 4 TB
- Individual physical-drive letters may be hidden after pooling.
- DrivePool duplication is currently off.
- No parity layer has been configured yet.
- SMART reports were clean at setup:
  - zero reallocated sectors
  - zero pending sectors
  - zero uncorrectable sectors

### Network Access
- ATLAS is shared over SMB from Windows.
- Share name: `ATLAS`
- MacBook connects successfully as a registered user.
- Files copied from the Mac appear correctly on the Windows host.

---


## Development Environment

### Source Repository
The active Git repository should **NOT** live on the ATLAS storage pool.

Recommended location:

```text
C:\Development\ATLAS\
```

(or `C:\Code\ATLAS\`)

Reasoning:
- Faster Git operations on NVMe
- Faster dependency installation and builds
- Avoid coupling development with pooled storage
- Keeps source code independent of ATLAS maintenance

### Runtime State

During development, Beacon should keep its live runtime data on the local NVMe:

```text
C:\ProgramData\ATLAS\Beacon\
├── beacon.db
├── logs\
├── cache\
└── temp\
```

Beacon should periodically back up important runtime data to:

```text
J:\System\Backups\Beacon\
```

The ATLAS pool (`J:`) should primarily contain managed media, user assets, derivatives, and long-term system backups—not the active source repository.


## Core Design Principles

1. **ATLAS is the platform, not the disks.**
   The physical storage may change over time, but ATLAS remains the source of truth.

2. **Beacon is modular.**
   Beacon can be replaced, upgraded, or rebuilt without changing the underlying archive.

3. **Original files remain ordinary files.**
   Avoid proprietary lock-in. Metadata and intelligence should exist beside the files, not replace them.

4. **AI observes; it does not destructively alter originals.**

5. **Every file should eventually receive a permanent ATLAS identity.**
   Example:
   `atlas://asset/<uuid>`

6. **Everything entering the managed library should pass through a controlled intake workflow.**

7. **Storage reliability comes before intelligence features.**

8. **The architecture should support future commercialization.**
   ATLAS may eventually become a modular platform for production companies, agencies, and other organizations with large media libraries.

---

## Product Architecture

```text
ATLAS
├── Storage Layer
│   ├── StableBit DrivePool
│   ├── Physical disk monitoring
│   ├── Future parity or backup layer
│   └── SMB network access
│
├── Beacon
│   ├── Intake watcher
│   ├── Metadata extraction
│   ├── Media analysis
│   ├── Transcription
│   ├── Scene descriptions
│   ├── Embeddings
│   ├── Search
│   └── Retrieval
│
├── Database
│   ├── Permanent asset IDs
│   ├── File locations
│   ├── Checksums
│   ├── Metadata
│   ├── relationships
│   └── processing state
│
├── Interfaces
│   ├── Local web interface
│   ├── API
│   ├── CLI
│   ├── Obsidian integration
│   └── Future desktop or mobile client
│
└── Future Modules
    ├── MONO ingest
    ├── Sentinel drive-health monitoring
    ├── Courier synchronization
    ├── Forge proxy generation
    ├── Chronicle project history
    └── Client portal or remote access
```

---

## Proposed Root Folder Structure

The current DrivePool root is `J:\`.

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
├── Deliverables\
├── Beacon\
│   ├── Database\
│   ├── Metadata\
│   ├── Embeddings\
│   ├── Proxies\
│   ├── Thumbnails\
│   ├── Transcripts\
│   ├── Logs\
│   └── Quarantine\
└── System\
    ├── Config\
    ├── Manifests\
    └── Backups\
```

This structure is provisional. Successful analysis authorizes placement only
when established hierarchy makes the final home unambiguous; otherwise Beacon
must ask a focused clarification.

---

## Beacon Mental Model

Beacon is a librarian.

A user places files at Beacon's desk. Beacon then:

1. Detects the new file.
2. Waits until the copy is complete.
3. Calculates a checksum.
4. Assigns a permanent asset UUID.
5. Extracts technical metadata.
6. Determines the media type.
7. Creates derivatives such as thumbnails or proxies.
8. Transcribes spoken audio when applicable.
9. Generates scene descriptions and tags.
10. Creates embeddings for semantic search.
11. Writes all results to the database.
12. Moves or links the original into its approved library destination.
13. Records every operation in an audit log.

Beacon should never delete or overwrite an original without explicit user approval.

---

## Recommended Technology Direction

These are starting assumptions, not irreversible decisions.

### Core Service
- Python 3.12+
- FastAPI for the local API
- Pydantic for schemas and configuration
- Watchdog or a durable polling queue for filesystem intake
- SQLite for the first local version
- SQLAlchemy or SQLModel for database access
- Alembic for schema migrations

### Media Processing
- FFmpeg / ffprobe
- ExifTool
- OpenAI Whisper or a local Whisper implementation
- Scene detection through PySceneDetect
- Image/video embeddings through a CLIP-compatible model
- Optional local vision-language model later

### Search
- Start with SQLite full-text search for metadata and transcripts
- Add vector search after the basic catalog is dependable
- Keep the vector backend replaceable

### Interface
- Local-first web dashboard
- Simple API-first architecture
- Windows service or scheduled background process
- Do not require cloud access for core storage functions

---

## Safety Requirements

Codex must follow these rules during development:

- Do not format, initialize, partition, or modify physical disks.
- Do not alter DrivePool configuration.
- Do not delete source media.
- Do not move user files during early prototypes.
- Initial indexing must be read-only.
- Use test fixtures and a dedicated sandbox folder before operating on real media.
- Maintain detailed logs.
- Store secrets outside the repository.
- Never commit API keys or passwords.
- Use checksums before and after any future file operation.
- Make all destructive actions opt-in and reversible where possible.
- Treat network shares as potentially unavailable.
- Handle interrupted copies and partially written files safely.
- Avoid indexing DrivePool internal `PoolPart.*` folders directly.
- Operate only through the pooled `J:\` path unless specifically instructed otherwise.

---

## Development Phases

### Phase 0 — Repository and Documentation
- Create the Git repository.
- Add this handoff document.
- Add `README.md`.
- Add `ARCHITECTURE.md`.
- Add `ROADMAP.md`.
- Add `.env.example`.
- Add logging and configuration foundations.
- Define coding standards and test strategy.

### Phase 1 — Read-Only Catalog Prototype
Goal: Prove that Beacon can inspect files safely.

- Watch a dedicated test inbox.
- Detect completed file copies.
- Assign UUIDs.
- Calculate SHA-256 checksums.
- Extract basic filesystem metadata.
- Run ffprobe on supported media.
- Store records in SQLite.
- Provide CLI commands to list and inspect assets.
- Do not move or rename files.

### Phase 2 — Dashboard
- Local FastAPI service.
- Browser-based asset list.
- Search by filename, path, type, date, camera, codec, and duration.
- Processing status and error display.

### Phase 3 — Derivatives
- Generate thumbnails.
- Generate lightweight video proxies.
- Store derivatives separately from originals.
- Record derivative lineage in the database.

### Phase 4 — Transcription
- Transcribe audio and video.
- Store timecoded transcript segments.
- Add transcript search.

### Phase 5 — Visual Intelligence
- Scene detection.
- Sample representative frames.
- Generate scene descriptions and tags.
- Add visual similarity and semantic search.

### Phase 6 — Managed Intake
- Add approval-based organization suggestions.
- Add optional file moves only after extensive testing.
- Maintain permanent asset IDs across renames and moves.

### Phase 7 — Integrations
- MONO ingest.
- Obsidian notes.
- Notifications.
- Health monitoring.
- Remote or multi-user access.

### Phase 8 — Productization
- Authentication and permissions.
- Multi-tenant architecture analysis.
- Installer and update system.
- Hardware abstraction.
- Module marketplace or licensing model.
- Agency deployment tooling.

---

## Immediate First Sprint

Codex should begin with a small, safe vertical slice.

### Sprint Objective
Create a local Beacon prototype that catalogs files placed into a test folder without changing them.

### Suggested Test Paths
```text
J:\Beacon\TestInbox\
J:\Beacon\Database\beacon.db
J:\Beacon\Logs\
```

### Acceptance Criteria
- A file copied into `TestInbox` is detected only after its size stops changing.
- A stable UUID is assigned.
- A SHA-256 checksum is calculated.
- Basic metadata is stored in SQLite.
- Video and audio files receive ffprobe metadata.
- Duplicate files are recognized by checksum.
- Errors are logged without crashing the service.
- Restarting the service does not create duplicate asset records.
- No source file is renamed, moved, edited, or deleted.
- A CLI command can list indexed assets.
- Automated tests cover the core intake and duplicate-detection behavior.

---

## Questions Codex Must Resolve Before Expanding Scope

1. Repository location has been decided: keep the Git repository on the local NVMe (e.g. C:\Development\ATLAS\).
2. Should Beacon run as a Windows service, scheduled task, Docker container, or ordinary application during development?
3. How should interrupted network copies be detected reliably?
4. Which metadata belongs in SQLite versus sidecar JSON files?
5. How should asset identity survive renames and moves?
6. What is the backup strategy for the Beacon database?
7. What parity or backup layer will protect the underlying ATLAS files?
8. Which models should run locally, and which may use external APIs?
9. What privacy boundaries are required before indexing personal media?
10. Which folder conventions should be fixed versus user-configurable?

---

## Instructions for Codex

Start by inspecting the repository and this document.

Do not immediately build the entire system.

First:

1. Propose a repository structure.
2. Identify missing decisions and risks.
3. Write a concise implementation plan for Phase 0 and Phase 1.
4. Ask for approval before adding dependencies or creating services.
5. Build the smallest safe read-only prototype.
6. Keep all work modular and documented.
7. Favor boring, recoverable engineering over clever shortcuts.

The first successful milestone is not "AI search."

The first successful milestone is:

> Beacon can safely notice, identify, and catalog a file without harming it.
