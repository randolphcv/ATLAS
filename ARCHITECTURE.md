# ATLAS Architecture

## Boundaries

- **Originals:** ordinary user files; Beacon opens them read-only.
- **Catalog:** SQLite facts about content and observed locations.
- **Derivatives:** future thumbnails, proxies, and transcripts; never originals.
- **Runtime:** local NVMe state under `C:\ProgramData\ATLAS\Beacon`.
- **Archive:** protected managed storage exposed through `J:\`.
- **Desktop:** native Qt Quick observation and recovery interface.
- **API:** optional localhost-only integration adapter.

## Phase 1 flow

1. Poll a configured sandbox inbox from an ordinary foreground process.
2. Require matching size and modification time across stability observations.
3. Stream SHA-256 without modifying the file.
4. Derive a provisional UUIDv5 from the content hash.
5. Collect filesystem facts and optional `ffprobe` JSON.
6. upsert content and location records in one SQLite transaction.
7. Emit structured logs and expose list/inspect CLI commands.

Content identity and location identity are separate. The UUIDv5 rule makes
reprocessing deterministic, but remains provisional until edit/move/version
semantics are deliberately decided.

## Desktop and API

Beacon 0.3.0 is a foreground native Windows application built with Qt Quick/QML.
Python repository modules feed explicit Qt list models and properties; the
desktop client reads catalog facts directly and never becomes a second metadata
authority. Backup work runs outside the UI thread and only reports success
after SQLite integrity verification and SHA-256 calculation.

The desktop application starts no web server, opens no browser, and listens on
no port. A separate FastAPI adapter remains available for local integrations
and development. It binds only to `127.0.0.1` and exposes health, summaries,
asset search/detail, events, and verified backup creation. It does not expose
arbitrary scan paths, file mutations, restore, or production-storage controls.

The Windows artifact is a windowed PyInstaller one-folder bundle using the
PySide6 Essentials runtime. This is easier to diagnose than a one-file
executable, avoids temporary extraction on every launch, and excludes FastAPI,
Uvicorn, Pydantic, and Qt WebEngine from the desktop distribution. The entire
distribution folder is the application.

## Safety

The scanner skips symlinks and non-files. It performs no move, rename, write, or
delete operation against observed paths. SQLite foreign keys and unique
constraints make retries idempotent.

The native client has no network listener. The optional web server binds to
loopback only, validates the Host header, sends a strict Content Security
Policy, disables API caching, and requires an explicit custom header for backup
creation.
