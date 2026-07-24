# Changelog

## Unreleased

- Replaced Beacon's phrase-triggered conversation router with a bounded
  Qwen-authored goal and iterative read-only catalog-agent loop.
- Qwen now decides intent, count, media type, constraints, search/refinement,
  inspection, clarification, final wording, and selected result cards.
- Added broader candidate discovery and lightweight filename-series signals so
  requests for unique results do not default to adjacent captures from one
  burst or setup.
- Added a focused Qwen composition pass that attaches only model-selected,
  previously observed asset IDs and honors the model-authored result count.
- Added durable audit events for every agent tool step, structured-output
  retry, a 16K local context window, and hard rejection of invented result IDs.
- Thread-scoped correction memory is now identified by Qwen from the active
  human turn instead of a fixed phrase list.
- Retained hard local safety boundaries: loopback inference only, bounded
  history/steps/results, read-only catalog search and inspection, no generic
  filesystem or mutation tool, and hidden live test/sandbox paths.
- Added schema-14 durable conversational-worker leases and run history with a
  hard pause while catalog analysis owns the local inference lane.
- Added message-linked grounded catalog result cards whose only native action
  is to inspect the permanent asset identity in Library.
- Added a native folder picker for custom intake batches; the selected folder
  is snapshotted recursively with the same approved-root and file-limit gates.
- Added schema-13 truthful durable catalog-analysis pipeline stages, including
  active checksum-bound filenames and accurate recovery/cancel/terminal state.
- Added the compact application-shell Beacon conversation dock using the
  existing local Beacon Desk threads and messages. Its draft and scroll state
  survive page navigation, and page/asset context attaches only explicitly.
- Expanded the catalog-operations card when analysis status is present so its
  intake controls and snapshot identifier remain inside the card boundary.
- Catalog analysis now continues after individual asset failures, and its
  durable Cancel and Retry controls operate on the latest analysis job.
- Overview failure counts now report retryable failures in the latest intake
  and analysis jobs instead of mixing them with lifetime audit history.
- Added an isolated Python 3.11 music runtime with CUDA-enabled Demucs,
  ONNX-backed Basic Pitch, and librosa tonal/rhythm analysis.
- Added schema-12 checksum-bound music results and verified MIDI/stem
  derivatives, with a conservative gate that skips expensive models for
  speech and other weakly tonal audio.
- Added Music Intelligence detail UI for confidence, BPM, estimated key,
  chord path, pitch range, prominent notes, and generated stems.
- Added schema-11 checksum-bound full transcripts, cached across later
  metadata analysis passes.
- Added waveform plus transcript audio previews and a full transcript section
  in the scrollable asset record.
- Successful local analysis now commits files with unambiguous Inbox hierarchy
  through the existing verified managed-move boundary; only unclear placement
  creates a clarification, and operating-system metadata is ignored.
- Expanded local visual analysis to six timeline samples and detailed
  stock/B-roll metadata.
- Added local faster-whisper speech transcription and full-file spectrogram
  context for meaningful audio analysis.
- Added schema-9 field authority so reanalysis refreshes AI-owned editable
  metadata while preserving human-edited fields.
- Reanalysis scope now selects all existing catalog assets without a
  hard-coded count.
- Added a native Analyze Catalog scope-and-policy dialog with explicit local
  runtime readiness, installed-model selection, and no cloud fallback.
- Added schema-8 restartable local analysis jobs and per-asset items.
- Routed completed local results through checksum-bound candidate import with
  model, endpoint, policy, scope, confidence, and input provenance.
- Supplied verified technical metadata, path context, and verified local
  thumbnails to the local adapter while keeping originals unchanged.
- Normalize local-model percentage-style confidence values to the candidate
  0–1 scale with explicit provenance, and insert a non-operative fallback when
  an organization suggestion is structurally empty.
- Established the canonical NVMe repository.
- Added the standard-library Beacon read-only catalog prototype.
- Added synthetic acceptance tests and operational documentation.
- Added foreground synthetic-inbox watching and retained operational logs.
- Verified generated WAV/MP4 metadata through FFprobe.
- Verified duplicate, restart, partial-copy, unavailable-path, and corrupt-media behavior.
- Added schema version 2 with a visible audit-event ledger.
- Added loopback-only FastAPI health, catalog, event, and backup APIs.
- Added verified online SQLite backups with atomic placement and SHA-256.
- Added the branded ATLAS Beacon archive dashboard.
- Added a reproducible PyInstaller Windows application bundle.
- Replaced the primary browser dashboard with a native Qt Quick desktop client.
- Added native archive navigation, master-detail inspection, and system views.
- Moved verified backup execution off the UI thread.
- Removed browser launch, network listeners, and web dependencies from the
  packaged desktop runtime while retaining the API as an optional adapter.
