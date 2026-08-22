# ATLAS Repository Instructions

This file is doctrine. It governs every change made in this repository.

## 1. Product and deployment

ATLAS is a software platform. It is not a drive, a volume, a folder, a storage
pool, or any person's files. Modules provide capability on top of it.

A deployment is one installation of ATLAS with its own configuration and its own
archive roots. Every deployment is a customer, including the author's.

The author's archive volume is one archive root belonging to one deployment. It
is not "the ATLAS". This repository must never assume otherwise.

ATLAS does not currently manage physical storage. A storage layer replacing the
current third-party pooling software is a future module that does not exist yet.
Until it does, the storage provider is an external dependency and is never named
as a requirement.

## 2. Vocabulary

- **ATLAS** — the platform.
- **Module** — an add-on providing capability within ATLAS.
- **Beacon** — the librarian module: intake, catalog, analysis, retrieval, and
  managed placement. One module among future others.
- **Archive root** — a configured filesystem location ATLAS manages. Written
  `<ARCHIVE_ROOT>` in documentation; resolved from configuration in code.
- **Inbox** — the intake area beneath an archive root, written `<INBOX>`.
- **Deployment** / **instance** — one installation. Never described here.

`Beacon` is an implementation name. It stays `Beacon` in code, paths, schemas,
table names, and module names. The vocabulary above is documentation register,
not a rename.

## 3. Instance data is prohibited in this repository

Never in source, tests, fixtures, documentation, comments, commit messages, or
any file tracked by Git:

- drive letters or absolute paths belonging to any deployment;
- client names, project names, personal names, event names, place names;
- real filenames from any archive;
- hostnames, machine names, or agent-environment nicknames;
- a storage vendor or product named as though it were a requirement;
- credentials, tokens, account identifiers, or licence keys.

Documentation uses `<ARCHIVE_ROOT>`, `<INBOX>`, `<CLIENT>`, `<PROJECT>`.

Tests use synthetic fixtures whose names could not occur in a real archive:
`fixture_client_a`, `project_alpha`, `SAMPLE_0001.CR3`. A fixture that could be
mistaken for production data is a defect.

`tests/test_no_instance_data.py` enforces the structural half of this rule
mechanically. Deployment-specific terms belong in `instance-terms.local.txt`,
which is untracked.

## 4. Derivative content

Derivative content is any artifact produced from archived material: thumbnails,
previews, proxies, transcripts, embeddings, extracted frames, analysis results,
and the catalog itself.

The home of record for derivative content is the archive root. Derivative
content never exists solely outside it.

Local storage may hold a working cache. A cache is disposable by definition and
fully reproducible from the archive root. If losing it loses information, it is
not a cache — it is derivative content in the wrong place.

No derivative content is ever written into the repository.

## 5. Location separation

- **Repository** — source, tests, documentation, build configuration, version
  history. No deployment data, no derivative content.
- **Runtime** — configuration, working cache, application logs. Local,
  disposable, reproducible.
- **Archive root** — originals, derivative content, the catalog of record, and
  archive-scoped logs.

Nothing crosses these boundaries except through configuration and audited
operations.

## 6. Archive operations

Originals are never modified or deleted. Beacon opens them read-only.

Catalog observation is read-only. Managed placement is a separate, audited
analysis-commit operation. Ambiguous placement requires clarification rather
than a guess.

Managed moves stay within approved archive roots, re-hash the source, refuse
silent overwrite, verify destination bytes, and roll back on a failed
post-move check.

Relative structure beneath the Inbox is preserved verbatim when material is
placed into the archive. The path of a file below `<INBOX>` is reproduced below
its archive destination. Placement reorganizes nothing.

Never change third-party storage configuration.

## 7. Evidence discipline

This is the rule whose absence caused instance data to accumulate here.

Verification against live material is still required. Live state outranks any
note. But evidence recorded in this repository must be redacted to structural
form. Record what was proven: counts, states, durations, checksum verification
status, error classes, job outcomes. Never record which specific files proved
it.

"Moved 934 companion files and removed 27 empty directories, zero failures" is
correct. The same sentence naming a client folder is a defect, however true.

## 8. One record of current state

`docs/ATLAS_PROJECT_MEMORY.md` is the single record of current live state. It
was chosen because it is already the designated memory document and is
referenced as such by the deployment's own documentation.

Every other document links to it and asserts no facts about the present.
Four documents each claiming current state is what produced the existing drift.

A document that describes design, architecture, or intent is timeless and
belongs elsewhere. A document that says "is live", "is running", or "currently
reports" is making a state claim and belongs in the state record or nowhere.

## 9. Operator environment

Agent-environment names for particular machines are deployment data and leave
this repository. Operator environments are named in `OPERATOR.local.md`, which
is untracked, and in the deployment's own documentation.

Refer to them generically here: the operator environment, the workstation
environment, the secondary environment.

## 10. Engineering rules

- Develop and test with synthetic fixtures unless a production scope is
  explicitly approved.
- Keep source, runtime data, derivatives, backups, and originals in separate
  locations.
- Make jobs restartable and idempotent. Verify source bytes before declaring
  work complete.
- No module hardcodes a drive letter or an archive path. Paths come from
  configuration.
- Store secrets outside Git. Core catalog behavior must work without cloud
  access.
- Update documentation only after live verification, and redact that evidence
  to structural form per section 7.

## 11. Commit convention

Single-line subject, 50 characters or fewer, imperative mood, sentence case.
No type prefixes. No trailers.
