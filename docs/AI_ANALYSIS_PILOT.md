# Beacon AI Analysis Pilot

Verified on the Windows ATLAS host on 2026-07-23.

## Scope

The pilot analyzed the five unique assets already present in Beacon's live
catalog. The analyzed source locations were limited to the existing local
synthetic sandbox and controlled UseTest-01 copies.

The active `J:\Inbox` transfer, every uncataloged file, and all other `J:\`
content were explicitly excluded. No watcher or production scan was started.

## Processing boundary

- Connor explicitly requested a Beacon subagent for this five-asset pilot.
- The analyzer was recorded as external Codex-assisted inference, not local
  inference.
- No separate cloud connector or external API was called.
- FFmpeg/FFprobe supplied local technical facts and bounded derivatives.
- The PC did not have an approved local vision-language, Whisper, Ollama,
  Torch, or audio-semantic runtime.
- Originals were read but never renamed, moved, edited, or deleted.

## Result

- five contextual-metadata candidates were created for five asset identities;
- a byte-identical two-location image was analyzed once, not twice;
- titles, descriptions, categories, tags, privacy/rights flags, confidence,
  organization suggestions, and follow-up needs were recorded;
- verified facts and AI observations/inferences remain distinguishable in
  provenance;
- organization suggestions are visibly approval-required and did not cause file
  operations;
- audio genre, instruments, vocals, lyrics, language, and mood were left unset
  where no approved analysis method was available;
- the exact manifest re-import returned the existing run with no duplicate
  rows.

The live run ID is
`20dc7641-a832-5369-9856-88cbacdb6f41`. Candidate content remains in the local
runtime database and private manifest, not in Git documentation.

## Schema and safety

Schema version 4 adds `analysis_runs` and `analysis_results`. Every result is
bound to an asset ID and source SHA-256, records analyzer/policy versions and
execution location, carries confidence and evidence, and starts in `candidate`
review state. AI output does not overwrite the verified media metadata stored on
the asset.

Before schema migration and import, Beacon created and integrity-checked an
online live-database backup. The import was atomic: a missing asset, changed
source checksum, malformed result, absent provenance, or unrecorded
external-inference authorization rejects the complete manifest.

## Before the large inbox

Do not send the active copy stream directly into AI analysis. After copying is
finished:

1. define the exact approved path and exclusions;
2. take a stable, checksummed catalog snapshot;
3. classify privacy and rights zones;
4. choose local versus optional external analyzers per media type;
5. estimate GPU, time, storage, and API cost;
6. run one representative batch through queued, restartable jobs;
7. review candidate quality before expanding;
8. keep organization and file movement approval-based.