- Added explicit JPEG/PNG/TIFF/WebP image probing after the first real use test.
- Preserved still-image identity and dimensions without displaying FFprobe's
  synthetic single-frame duration.
- Added schema version 3 with verified, hashed thumbnail-derivative lineage.
- Added idempotent FFmpeg thumbnails for images, video frames, and audio
  waveforms without editing source files.
- Added native Finder-style Space previews with image fit, audio/video playback
  controls, and safe metadata fallback for other file types.
- Added Qt Multimedia to the native bundle while explicitly excluding browser,
  3D, charting, PDF, and virtual-keyboard capabilities.
- Verified Beacon 0.4.0 source and frozen previews against the isolated
  UseTest-01 copies while retaining byte-identical ATLAS sources.
- Corrected the standalone-launch catalog mismatch exposed after 0.4.0:
  verified media had remained in the isolated use-test database while the
  double-clickable app correctly opened its separate live database.
- Backed up the live catalog, cataloged the approved NVMe copies into it, and
  verified the exact no-argument packaged launch shows all expected assets.
- Added explicit Live/Isolated/Custom catalog labels and lightweight automatic
  refresh when the SQLite database or WAL changes.
- Added regression coverage for catalog labeling and externally written catalog
  updates, bringing the suite to 22 tests.
- Added bounded, read-only plain-text previews with common UTF and Windows
  encoding detection, binary rejection, and a 512 KB display cap.
- Promoted Space to an application-level preview shortcut, prevented mouse
  clicks from trapping focus on action buttons, and added a real Qt regression
  test for the focused-button case.
- Added a larger selected-asset thumbnail to the detail header with a branded
  extension tile for files without media derivatives.
- Verified Beacon 0.5.0 source and packaged behavior against the five-asset
  live catalog, bringing the complete suite to 27 tests.
- Added schema version 4 with immutable, checksum-bound analysis runs and
  candidate results stored separately from verified catalog facts.
- Added idempotent analysis-manifest import with explicit analyzer, policy,
  execution-location, external-inference authorization, confidence, evidence,
  privacy, and review-state fields.
- Added native Beacon Analysis detail cards and search across candidate titles,
  descriptions, and tags while keeping every organization path advisory.
- Completed a five-asset Beacon librarian pilot without scanning the active
  ATLAS inbox or modifying an original.
- Added schema version 5 with durable Beacon Desk threads and ordered messages.
- Added a native Overview-page conversation queue for Beacon questions,
  approval requests, blockers, clarifications, and human-started requests.
- Added plain-English replies, explicit resolution, and honest local queue
  states without interpreting conversation text as permission for file actions.
- Seeded the pilot's three verified scale-up gates separately from three
  optional enrichment conversations.
- Added schema version 6 with structured Beacon policies, revisioned editable
  asset metadata, immutable metadata history, and managed-move records.
- Added a native Library metadata editor covering human titles, descriptions,
  categories, tags, people, dates, places, clients, projects, rights, notes,
  and approved organization directories.
- Added search and display-title support for editable metadata without changing
  verified technical facts or embedded source-media metadata.
- Added policy-gated, same-volume managed moves with exact observed-location
  checks, source/destination SHA-256 verification, approved-root enforcement,
  reparse rejection, non-overwrite behavior, audit events, and rollback.
- Reconciled all six pilot Desk replies, verified a stable 7,093-file Inbox
  snapshot, and completed one real catalog-to-managed-location proof.
- Added schema version 7 with durable recursive intake jobs and item-level
  progress, attempts, errors, snapshot signatures, and source stat evidence.
- Added native Overview controls to prepare a bounded or complete Inbox
  snapshot, start or resume it, cancel between files, and retry only failures.
- Added startup recovery that returns interrupted work to a visible paused
  state without repeating completed files.
- Kept intake catalog-only: no automatic watcher, move, delete, or source-file
  edit is introduced.
