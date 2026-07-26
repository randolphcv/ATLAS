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
- intake job `43bc6778-69e1-4432-a937-bd367acc0a7e` completed 157/157, and
  the latest intake `38fc99f1-cc62-41ef-929c-a89b3c1d11c6` completed 500/500;
- analysis job `a6f80068-0b86-42dd-887b-0fc8f5b62265` is complete with
  408 publishable results, 177 excluded generated artifacts, and zero
  failures;
- latest analysis job `ea673da9-6ed6-4e18-a83a-8b4cc9df2e37` is terminal
  `partial` with 484 completed items and six failures;
- all 113 tests pass;
- `main` includes the immediate native-video-preview correction;
- the public repository is live at `https://github.com/randolphcv/ATLAS`,
  and local `main` tracks `origin/main`; do not rewrite published history;
- the Ultron/Jarvis bridge is live at `J:\ULTRON_CONTEXT.md` and
  `J:\JARVIS_CONTEXT.md`; preserve separate ownership and atomic replacement;
- do not treat generated derivatives, runtime databases, backups, personal
  media, model files, secrets, or `J:\` content as Git source.

Next priorities, in order:

1. Run representative Beacon conversation tests against the live catalog.
   Cover exact retrieval, semantic retrieval, requested result counts,
   distinct/unique results, explicit no-search turns, relevant clarification,
   correction memory, and attachment of only Qwen-selected grounded cards.
   Record the prompt, observed cards, durable worker state, and whether the
   response was actually useful. Diagnose failures before changing behavior.
2. Maintain the shared Markdown bridge after meaningful milestones. Ultron
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
