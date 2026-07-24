# Beacon Shell Conversation

Updated: 2026-07-24

Beacon conversation is an application-shell capability. It is not owned by
Overview, Library, Reports, Operations, or System, and navigation must not
replace the active conversation.

## Authority and lifecycle

- `beacon_threads` and `beacon_messages` remain the only durable conversation
  authority.
- `DesktopController` owns the active thread and its message model for the
  lifetime of the application.
- The root QML shell owns the expanded state, composer draft, and message
  scroll position. Page navigation changes the workspace behind the shell
  without recreating these controls.
- Draft text is intentionally in-memory in this first slice. Sending writes a
  normal human Beacon Desk message; closing the application discards an unsent
  draft.
- The full Beacon Desk on Overview remains the detailed thread-management
  surface. The shell dock is a compact view of the same selected thread, not a
  second chat system.

## Context boundary

The shell shows the current page and, in Library, the selected asset identity.
Changing pages never adds this context to a conversation. **Attach** inserts a
plain, inspectable context marker into the draft only when the human requests
it. The marker becomes durable only when the human saves the reply.

Context is advisory. It does not authorize analysis, intake, file movement, or
any other operation.

## Runtime boundary

Conversation storage works without a model. The shell reports whether the
separately managed local model runtime is available, but it does not start a
cloud service, embed a browser engine, or bundle model weights.

A future conversational responder must sit behind a replaceable local adapter.
It may append Beacon messages to an existing thread. Any consequential request
must first become a typed command and pass the existing policy, confirmation,
checksum, and audit boundaries. Free-form model output never performs a file
operation directly.

## Performance contract

- Keep the shell component alive rather than rebuilding it per page.
- Continue using the existing low-cost SQLite/WAL signature refresh.
- Load only the selected thread's messages; do not preload transcripts, report
  data, or every closed conversation.
- Collapsed height is 58 logical pixels and does not run inference.
- Treat startup, idle CPU/RAM, database-query, or bundle-size regressions as
  release blockers.

## Conversational worker

Schema 14 adds a loopback-only worker that leases one queued Desk thread,
performs bounded read-only catalog search, and appends a grounded response.
The shell can run one queued conversation when catalog analysis is idle.
Responses may include message-linked catalog cards whose only action is to
inspect the asset in Library.

The CLI also supports an explicitly launched low-frequency watch loop. It
pauses while catalog analysis is running and does not infer while idle. See
`BEACON_CONVERSATION_WORKER.md`.

## First implemented slice

The native shell provides:

- a collapsed local status bar on every page;
- expandable history for the active Beacon Desk thread;
- a persistent reply draft across page navigation;
- explicit page/selected-asset context attachment;
- local-only runtime status;
- new-conversation and saved-reply entry points backed by Beacon Desk.

It does not yet provide report generation, consequential command routing,
persisted unsent drafts, file collection/export, or remote delivery.
