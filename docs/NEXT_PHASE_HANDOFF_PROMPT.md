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

- Beacon 0.21.4 is live from
  `C:\Development\ATLAS\dist\releases\0.21.4\ATLAS Beacon\ATLAS Beacon.exe`;
- schema 16 is healthy with zero foreign-key violations;
- intake job `43bc6778-69e1-4432-a937-bd367acc0a7e` was actively running
  with 157 snapshotted items at handoff; re-check its durable state and do not
  assume it is terminal;
- analysis job `a6f80068-0b86-42dd-887b-0fc8f5b62265` is complete with
  408 publishable results, 177 excluded generated artifacts, and zero
  failures;
- all 113 tests pass;
- `main` includes the immediate native-video-preview correction;
- do not treat generated derivatives, runtime databases, backups, personal
  media, model files, secrets, or `J:\` content as Git source.

Tomorrow's priorities, in order:

1. Set up the ATLAS GitHub repository. Confirm the repository name,
   visibility, owner, and authentication path with Connor before publishing.
   Audit `.gitignore` and the commit history for runtime data, secrets, media,
   binaries, and machine-specific paths before adding or pushing a remote.
   Do not rewrite history or publish anything unexpected.
2. Implement the shared Markdown file for Ultron and Jarvis. Connor has
   prepared the authoritative implementation prompts; ask for and follow
   those prompts rather than inventing the synchronization contract. Preserve
   the identity boundary: Ultron is Windows Codex, Jarvis is MacBook Codex,
   and Beacon is the product/runtime.
3. Run representative Beacon conversation tests against the live catalog.
   Cover exact retrieval, semantic retrieval, requested result counts,
   distinct/unique results, explicit no-search turns, relevant clarification,
   correction memory, and attachment of only Qwen-selected grounded cards.
   Record the prompt, observed cards, durable worker state, and whether the
   response was actually useful. Diagnose failures before changing behavior.

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
