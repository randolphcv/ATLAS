# Database

Schema version 6 separates content, locations, derivatives, audit events,
AI-generated candidates, durable Beacon conversations, editable context, and
managed file operations:

- `assets`: UUID, SHA-256, byte size, optional media metadata, timestamps.
- `locations`: path, modification timestamp, observation timestamp, asset link.
- `system_events`: catalog and backup outcomes with provenance.
- `derivatives`: verified thumbnails with source-checksum lineage.
- `analysis_runs`: analyzer/policy versions, execution location, external
  inference authorization, immutable manifest hash, scope, and run state.
- `analysis_results`: checksum-bound candidate payloads, evidence provenance,
  confidence, and human review state.
- `beacon_threads`: subject, conversation kind, priority, explicit queue state,
  approval flag, optional asset link, and timestamps.
- `beacon_messages`: ordered Beacon, human, and system messages attached to a
  durable thread.
- `beacon_policies`: structured operational policy with source provenance.
- `asset_metadata`: the current editable contextual metadata revision for an
  asset identity.
- `asset_metadata_revisions`: immutable history of every contextual edit.
- `managed_moves`: exact source/destination, checksum, authorization, state,
  completion, and failure evidence for each managed move.
- `schema_version`: applied schema versions.

SHA-256 is unique in `assets`; paths are unique in `locations`. This recognizes
byte-identical duplicates while preserving every observed location.

AI results do not modify `assets.media_metadata_json`. Verified technical facts
and model output remain separate. An imported analysis manifest is atomic and
idempotent: every source checksum must still match the asset record, and the
manifest SHA-256 prevents duplicate runs. Results begin in `candidate` state;
organization suggestions do not execute file operations.

Beacon Desk threads use four explicit states: `awaiting_human`,
`queued_for_beacon`, `resolved`, and `closed`. A human reply appends a message
and queues the thread for Beacon. It never parses conversational text into a
file operation or marks the thread resolved. Resolution is a separate explicit
action.

Editable metadata is asset-level and follows the permanent asset UUID across
locations. Verified `assets`, probe metadata, checksums, and derivative lineage
remain separate and are not edited through the contextual form.

Connections use WAL mode, normal synchronous durability, foreign keys, and a
30-second busy timeout. Health checks run SQLite integrity and foreign-key
checks.

Backups use SQLite's online backup API, are written to a temporary file, checked
for integrity, atomically placed in the backup directory, and hashed with
SHA-256. Automatic deletion and restore are deliberately not implemented yet.
