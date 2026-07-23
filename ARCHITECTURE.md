# ATLAS Architecture

## Boundaries

- **Originals:** ordinary user files; Beacon opens them read-only.
- **Catalog:** SQLite facts about content and observed locations.
- **Derivatives:** future thumbnails, proxies, and transcripts; never originals.
- **Runtime:** local NVMe state under `C:\ProgramData\ATLAS\Beacon`.
- **Archive:** protected managed storage exposed through `J:\`.
- **API/dashboard:** localhost-only observation and recovery interface.

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

## Dashboard and API

Beacon 0.2.0 is a foreground Windows application that serves FastAPI and static
dashboard assets on `127.0.0.1`. The current API exposes health, summaries,
asset search/detail, events, and verified backup creation. It does not expose
arbitrary scan paths, file mutations, restore, or production-storage controls.

The browser is a replaceable local client. Catalog and backup logic remain in
Python modules behind the API so future desktop, mobile, or integration clients
do not become metadata authorities.

The Windows artifact is a PyInstaller one-folder bundle. This is easier to
diagnose than a one-file executable and avoids temporary extraction on every
launch. The entire distribution folder is the application.

## Safety

The scanner skips symlinks and non-files. It performs no move, rename, write, or
delete operation against observed paths. SQLite foreign keys and unique
constraints make retries idempotent.

The web server binds to loopback only, validates the Host header, sends a strict
Content Security Policy, disables API caching, and requires an explicit custom
header for backup creation.
