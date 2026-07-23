# ATLAS Architecture

## Boundaries

- **Originals:** ordinary user files; Beacon opens them read-only.
- **Catalog:** SQLite facts about content and observed locations.
- **Derivatives:** future thumbnails, proxies, and transcripts; never originals.
- **Runtime:** local NVMe state under `C:\ProgramData\ATLAS\Beacon`.
- **Archive:** protected managed storage exposed through `J:\`.

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

## Safety

The scanner skips symlinks and non-files. It performs no move, rename, write, or
delete operation against observed paths. SQLite foreign keys and unique
constraints make retries idempotent.
