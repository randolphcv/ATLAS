# Database

Schema version 14 separates content, locations, derivatives, audit events,
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
- `beacon_worker_runs`: loopback model provenance, exactly-once thread lease,
  completion state, and failure evidence for conversational work.
- `beacon_message_assets`: ranked grounded catalog assets and match reasons
  attached to a specific Beacon message.
- `beacon_policies`: structured operational policy with source provenance.
- `asset_metadata`: the current editable contextual metadata revision for an
  asset identity.
- `asset_metadata_revisions`: immutable history of every contextual edit.
- `managed_moves`: exact source/destination, checksum, authorization, state,
  completion, and failure evidence for each managed move.
- `intake_jobs`: approved root, mode, durable state, snapshot SHA-256, scoped
  totals, current path, cancellation flag, and lifecycle timestamps.
- `intake_items`: per-job source stat evidence, attempt count, progress state,
  cataloged asset identity, error, and completion timestamps.
- `local_analysis_jobs`: local endpoint/model, frozen checksum scope, durable
  lifecycle, progress, cancellation, current truthful pipeline stage, and the
  resulting candidate run.
- `local_analysis_items`: one restartable item per asset, with source checksum,
  attempts, validated candidate JSON, and failure evidence.
- `asset_transcripts`: full local transcript text, text SHA-256, source
  checksum, language, generator, and verification timestamps.
- `asset_music_analysis`: checksum-bound local BPM, key, chord, note, and stem
  results with canonical result hashes and worker provenance.
- `schema_version`: applied schema versions.

SHA-256 is unique in `assets`; paths are unique in `locations`. This recognizes
byte-identical duplicates while preserving every observed location.

AI results do not modify `assets.media_metadata_json`. Verified technical facts
and model output remain separate. An imported analysis manifest is atomic and
idempotent: every source checksum must still match the asset record, and the
manifest SHA-256 prevents duplicate runs. Results begin in `candidate` state.
After successful local analysis, an unambiguous Inbox hierarchy may trigger the
separate verified managed-move operation.

Beacon Desk threads use four explicit states: `awaiting_human`,
`queued_for_beacon`, `resolved`, and `closed`. A human reply appends a message
and queues the thread for Beacon. It never parses conversational text into a
file operation or marks the thread resolved. Resolution is a separate explicit
action.

Editable metadata is asset-level and follows the permanent asset UUID across
locations. Verified `assets`, probe metadata, checksums, and derivative lineage
remain separate and are not edited through the contextual form.

Intake snapshots are immutable scopes. A job retries by changing only item
state and attempts; it does not rewrite the recorded source path, size, modified
time, or snapshot signature. Completed items stay complete across cancellation,
pause, retry, app shutdown, and crash recovery.

Local analysis jobs freeze asset IDs and catalog checksums before execution.
Interrupted running items recover as pending. Completed results pass through
the same atomic checksum-bound candidate import used by explicit manifests.
Full transcripts are cached against the asset and source SHA-256 so later
metadata-only analysis does not repeat unchanged speech transcription.

Schema 13 adds nullable `current_stage` and `current_stage_updated_at` to
`local_analysis_jobs`. The current filename is derived from
`current_asset_id` and the checksum-bound analysis item rather than duplicated
on the job. Recovery, cancellation, retry, and terminal completion clear the
active stage and asset while preserving the time of that boundary.

Schema 14 adds durable conversation-worker claims and message-linked grounded
asset cards. Conversation results retain permanent asset IDs while the UI
resolves the current preferred location at read time.

Connections use WAL mode, normal synchronous durability, foreign keys, and a
30-second busy timeout. Health checks run SQLite integrity and foreign-key
checks.

Backups use SQLite's online backup API, are written to a temporary file, checked
for integrity, atomically placed in the backup directory, and hashed with
SHA-256. Automatic deletion and restore are deliberately not implemented yet.
