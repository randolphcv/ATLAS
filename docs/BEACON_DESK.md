# Beacon Desk

Beacon Desk is the durable conversation surface between the human archivist and
Beacon. Its detailed management surface lives on the native Overview page, and
its compact conversation dock lives in the application shell. Both persist
messages in the same local SQLite catalog as the rest of Beacon's operational
state.

## What belongs here

- blockers that require a human fact or boundary;
- questions and clarifications;
- requests for approval;
- human-started requests for Beacon;
- a complete ordered message history for each conversation.

The collection is called **Open conversations**, not a task or to-do list.

## States

- `awaiting_human`: Beacon needs an answer.
- `queued_for_beacon`: a human message is saved for Beacon to review.
- `resolved`: the conversation was explicitly marked complete.
- `closed`: reserved for a future administrative close operation.

Replying does not automatically resolve a conversation. This preserves a clear
handshake: the human supplies context, Beacon reviews it, and either continues
the conversation or closes the loop.

## Authority boundary

Conversation is not execution. A reply may record an approval or policy
decision, but it cannot directly scan, upload, rename, move, delete, overwrite,
or promote candidate metadata. Consequential work requires a separate,
auditable operation designed for that exact action.

## Worker boundary

Beacon Desk is currently a local handoff queue. It does not claim that an AI
worker is always online. The UI labels messages `SAVED LOCALLY`; a deliberate
Beacon analysis session can consume queued threads and append Beacon messages
through the repository boundary.

The compact shell dock is a second view of this same durable authority. It
keeps the selected thread, draft, and message scroll position alive while page
content changes. Page or selected-asset context is added only through the
explicit **Attach** action. See `BEACON_SHELL_CONVERSATION.md`.

## Initial pilot conversations

The live catalog begins with six idempotently seeded conversations from the
five-asset pilot:

- three important gates for copy completion, AI privacy, and candidate-only
  metadata;
- three optional enrichment conversations for the representative image, video,
  and audio assets.

Seeding uses stable keys. Re-running the seed does not duplicate or reopen a
resolved conversation.
