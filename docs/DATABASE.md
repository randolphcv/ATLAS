# Database

Schema version 4 separates content, locations, derivatives, audit events, and
AI-generated candidates:

- `assets`: UUID, SHA-256, byte size, optional media metadata, timestamps.
- `locations`: path, modification timestamp, observation timestamp, asset link.
- `system_events`: catalog and backup outcomes with provenance.
- `derivatives`: verified thumbnails with source-checksum lineage.
- `analysis_runs`: analyzer/policy versions, execution location, external
  inference authorization, immutable manifest hash, scope, and run state.
- `analysis_results`: checksum-bound candidate payloads, evidence provenance,
  confidence, and human review state.
- `schema_version`: applied schema versions.

SHA-256 is unique in `assets`; paths are unique in `locations`. This recognizes
byte-identical duplicates while preserving every observed location.

AI results do not modify `assets.media_metadata_json`. Verified technical facts
and model output remain separate. An imported analysis manifest is atomic and
idempotent: every source checksum must still match the asset record, and the
manifest SHA-256 prevents duplicate runs. Results begin in `candidate` state;
organization suggestions do not execute file operations.

Connections use WAL mode, normal synchronous durability, foreign keys, and a
30-second busy timeout. Health checks run SQLite integrity and foreign-key
checks.

Backups use SQLite's online backup API, are written to a temporary file, checked
for integrity, atomically placed in the backup directory, and hashed with
SHA-256. Automatic deletion and restore are deliberately not implemented yet.
