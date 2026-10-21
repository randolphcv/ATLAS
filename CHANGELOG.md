# Changelog

## Unreleased

## 0.22.16 - 2026-10-20

- Settling the Inbox no longer scans the whole analysis-item history once per
  file. The step asks the catalog what terminal state each candidate holds,
  and the only index on that table led with the job identifier, so the
  question could not be answered by a seek and fell back to a full scan of
  every item ever enrolled. On a live catalog that was roughly a hundred
  million row reads before the first file moved, and a scoped drain sat for
  eleven minutes looking as though it had stalled. An index leading with the
  asset identifier and carrying the completion timestamp makes each lookup a
  seek and serves the ordering without a sort, which takes the catalog to
  schema 18.
- The defect was correctness-neutral and invisible to every test that
  existed, because a full scan of a six-row fixture table is instant. The
  guard added for it asserts the query plan rather than a duration: a timing
  assertion would be unreliable on a loaded volume, while the plan names the
  defect exactly and fails as soon as the index stops covering the lookup.

## 0.22.15 - 2026-10-20

- The Inbox now means one thing: not yet looked at. Every item an analysis job
  reaches a terminal state on leaves the Inbox in the same operation, to a
  final destination or to one of three bounded holding zones beneath the
  archive root — `Holding\Cache` for regenerable generated artifacts,
  `Holding\Review` for items whose analysis failed, and
  `Holding\Unidentified` for items no placement rule derives a destination
  for. Material that belongs together stays together: an editable project
  file and the camera index beside it follow their media into the same folder
  rather than being separated by class, and relative structure beneath the
  Inbox is reproduced verbatim beneath every destination, holding zones
  included. Until now a human could not tell by looking whether anything in
  the Inbox had been analysed, because analysed, excluded, failed and
  untouched material all sat in it together.
- A single failed item no longer stops the Inbox from draining. Placement was
  gated on the job having zero failed and zero pending items, so one model
  error skipped the move for every other item in that job; the Inbox had been
  accumulating looked-at material behind such failures across many jobs. This
  was a fourth instance of the per-item-failure-aborts-the-batch pattern that
  the engineering rules already forbid. A failed item is now settled to the
  review zone and strands nobody, and a retry resolves it by its catalog
  location rather than by the Inbox path it was enrolled from, so holding an
  item for review does not make it unretryable.
- Placement no longer requires a file already analysed in the destination tree
  before it will move anything there. That requirement was circular — nothing
  could leave the Inbox until something had already left it — so a folder
  whose media was never placed stayed full indefinitely. The destination is
  derived from the path beneath the Inbox, which the structure rule requires be
  preserved verbatim in any case, so the requirement added no safety.
- Editable production project files are now enrolled rather than filtered out
  before a job sees them. An item that never enrols receives no record, no
  reason and no terminal state, so nothing could ever move it and it sat in
  the Inbox indefinitely. They are still never sent to the model: exclusion is
  decided when the item is picked up, before any analysis, so enrolment costs
  no model time and buys them a recorded reason and a destination.
- The scope guard from 0.22.12 is unchanged and now covers the new step. A job
  whose scope enrols only regenerable artifacts still moves nothing at all,
  settle included, and the analysis dialog still says so; it now states the
  consequence for the clearing rule in the other direction too, that the job
  moves everything it analyses to a final destination or a holding zone.
  Regenerable artifacts are still never placed into the archive proper,
  whichever scope enrolled them — they leave the Inbox for the cache holding
  zone instead, because cache that has been classified has been looked at.

## 0.22.14 - 2026-10-20

- The version stamped into the packaged executable is now generated from the
  package version instead of being maintained by hand. The Windows version
  resource was the only thing that labelled the binary, and it declared the
  version four more times — as two numeric tuples and two dotted strings — in
  a file nothing generated and nothing checked, so a release could carry new
  code under an old label. That is how 0.22.5 through 0.22.7 shipped, and
  0.22.12 came within one step of repeating it, caught only because the
  implementer happened to read the file before building rather than after. A
  single generator now renders the resource from the package version, and the
  build writes it before PyInstaller reads it and refuses to continue if what
  it wrote does not declare the version being built. Every field that
  identifies the product rather than the release is a constant in that
  generator, so nothing a release touches can move them.
- The generated resource is no longer tracked, which removes the last way the
  stamp could go stale. It is written beside the generated icon, under the
  same ignore rule and consumed by the spec the same way, so the packaging
  configuration did not have to change to accommodate it. A tracked copy would
  have left a file that a commit could carry forward unchanged while the
  source version moved, which is the defect being closed rather than a smaller
  version of it. Untracking it also returns the legal attribution to a single
  tracked home in the generator, where the instance-data allow-list justifies
  it.
