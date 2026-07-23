# ATLAS — Project Memory and Decision Ledger

Updated: 2026-07-23  
Status: portable cross-machine handoff; verify live Windows state before treating recorded runtime details as current

Use this file for durable, low-noise context. Do not store raw logs, secrets, personal media content, full transcripts, or speculative brainstorming here.

## Current Verified/Reported Baseline

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

### Windows and Storage

- Host is a Windows desktop with an Intel Core i9, 64 GB RAM, and an MSI Tomahawk motherboard.
- An NVIDIA GeForce RTX 3060 with 12,288 MiB VRAM and driver 610.74 was
  observed through `nvidia-smi` on 2026-07-23; re-check before selecting or
  benchmarking local models.
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
10. Existing user files are not reorganized without explicit approval.

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
| Organization suggestions never execute file operations | Decided in Beacon 0.6.0 | Separate librarian advice from approval-based managed intake |
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

- Last verified: 2026-07-23 on the Windows ATLAS host
- Working branch/commit: `C:\Development\ATLAS`, branch `main`, Beacon 0.9.0 feature commit `72e27ea`, merged by `7166de8`
- Current milestone: resumable Archive Intake merged; bounded live-Inbox reliability pilot ready
- Verified complete: prior Desk, analysis-candidate, editable-metadata, and managed-move work; schema-7 deterministic recursive snapshots; item-level progress and attempts; changed-source rejection; cancel, pause, resume, failure-only retry, and interrupted-session recovery; native Overview master-detail intake controls; packaged Beacon 0.9.0 release
- In progress: no production intake is running; the prior verified post-move Inbox inventory remains 7,092 files and 744,696,445,768 bytes
- Blocked: nothing blocks the bounded 25-file pilot; full-corpus expansion remains gated on pilot verification, and asset-specific destinations still require verified or editable context
- Files changed: merged repository under `C:\Development\ATLAS`; release bundle under `C:\Development\ATLAS\dist\releases\0.9.0\ATLAS Beacon`; ZIP package under `C:\Development\ATLAS\dist`; verified pre-schema-7 recovery copy under `C:\ProgramData\ATLAS\Beacon\backups`; portable documentation under `J:\System\Documentation\ATLAS\`
- Tests/live checks: Python compilation and 52/52 tests passed with real FFprobe and FFmpeg; exact packaged 0.9.0 rendered a complete three-file nested synthetic intake with source hashes unchanged; synthetic database healthy at schema 7 with zero foreign-key errors; bundle contains 1,748 files and 178,196,704 bytes with zero blocked capabilities; executable SHA-256 `1BC9B4E5376537FC46B0DBC714ED6DC3A50D3E059F74F3800EFFE5C81BE262FB`; package SHA-256 `A2905C2AFAC3D129E63927E8E61DFD178D8179C1C306F870D751AB2F77D4F790`; first packaged 0.9.0 launch migrated the live database cleanly to healthy schema 7 with zero intake jobs; verified pre-schema-7 backup `beacon-pre-schema7-20260723T192234.940229Z.db` SHA-256 `f66387248420bb7c3b2b1ff4d7e9a0b5c8cc8ee3358c05921dbd08fec614ca57`
- Unverified assumptions: current post-transfer Inbox stability, physical SMART state, current DrivePool duplication/parity state, independent archive backup strategy, production throughput, database restore/retention policy, code-signing strategy, local model choices and measured RTX 3060 throughput, external-model cost/authorization, face-analysis policy, rights taxonomy, and canonical sidecar-versus-SQLite metadata policy
- Next smallest step: run the 25-file `J:\Inbox` pilot from Beacon 0.9.0, exercise cancel/resume, verify catalog/database/source evidence, then stop for review before any full-Inbox or AI-analysis expansion
