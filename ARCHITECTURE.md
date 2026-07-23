# ATLAS Architecture

## Boundaries

- **Originals:** ordinary user files; Beacon opens them read-only.
- **Catalog:** SQLite facts about content and observed locations.
- **Derivatives:** verified thumbnails today; future proxies and transcripts;
  never originals.
- **Runtime:** local NVMe state under `C:\ProgramData\ATLAS\Beacon`.
- **Archive:** protected managed storage exposed through `J:\`.
- **Desktop:** native Qt Quick observation and recovery interface.
- **Beacon Desk:** durable local human/Beacon conversations and queue state;
  never a file-operation interpreter.
- **Archive Intake:** explicit, durable recursive catalog jobs; never an
  automatic production watcher or managed-move trigger.
- **API:** optional localhost-only integration adapter.

## Phase 1 flow

1. Poll a configured sandbox inbox from an ordinary foreground process.
2. Require matching size and modification time across stability observations.
3. Stream SHA-256 without modifying the file.
4. Derive a provisional UUIDv5 from the content hash.
5. Collect filesystem facts and optional `ffprobe` JSON.
6. upsert content and location records in one SQLite transaction.
7. Emit structured logs and expose list/inspect CLI commands.
8. For supported media, create a separate thumbnail atomically, verify and hash
   it, then record its source checksum and generator in schema 3.

Content identity and location identity are separate. The UUIDv5 rule makes
reprocessing deterministic, but remains provisional until edit/move/version
semantics are deliberately decided.

## Desktop and API

Beacon 0.9.0 is a foreground native Windows application built with Qt Quick/QML
and Qt Multimedia.
Python repository modules feed explicit Qt list models and properties; the
desktop client reads catalog facts directly and never becomes a second metadata
authority. Backup work runs outside the UI thread and only reports success
after SQLite integrity verification and SHA-256 calculation.

The Library reads thumbnail paths from the derivative ledger. A selected asset
can be opened in a modal temporary preview with Space. Images are fit to the
window; audio and video are decoded locally with native Qt playback; unsupported
formats receive a metadata-only safety view. Closing the preview stops playback.
No preview action opens an editor or writes to the observed path.

The Overview uses a master-detail Beacon Desk for persistent questions,
approval requests, blockers, clarifications, and human-started requests. A
plain-English reply is stored as a message and changes the thread to
`queued_for_beacon`; it cannot directly authorize or execute a file operation.
Beacon worker execution remains a separate, deliberate process.

Archive Intake snapshots an approved recursive source into schema-7 job and
item rows before work starts. A single background worker verifies the recorded
size and modified time, catalogs one regular non-link file, then commits that
item's result. Progress therefore survives UI refreshes and process restarts.
Cancel and app-close pauses are honored between files; retry resets only failed
items.

Human and Beacon-supplied context lives in revisioned `asset_metadata` records.
Those records are fully editable in Library and searchable, while source
checksums and probed technical facts remain immutable evidence. Metadata edits
do not write into source-media headers.

Managed moves are a separate policy-gated operation. Beacon requires an exact
catalog asset/location pair, re-hashes the source, restricts destinations to
approved ATLAS roots, refuses silent overwrite or duplicate merging, performs
an atomic same-volume rename, verifies the destination hash, and only then
updates the catalog location and audit ledger. A post-move failure triggers a
best-effort rollback.

The default double-click launch always opens the live catalog at
`C:\ProgramData\ATLAS\Beacon\beacon.db`. Custom and isolated use-test databases
must be supplied explicitly. The Library labels the active context as Live,
Isolated, or Custom and watches the database/WAL signature so externally
committed catalog updates appear without making a full integrity pass on every
timer tick.

The desktop application starts no web server, opens no browser, and listens on
no port. A separate FastAPI adapter remains available for local integrations
and development. It binds only to `127.0.0.1` and exposes health, summaries,
asset search/detail, events, and verified backup creation. It does not expose
arbitrary scan paths, file mutations, restore, or production-storage controls.

The Windows artifact is a windowed PyInstaller one-folder bundle using the
PySide6 Essentials and the selected Qt Multimedia runtime. This is easier to
diagnose than a one-file
executable, avoids temporary extraction on every launch, and excludes FastAPI,
Uvicorn, Pydantic, Qt WebEngine, and unrelated Qt Addons capabilities from the
desktop distribution. The entire distribution folder is the application.

## Safety

The scanner skips symlinks, reparse points, and non-files. Intake accepts only
an approved root, rejects changed snapshot items, and performs no move, rename,
write, or delete operation against observed paths. SQLite foreign keys, unique
constraints, and durable per-item states make retries idempotent.

Thumbnail output is written to a temporary file under the runtime derivative
tree, verified with FFprobe, hashed, and atomically placed before its database
record is committed. A derivative failure is visible in the operation ledger
and does not make catalog identity contingent on derivative success.

The native client has no network listener. The optional web server binds to
loopback only, validates the Host header, sends a strict Content Security
Policy, disables API caching, and requires an explicit custom header for backup
creation.