- A new guard fails the suite when the version declarations disagree. It
  compares the package version against the one in the project metadata and
  against every declaration in the resource the generator produces, in the
  numeric form as well as the dotted one, because a correct string beside a
  stale tuple is still the version Windows reports. It writes the resource the
  way the build does rather than reading whatever a previous build left
  behind, counts the declarations so a fifth one cannot appear unnoticed,
  pins the product identity fields and the legal attribution, and checks that
  the file the generator writes is the file the spec stamps and that the build
  writes it before packaging — a guard aimed at a file the build no longer
  uses would guard nothing.

## 0.22.13 - 2026-10-20

- The analysis dialog now opens on General rather than Total, and resetting it
  on each opening returns it to General instead of Total. Total means
  whole-catalog analysis with managed placement active, so opening on it made
  the broadest, file-moving scope the default outcome of clicking through the
  dialog: an operator who intended to analyze one folder could start a
  whole-catalog job without choosing anything. The reset itself is kept,
  because a stale category selection could otherwise show one category while
  the job ran another, and Total remains a single click away.
- The folder field that confines a job to one path is now proven reachable in
  both modes that honour it. General and Total both pass the prefix through to
  job creation, Granular analyzes one selected asset and ignores it, and the
  dialog's surface tests now assert that visibility mode by mode, so a prefix
  can no longer become honoured by the job but untypeable in the dialog.
- The dialog now states the placement consequence for every mode and scope
  rather than only for generated cache artifacts. It says either that the job
  may move originals out of the Inbox into the archive, or that the job moves
  nothing, and which one it says is derived from the placement rule the run
  itself applies: the placement-free scope kinds and the scope kind each mode
  creates its job with both come from the controller, so the surface holds no
  second copy of the rule that could drift from the job. An operator no longer
  has to infer whether a job can move files.

## 0.22.12 - 2026-10-20

- Analysis job creation now accepts an optional path prefix, so a job can be
  confined to one folder instead of covering every matching asset in the
  catalog. Scope was previously expressible only by media kind, which meant a
  single ingest could not be analyzed on its own and the only targeted path was
  an explicit asset selection capped at a thousand items. The prefix composes
  with every existing scope kind, matches the catalog's stored path
  case-insensitively, and reuses the archive tier's own prefix helper, so a
  prefix written with or without a trailing separator selects the same assets
  and an underscore in a folder name is matched literally rather than as a
  wildcard.
- A new `artifacts` scope enrols only the regenerable generated cache that the
  repository's support-path rule already recognizes, and a structural guard
  stops such a job from moving anything. Completing analysis authorizes managed
  placement, and a run moves files at two sites: the placement of each analyzed
  candidate, and an Inbox-wide companion sweep that is not scoped to the job at
  all and would have moved the very files the job marked excluded. Cache items
  previously avoided placement only because exclusion happened to short-circuit
  first, which was incidental rather than a guarantee. The scope kind is now
  recorded on the job, both sites read that one answer, and a second check
  refuses to place a generated artifact whatever scope enrolled it, so clearing
  cache from an ingest leaves every original where it is.

## 0.22.11 - 2026-10-19

- The Desk seed threads and the conversation and catalog test fixtures no
  longer carry deployment names. Shipped application source and test fixtures
  held real client, personal, place and archive-filename values, which a
  repository must never record, so each one is replaced with a synthetic value
  that could not occur in a real archive. The fixtures still prove what they
  proved before: distinct people remain distinct tokens, the exact-filename
  retrieval still has a same-suffix neighbour to discriminate against, and the
  transcript search still matches a multi-word phrase.
- The packaged executable's copyright attribution now names the business
  entity rather than an individual. The notice is compiled into the delivered
  executable's metadata, so the personal name travelled with every build; the
  entity name is the correct holder and keeps the attribution out of the class
  of personal data the repository excludes.

## 0.22.10 - 2026-10-19

- The desktop window no longer freezes while a job runs. A repeating five-second
  refresh on the UI thread was doing roughly twenty-seven seconds of work per
  pass, so it re-entered as soon as it returned and the window stopped pumping
  messages for minutes at a time. The library query now selects a page of
  identifiers before projecting the expensive per-row columns, and a correlated
  lookup that SQLite was resolving through a near-useless index is steered onto
  the selective one. That query drops from 24.1s to 0.35s on a catalog of
  17,829 assets, with byte-identical results.
- The catalog integrity check leaves the refresh path. `PRAGMA integrity_check`
  and `foreign_key_check` read every page of the catalog; they now run at
  startup and on explicit request from the System view, never on a timer, and
  they open the catalog read-only so a diagnostic cannot alter what it inspects.
- Catalog change detection uses `PRAGMA data_version` on a long-lived read-only
  connection instead of database and write-ahead-log file metadata, and a
  refresh already in flight is not re-entered.
- The second model-output gate now degrades instead of discarding. An analysis
  whose only fault is an over-long field is kept and corrected rather than
  failing the item after three full generations; the request schema also states
  the field limits, and a repeat violation degrades after one corrective retry
  rather than a third.
