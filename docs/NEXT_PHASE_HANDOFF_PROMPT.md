# ATLAS — Next-Phase Handoff Prompt

Use the prompt below to begin the next ATLAS task.

---

Continue ATLAS from `<REPO>` on `main`. Use one primary agent.

Read, in order:

1. `AGENTS.md`
2. `CODEX_CONTEXT.md`
3. `docs\ATLAS_PROJECT_MEMORY.md`
4. `docs\ATLAS_CODEX_HANDOFF.md`
5. `docs\NEXT_PHASE_HANDOFF_PROMPT.md`

Before changing anything:

- confirm `main` and inspect the worktree without discarding any user changes;
- verify the exact running Beacon executable and version;
- check SQLite integrity and foreign keys;
- inspect the latest intake and analysis jobs;
- if tonight's intake is still active, do not interrupt it, migrate the live
  database, or start catalog analysis.

This document asserts no facts about current state.
`docs/ATLAS_PROJECT_MEMORY.md` is the single state record. Read the current
state section there and verify it against live state before acting.

Verify for yourself, and do not carry an earlier answer forward:

- the packaged version on disk and the version declared in source;
- schema version, `integrity_check`, and `foreign_key_check`;
- the latest intake and analysis job states, and any non-terminal job;
- storage mode and whether directory creation works, from service logs rather
  than from a note;
- open Beacon Desk threads awaiting a human.

Standing constraints:

- do not rewrite published history;
- do not bypass the storage layer or touch its underlying parts;
- do not treat generated derivatives, runtime databases, backups, media, model
  files, secrets, or archive-root content as Git source;
- record evidence in structural form only, per `AGENTS.md` section 7.

Next priorities, in order:

1. Finish the large in-progress ingest's outstanding analysis, once the
   batch-abort fix at the analysis per-item boundary is committed and
   delivered, so one item's checksum drift cannot end the whole job. Read the
   current outstanding count from `docs/ATLAS_PROJECT_MEMORY.md` and verify it
   against the catalog before starting.

   The input-validation item that previously led this list is done. The
   metadata-normalization boundary now degrades an over-length
   model-generated field instead of raising, and records the correction.

2. Decide what to do with the long-paused intake job and the Beacon Desk
   clarification thread that has awaited an answer for over two weeks.
3. Add MXF test coverage. The format is handled end to end and has none.
4. Run representative Beacon conversation tests against the live catalog.
   Cover exact retrieval, semantic retrieval, requested result counts,
   distinct/unique results, explicit no-search turns, relevant clarification,
   correction memory, and attachment of only model-selected grounded cards.
   Record the prompt, observed cards, durable worker state, and whether the
   response was actually useful. Diagnose failures before changing behavior.

   The storage-licensing item that previously led this list has been removed.
   Live evidence does not support it, and directory creation works.

---
