# Proposal — exclude non-media companions from analysis scope

> Proposal only. Nothing here is implemented. The owner decides.
> This document asserts no facts about current state.
> `docs/ATLAS_PROJECT_MEMORY.md` is the single state record.

## The finding

One analysis run scoped 1,054 items and recorded 79 item failures. 61 of those
— 77% of all failures — carried the message "no decodable visual, audio, or
text content evidence was available".

Read from the catalog, those 61 are three extensions:

| Extension | Failed | Share of that extension in scope | On a media allowlist? | Probed? |
|---|---|---|---|---|
| `.mif` | 45 | 45 of 45 — 100% | no | never attempted |
| `.key` | 15 | 15 of 15 — 100% | no | never attempted |
| `.prin` | 1 | 1 of 1 — 100% | no | never attempted |

Every one of them failed. None of them was ever probed, because none is in
`AUDIO_VIDEO_EXTENSIONS` or `IMAGE_EXTENSIONS` in `beacon/media.py`, so
`should_probe` returned false and there was no metadata for the analyzer to
work from.

Identified by file signature rather than by extension:

- `.mif` — 45 files, byte-identical in size, one per distinct parent directory.
  A fixed-size camera media index or card-metadata record written once per
  clip folder. Not media.
- `.key` — ZIP container signature. Presentation documents, 42 MB to 769 MB,
  across 3 parent directories. A document, not media.
- `.prin` — gzip signature. A generated editor index/cache file. It is the only
  one of the three with a same-stem sibling of another extension in the
  catalog, so it is a true sidecar.

None is zero-byte. All 61 were readable at the time of inspection. None is
truncated or corrupt.

## Three-way classification

- **Companion / non-media — 61 of 61.** All three extensions. Camera metadata,
  a generated editor index, and presentation documents. Asking a
  vision-language model to describe any of them was never going to work.
- **Media that should have worked — 0.** There is no decode gap in this set.
  Worth stating explicitly because the project's notes flag HEIC support as
  unresolved: no HEIC or HEIF file appears anywhere in this job. The catalog
  holds HEIC assets, but none was in scope here, so HEIC is neither confirmed
  nor implicated by this failure set.
- **Genuinely undecodable — 0.** No zero-byte, truncated, or corrupt file.

The other 18 failures are a different problem and are addressed separately: 16
were over-limit model output on a supported video type that analysed fine
otherwise, and 2 were malformed model JSON on a text type.

## What excluding them would do

| Measure | Now | With the three extensions out of scope |
|---|---|---|
| Items scoped | 1,054 | 993 |
| Item failures | 79 | 18 |
| Failures from undecodable content | 61 | 0 |

Combined with the model-output handling shipped alongside this proposal, which
retries and then degrades over-limit fields rather than failing the item, the
remaining 18 would be expected to fall further.

## Where scope is determined

Two places, and the second is the one to change.

1. `beacon/local_analysis.py` — `_project_scope_sql` builds the SQL predicate
   that keeps `NON_CONTENT_PROJECT_EXTENSIONS` out of the candidate query when
   a job is created.
2. `beacon/local_analysis.py` — `_artifact_exclusion_reason` runs per item at
   analysis time. It returns a human-readable reason, and
   `_complete_analysis_exclusion` then marks the item `complete` with an
   `excluded_reason` rather than `failed`.

`_artifact_exclusion_reason` already handles exactly this shape for three
cases: zero-byte files, editable production project files
(`NON_CONTENT_PROJECT_EXTENSIONS`), and hidden support/sidecar paths. The
mechanism exists and is well-behaved. This proposal adds a fourth case rather
than inventing anything.

## The change

Add a set alongside `NON_CONTENT_PROJECT_EXTENSIONS` — a name such as
`NON_CONTENT_COMPANION_EXTENSIONS` — holding the camera-metadata, editor-index
and presentation-document extensions, and return an exclusion reason for them
in `_artifact_exclusion_reason`.

Those items would then be recorded `complete` with a reason in the same register
as the existing text, for example: *"Excluded camera metadata / generated index
/ document from contextual content inference; the file remains cataloged and
searchable."*

The extension list should be a named constant, not a literal in a query, so the
owner can add to it without a code change to logic.

## What this does not change

This is the part the owner cares about, and the answer is favourable on all
three counts.

- **Cataloging — unaffected.** Exclusion happens at analysis, long after
  intake. The asset, its checksum, its size, its locations and its identity are
  already recorded and stay recorded.
- **Retrievability — unaffected.** The asset stays searchable by filename,
  path, checksum and ATLAS ID. It loses only model-derived description and
  tags, which for these three types were never produced anyway — all 61
  currently produce nothing but a failure.
- **Placement alongside originals — improved, not harmed.** This is worth
  being precise about. `archive_contextual_inbox_companions` in
  `beacon/managed_moves.py` selects companions using, among other tests,
  `excluded_reason IS NOT NULL`. An excluded item is therefore *explicitly*
  treated as a companion and placed into the project tree beside its
  neighbours, preserving its relative folder structure. A **failed** item is
  not selected that way. Excluding these files makes them more likely to travel
  with their originals, not less.

One honest caveat: companion placement inherits its destination from an
analysed neighbour in the same client/project tree. The presentation documents
sit in directories with no analysed same-stem sibling, so whether each one
inherits a destination depends on whether an analysed file exists elsewhere in
its project tree. That is true today and would remain true; the change neither
improves nor worsens it.

## Recommendation

Adopt for the camera-metadata and editor-index extensions without reservation:
they are unambiguously generated, non-content companions, and the existing
exclusion mechanism was built for precisely this.

Treat the presentation-document extension as the owner's call. It is not a
sidecar and not camera output — it is a real document a person authored. It
holds no decodable *media*, so it will keep failing analysis as things stand,
but a future text- or document-extraction path could give it genuine content
evidence. Excluding it now is correct for today and reversible later; the
alternative is to leave it failing until such a path exists.
