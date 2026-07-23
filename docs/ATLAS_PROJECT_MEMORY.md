# ATLAS — Project Memory and Decision Ledger

Updated: 2026-07-22  
Status: initial portable context; verify on the Windows host before treating hardware or runtime details as current

Use this file for durable, low-noise context. Do not store raw logs, secrets, personal media content, full transcripts, or speculative brainstorming here.

## Current Verified/Reported Baseline

### Identity

- Project: **ATLAS — Adaptive Topological Library & Archive System**
- AI librarian: **Beacon**
- Mission: preserve, organize, and make searchable Connor's creative archive.
- Core boundary: AI observes and catalogs; it does not own or destructively alter originals.

### Windows and Storage

- Host is a Windows desktop with an Intel Core i9, 64 GB RAM, and an MSI Tomahawk motherboard.
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

Phase 0 foundations and the Phase 1 synthetic read-only catalog milestone are
verified complete. Production-path indexing remains deliberately unapproved.

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

## Decisions Still Open

Do not silently resolve these:

- development run mode: ordinary app, scheduled task, Windows service, or container;
- exact copy-stability algorithm and time thresholds;
- metadata split between SQLite and sidecar files;
- asset identity rules across moves, renames, edits, and true duplicates;
- independent backup/parity strategy for original media;
- database backup schedule, retention, restore test, and integrity checks;
- privacy zones and default indexing exclusions;
- which AI models are local versus optional external adapters;
- which root conventions are fixed versus configurable;
- whether derivatives live only under `J:\Beacon\` or may be colocated by policy;
- terminology and state-machine names for intake jobs;
- initial UI reference model and final ATLAS visual tokens.

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

Last verified: 2026-07-22 on the Windows ATLAS host  
Working branch/commit: `C:\Development\ATLAS`, branch `main`, verified implementation commit `802e788`  
Current milestone: Phase 1 synthetic read-only catalog complete  
Verified complete: canonical NVMe Git repository; foreground watcher; stability observation; SHA-256; deterministic provisional asset UUID; SQLite schema; content/location duplicate handling; restart idempotency; CLI init/add/scan/watch/list/inspect; structured logs; FFprobe WAV/MP4 metadata; corrupt-media and FFprobe-timeout handling; safe unavailable-path behavior  
In progress: none  
Blocked: production pilot requires an exact approved sandbox/path and stability policy  
Files changed: repository under `C:\Development\ATLAS`; synthetic acceptance runtime under `C:\ProgramData\ATLAS\Beacon\acceptance-20260722-231828`; this portable handoff  
Tests/live checks: Python compilation passed; 10/10 tests passed; two independent watcher processes passed; database integrity `ok`; four content assets and five locations; H.264 and PCM metadata verified; unavailable path exited 1 safely; all fixture hashes matched before and after; log matched no common secret patterns  
Unverified assumptions: physical SMART state, current DrivePool duplication/parity state, independent backup strategy, real-world copy pause behavior, production stability thresholds, and database backup/restore policy  
Next smallest step: design the Phase 2 hardening slice—database backup/restore plus a local job/status API—while keeping any real-media pilot separately scoped and explicitly approved
