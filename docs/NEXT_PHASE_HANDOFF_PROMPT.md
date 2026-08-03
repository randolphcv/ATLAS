# ATLAS — Next-Phase Handoff Prompt

Use the prompt below to begin the next ATLAS task.

---

Continue ATLAS from `C:\Development\ATLAS` on `main`. Use one primary agent.

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

Current verified baseline:

- Beacon 0.22.4 is live from
  `C:\Development\ATLAS\dist\releases\0.22.4\ATLAS Beacon\ATLAS Beacon.exe`;
- schema 16 is healthy with zero foreign-key violations;
- latest intake `4ff7f10f-e72a-4762-88ae-b6264e4e8567` completed 3,830/3,830;
- Total Analysis job `37d94efb-26bb-4701-8efe-782ae9687835` is complete with
  2,896 publishable results, one excluded zero-byte file, zero failures, and
  zero pending items;
- 291 analyzed assets completed checksum-verified placement into existing
  destinations; 2,605 remain in Inbox behind 31 durable placement blockers;
- `J:` is a healthy StableBit DrivePool volume currently reporting
  `PoolModeNoCreateDirectories`, consistent with an inactive/expired DrivePool
  license; do not bypass the pool or touch pool-part folders;
- all 123 tests pass; two opt-in real-FFprobe tests skip unless
  `BEACON_FFPROBE` is supplied;
- the public repository is live at `https://github.com/randolphcv/ATLAS`,
  and local `main` tracks `origin/main`; do not rewrite published history;
- the Ultron/Jarvis bridge is live at `J:\ULTRON_CONTEXT.md` and
  `J:\JARVIS_CONTEXT.md`; preserve separate ownership and atomic replacement;
- do not treat generated derivatives, runtime databases, backups, personal
  media, model files, secrets, or `J:\` content as Git source.

Next priorities, in order:

1. Have Connor confirm/activate the StableBit DrivePool license. Verify one
   approved missing Projects destination can be created before resuming the
   deferred checksum-verified placements. Do not modify ACLs or pool parts.
2. Run representative Beacon conversation tests against the live catalog.
   Cover exact retrieval, semantic retrieval, requested result counts,
   distinct/unique results, explicit no-search turns, relevant clarification,
   correction memory, and attachment of only Qwen-selected grounded cards.
   Record the prompt, observed cards, durable worker state, and whether the
   response was actually useful. Diagnose failures before changing behavior.
3. Maintain the shared Markdown bridge after meaningful milestones. Ultron
   writes only `J:\ULTRON_CONTEXT.md`, reads Jarvis's file without editing it,
   and uses atomic same-directory replacement.

Maintain local-first operation and the existing safety boundaries. Qwen should
control conversational reasoning and retrieval choices; deterministic code is
for safety, grounding, resource limits, and verified tools—not a phrase router
or substitute personality. Never move, delete, or rewrite source media outside
the existing checksum-verified managed-operation boundaries.

If a task genuinely needs Sol High or Ultra, tell Connor before starting and
pause for the model change.

Finish with a clean, intentional commit on `main`, relevant verification
results, and updated durable handoff documentation only after live
verification.

---
