# ATLAS — Connor Context and Product Direction

Updated: 2026-07-22  
Purpose: portable context for **Ultron**, the Codex environment on the Windows
ATLAS workstation. The separate MacBook Codex environment is **Jarvis**.

## Codex Environment Identity

- **Ultron**: Codex running locally on the Windows ATLAS workstation. This
  repository, the Beacon runtime, Ollama, Qwen, faster-whisper, the live SQLite
  catalog, and `J:\` operations are currently local to Ultron's machine.
- **Jarvis**: Codex running on Connor's MacBook. Jarvis may work through the
  SMB share or a separate repository/session and must verify Windows runtime
  state rather than assuming it.
- **Beacon**: the ATLAS librarian application and future persistent local
  agent. Beacon is not another name for Ultron and is not currently a spawned
  Codex subagent.

Connor will address the Windows Codex as Ultron and the MacBook Codex as
Jarvis. The current Windows hostname remains `DESKTOP-8B4OJIR`; a rename to
`Ultron` is pending a later restart and must be verified afterward.

This document captures the working preferences and design language that should remain consistent as ATLAS evolves. It is a curated guide, not a transcript archive and not permission to expand scope.

## How Connor Likes Codex to Work

### Lead with the outcome

State what is true, what changed, and what remains unresolved. Keep routine process narration short.

### Act autonomously inside a safe, agreed scope

Inspect first, make reasonable low-risk assumptions, implement the requested change, and verify it. Ask only when a missing choice would materially affect architecture, privacy, cost, destructive behavior, or the treatment of user media.

### Use live artifacts as truth

Prefer the current filesystem, Git state, tests, service status, database contents, logs, and rendered interface over plans or backend assumptions. A command returning successfully is not always proof that the user-facing or destination state is correct.

### Reproduce demonstrated workflows faithfully

Once Connor shows an exact workflow, preserve its sequence and acceptance shape. Do not replace it with a theoretically clever shortcut unless Connor agrees to the change.

### Prove one representative case before batching

For risky automation, transfers, migrations, metadata writes, or media processing:

1. test one small complete case;
2. inspect structure and visible result;
3. confirm persistence/restart behavior;
4. only then expand.

### Protect creative and personal judgment

Automate repetitive preparation, indexing, derivatives, organization suggestions, and retrieval. Connor retains aesthetic judgment, storytelling, pacing, cultural judgment, publishing decisions, and final approval.

### Keep durable memory compact

Record canonical paths, decisions, invariants, verification commands, current state, failure causes, and next steps. Do not dump entire conversations, raw logs, private content, or hidden reasoning into project memory.

## Structural Preferences

Connor's projects work best when they have:

- one clear source of truth for each type of data;
- a documented root structure;
- obvious entrypoints;
- named safety modes and visible state;
- small modules with explicit boundaries;
- local, double-clickable or low-friction operation where practical;
- no unnecessary build or infrastructure complexity;
- a concise `AGENTS.md` for controlling rules;
- a `CODEX_CONTEXT.md` for durable collaboration and design context;
- an architecture document for boundaries;
- a roadmap that separates now, next, and later;
- a small living memory/decision ledger;
- test fixtures that cannot be confused with production data.

Avoid duplicated configuration, duplicated metadata authorities, magic folders, hidden mutations, and giant modules that mix watching, cataloging, AI analysis, storage operations, and UI concerns.

## ATLAS Product Character

ATLAS is not a generic cloud-drive dashboard. It should feel like a dependable archive and an intelligent studio instrument.

The product metaphor is:

- **ATLAS is the library and map.**
- **Beacon is the calm librarian and guide.**
- **The archive is durable; intelligence modules are replaceable.**

The experience should communicate:

- permanence without heaviness;
- intelligence without mystery;
- power without recklessness;
- density without clutter;
- technical confidence without looking like an IT admin template.

## Initial Visual Direction

Treat this as a starting design system to prototype and review, not a locked brand kit.

### Tone

Use a cinematic, archival, cartographic direction: quiet, precise, premium, tactile, and slightly mysterious. Favor a purpose-built studio tool over generic SaaS styling.

### Palette

Suggested semantic families:

- deep ink / charcoal for the main shell;
- warm paper / bone for readable detail surfaces;
- muted atlas blue or blue-green for navigation and selected state;
- restrained brass / amber for identity, attention, and pending work;
- jade / green only for verified healthy or complete states;
- ember / red only for destructive, failed, or at-risk states.

Do not make every panel glow or every accent compete. Status colors must retain stable meaning.

### Typography

- Use a highly legible modern sans-serif for operational UI.
- A restrained editorial serif may be used for major identity moments, map/library headings, or empty states.
- Monospace belongs to paths, checksums, UUIDs, codecs, logs, and technical metadata.
- Use hierarchy and spacing before adding borders, badges, or decorative labels.

### Layout

- Design the dashboard as a spatial cockpit for archive work: persistent navigation, clear status, useful density, and minimal page-hopping.
- Keep the current object and current operation obvious.
- Prefer master-detail patterns for assets and processing jobs.
- Provide calm overview states plus drill-down detail; do not place every metric on the first screen.
- When a workflow benefits from staying in one view, avoid needless full-page scrolling.
- Use progressive disclosure for technical metadata and advanced operations.

### Motion

Motion should explain state changes: detection, waiting for copy stability, hashing, cataloging, derivative creation, success, and failure. Keep it restrained. Never use animation to imply completion before the backend state is verified.

### Reference-model rule

Before inventing a risky interaction from scratch, identify a named reference pattern and state what is being borrowed. Useful categories may include:

- Lightroom or Capture One for media-library browsing;
- Finder/Explorer for file-location clarity;
- DaVinci Resolve media management for technical media density;
- Obsidian graph/backlinks for relationships;
- enterprise backup tools for job history, health, and recoverability.

References are behavioral benchmarks, not licenses to copy a product wholesale. Ground aesthetic recommendations in the actual ATLAS screens, components, and tokens once they exist.

## Interface Content Principles

- Prefer plain language with exact technical detail available on demand.
- Always distinguish original, derivative, metadata, and backup.
- Show why Beacon believes two files are duplicates.
- Show the current path and permanent ATLAS identity together.
- Make processing state legible: waiting, stable, hashing, cataloged, derivative queued, complete, failed, quarantined, or approval required.
- Never label a job complete when it is merely queued or in progress.
- Make local/cloud boundaries visible before any upload or external model call.
- Put destructive actions behind explicit confirmation with a concrete target and consequence.
- Preserve audit history as a first-class user-facing feature, not only a developer log.

## Engineering Preferences

### Current Beacon baseline (2026-07-24)

- Beacon 0.15.4 is the current packaged candidate on branch
  `ops/overnight-250-tranche`.
- The bounded 250-file production tranche completed intake and contextual
  analysis locally; the one malformed Qwen JSON response passed on a one-item
  retry.
- Library browsing uses Recents plus a catalog-backed Explorer; brass means
  cataloged and cyan means contextually analyzed.
- RAW previews are disposable checksum-bound PNG derivatives. Microsoft Raw
  Image Extension and Beacon's packaged rawpy/Pillow fallback are installed;
  originals are never decoded in place or rewritten.
- Contextual analysis may describe a RAW photo only when the verified local
  derivative is supplied to the model. Missing visual evidence is a hard stop.
- Finder `.DS_Store` files are explicitly disposable metadata. Beacon recycles
  them before intake snapshots and audits the disposition.
- Contextual-analysis jobs continue after individual asset failures. Cancel
  targets the latest running durable analysis job, and Retry resets only its
  failed assets without replacing the job or repeating completed assets.
- Overview “Current failures” counts retryable items in the latest intake and
  analysis jobs; lifetime failed audit events remain in the operation ledger
  and are not presented as current work.
- Future thumbnail derivatives live under `J:\Beacon\Thumbnails` for the live
  catalog; C: remains the fast runtime/model/temp tier.

- Favor boring, recoverable engineering over clever shortcuts.
- Use explicit schemas, migrations, typed boundaries, and structured logs.
- Make jobs restartable and idempotent.
- Design for interruption, unavailable drives, partial copies, duplicate filenames, renamed files, and stale paths.
- Prefer immutable facts plus derived state over destructive normalization.
- Make local-first behavior the baseline; external AI services must be optional adapters.
- Keep proprietary intelligence replaceable and preserve ordinary-file access.
- Optimize only after measuring the real bottleneck.
- Keep Beacon's music models in the isolated Python 3.11 runtime under
  `C:\ProgramData\ATLAS\MusicRuntime`; do not fold CUDA/TensorFlow dependencies
  into the packaged Python 3.12 application.
- Keep source, runtime state, derivatives, backups, and originals in clearly different locations.

## Privacy and Authority Boundaries

- Personal and unpublished media stays local unless Connor explicitly authorizes a specific upload, share, generation, or publication.
- An installed connector or available model is not automatic permission to send data to it.
- Do not persist secrets or direct personal/private content in documentation or memory.
- Index content only after the intended scope and exclusions are explicit.
- Managed moves must be audited, checksummed, collision-safe, bounded to
  approved roots, and tested against non-production fixtures first. Successful
  analysis is standing authorization for an unambiguous final placement;
  Beacon asks only when placement logic is genuinely unclear.

## Communication and Handoff

At the end of meaningful work, report:

1. the verified outcome;
2. files or components changed;
3. checks/tests performed;
4. any live/runtime checks that could not be performed;
5. risks or unresolved decisions;
6. the smallest useful next step.

Update `ATLAS_PROJECT_MEMORY.md` only with durable project truth. If a note conflicts with the live system, verify the live state and then correct the note.

## Non-Goals for Early ATLAS

Do not let the first prototype drift into:

- autonomous media organization;
- bulk moves or renames;
- destructive deduplication;
- cloud-required indexing;
- a full semantic-search stack before the catalog is dependable;
- premature multi-user or multi-tenant architecture;
- elaborate animation before operational states are correct;
- product branding that obscures system safety;
- indexing every byte of `J:\` before a small sandbox is proven.

The early product promise is simple:

> Beacon can safely observe a file, give it a durable identity, describe what it is, and retrieve that knowledge later without harming the original.