- Camera media-index and generated editor-index files are excluded from
  analysis scope as non-media companions, and presentation documents under a
  distinct reason marking them deferred pending text extraction. Excluded items
  are recorded complete rather than failed, which is also how companion
  placement selects them to travel with their originals.
- A catalog checksum that drifted between scoping and analysis now fails only
  its own item. The drift check was raised outside the per-item boundary, so a
  single asset whose catalog identity had changed since the job was scoped
  terminalized the entire job and discarded the remaining work. It is now
  recorded as a per-item failure carrying the same reason, and the batch
  continues to the next asset.

## 0.22.9 - 2026-08-24

- Local model output is now treated as an untrusted input source. An over-limit
  or wrong-shaped field is retried, then corrected rather than failing the item,
  and every correction is written to the item record and the audit ledger. An
  over-long tag entry is dropped whole and its valid siblings kept; over-long
  prose is truncated. Human edits still reject invalid values as before.
- Analysis finalization is isolated per item. One asset's metadata or placement
  failure can no longer abort publication for every other item in the run.
- Interrupted managed-move recovery is isolated per record, so one unreadable
  row can no longer abort an analysis job before it starts.
- Undecodable-content failures now name the cause - unsupported media type,
  probe error, no streams, or streams carrying no usable evidence - instead of
  reporting only the symptom.
- Documented the proposal to exclude non-media companion files from analysis
  scope, so the reasoning and the exclusion reasons were settled in writing
  before the behavior itself changed.

## 0.22.8 - 2026-08-22

- The catalog of record now lives at `<ARCHIVE_ROOT>/System/Beacon`, where
  system state sits beside future modules instead of among bulk derivative
  content. When no archive location is configured Beacon asks for one and
  explains how to set it, rather than silently creating an empty local catalog
  that would then report itself healthy.
- A settings file that exists but cannot be read is now reported instead of
  being treated as absent. A malformed file looked identical to an unconfigured
  deployment, so the advice told the operator to add a setting they had already
  added.

## 0.22.7 and earlier

- Completed analysis now archives excluded project companions and generated
  support artifacts when analyzed files in the same client/project tree have
  already established the destination. Beacon preserves their relative folder
  structure, uses the normal checksum-and-audit move boundary, and removes
  empty Inbox directories afterward.
- Windows sharing violations now remain isolated, retryable single-file
  placement failures. Beacon blocks the rest of a destination only for an
  actual access denial, rather than deferring the directory when one source is
  temporarily open in another process.
- Sending a Beacon Desk reply now wakes the local conversation worker
  immediately. Replies received while Beacon is busy remain durably queued,
  and the desktop drains queued conversations one at a time without losing a
  newer human message when an earlier response completes.
- Editable Premiere Pro and After Effects project files remain cataloged and
  searchable but are excluded from contextual content inference.
- Qwen now receives an explicit grounded contract for abstract visual samples
  and audio-derived spectrograms, preventing decodable abstract MP4s and
  near-black audio-bearing clips from failing on evidence-mode disagreement.
- Ordinary non-Apple 59.94/60 fps H.264 MP4 files now play directly instead
  of being misclassified as slow-motion media and blocked on transcoding.
- Compatibility previews never suppress the readable source: native playback
  starts immediately while the optimized derivative is prepared in the
  background, with a thumbnail poster during initial buffering.
- Genuine Apple/high-frame-rate compatibility previews are now silent,
  GPU-preferred 720p derivatives with a fast CPU fallback and lower preview
  bitrate. Background FFmpeg, FFprobe, and analysis helpers no longer open
  Windows console windows.
- Expanded FFprobe coverage for common professional, mobile, and lossless
  audio/video containers, including AIFF, MTS/M2TS, MXF, and camera RAW video.
- Content analysis now checksum-verifies and durably reprobes incomplete
  catalog media metadata before deciding which evidence extractors to use.
- Uniformly low-detail black-level video samples now fall through to the
  verified audio stream instead of failing as visually unreadable content.
- When Qwen returns malformed structured analysis, the retry now gives Qwen
  its rejected output so the agent can reason over and correct its own answer.
- Local content analysis uses a 32K context window so rich transcripts,
  spectrogram context, schema constraints, and corrective turns remain intact.
- Local endpoint failures preserve bounded HTTP response details, including
  explicit context-limit diagnostics, instead of collapsing to a generic 400.
- Treat Qwen's initial request goal as a revisable working interpretation.
  When a later Qwen tool decision conflicts, a focused Qwen reconciliation pass
  now revises or confirms the goal instead of allowing code to veto the action.
- Persist initial and reconciled conversation goals as durable audit events,
  including the prior goal and whether Qwen changed it.
- Preserve explicit no-search instructions through reconciliation while
  allowing obvious typos and natural follow-ups to recover into grounded search.
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
