# Database

Schema version 2 separates content, locations, and audit events:

- `assets`: UUID, SHA-256, byte size, optional media metadata, timestamps.
- `locations`: path, modification timestamp, observation timestamp, asset link.
- `system_events`: catalog and backup outcomes with provenance.
- `schema_version`: applied schema versions.

SHA-256 is unique in `assets`; paths are unique in `locations`. This recognizes
byte-identical duplicates while preserving every observed location.

Connections use WAL mode, normal synchronous durability, foreign keys, and a
30-second busy timeout. Health checks run SQLite integrity and foreign-key
checks.

Backups use SQLite's online backup API, are written to a temporary file, checked
for integrity, atomically placed in the backup directory, and hashed with
SHA-256. Automatic deletion and restore are deliberately not implemented yet.
