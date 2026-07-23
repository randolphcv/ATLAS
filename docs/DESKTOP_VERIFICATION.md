# Native Desktop Verification

Verified on the Windows ATLAS host on 2026-07-23.

## Outcome

Beacon 0.8.0 is a native Qt Quick/QML desktop application. It uses the existing
read-only catalog, repository, audit, health, and verified-backup modules
directly. The desktop process does not open a browser, embed a web view, start
FastAPI, or listen on a network port.

The current client also uses Qt Multimedia for local temporary previews. It
loads verified thumbnail derivatives in Library and opens a selected asset with
Space. Plain-text files render in a bounded read-only viewer; binary formats
retain the metadata-only fallback. Playback stops when the modal preview
closes.

The selected-asset detail now presents checksum-bound Beacon analysis separately
from technical facts. Candidate title, description, tags, confidence, privacy
flags, execution location, and approval-only organization suggestions remain
visibly labeled as AI output.

The Overview now contains Beacon Desk, a persistent native master-detail
conversation surface. It distinguishes questions waiting for the human from
replies queued for Beacon, supports human-started requests, keeps approval
language separate from execution authority, and only closes a thread through an
explicit Resolve action.

Library now provides searchable, revisioned contextual metadata and a
policy-gated managed-move interface. Human context stays editable while
checksums and technical facts stay locked. A completed managed destination is
preferred as the current path without discarding any other observed location.

## Automated verification

- Python compilation: passed
- Unit and integration tests with real FFprobe and FFmpeg: 44 passed
- Native catalog model, search, detail, and health tests: passed
- Non-blocking verified-backup controller test: passed
- QML window offscreen load test: passed
- Application-level Space shortcut with a focused action button: passed
- Space inserts text in the Beacon reply composer without opening preview:
  passed
- Schema-6 Beacon thread/message persistence, seed idempotency, queue
  transitions, and explicit resolution: passed
- Editable metadata normalization, revision history, search, controller refresh,
  and native-dialog rendering: passed
- Managed-move policy gate, exact catalog-location match, SHA-256 verification,
  approved-root boundary, non-overwrite behavior, destination preference, audit
  history, and duplicate-location preservation: passed
- Dependency check: passed

## Rendered verification

The actual Qt window was rendered against the synthetic acceptance catalog.
The following states were visually reviewed:

- overview metrics, recent assets, audit signals, and local-only state;
- master-detail asset library with video/audio technical facts;
- system health, explicit backup action, and recovery-point history;
- packaged-executable asset library.
- image fit-to-window preview;
- audio waveform, playback, and scrubber;
- video playback and scrubber.
- exact no-argument packaged launch against the labeled Live catalog;
- automatic refresh after an external catalog transaction.
- larger image and text-fallback tiles in the selected-asset header;
- selectable read-only text preview with encoding and truncation status.
- source and packaged Beacon Analysis candidate detail with an explicit external
  inference label.
- source and exact packaged Beacon Desk Overview with six live conversations;
- new-request, reply, approval-boundary, and resolved-state controller flows.
- synthetic editable-metadata dialog with all supported contextual fields;
- exact packaged 0.8.0 live Library with human display titles and the verified
  managed location selected as the current path.

Screenshots:

- [`images/desktop-overview.png`](images/desktop-overview.png)
- [`images/desktop-library.png`](images/desktop-library.png)
- [`images/desktop-system.png`](images/desktop-system.png)
- [`images/desktop-packaged.png`](images/desktop-packaged.png)
- [`images/beacon-desk.png`](images/beacon-desk.png)
- [`images/editable-metadata.png`](images/editable-metadata.png)

## Executable verification

Artifact:

```text
C:\Development\ATLAS\dist\releases\0.8.0\ATLAS Beacon\ATLAS Beacon.exe
```

Package:

```text
C:\Development\ATLAS\dist\ATLAS-Beacon-0.8.0-win64.zip
```

The frozen executable passed smoke-test and screenshot modes against the
schema-6 live database without a `--db` override. Windows file and product
versions are both `0.8.0`.

Executable SHA-256:

```text
15375B4C2E5B0E90702914B196E77B12C4A3D9274C7E52BA5A413162BE9646E2
```

Package SHA-256:

```text
61E12DB4F8CD61540D7BBB1C2357C475CFB7DA7ECC60CAB8608278E6DC0F607D
```

The one-folder bundle contains 1,748 files and 178,146,202 bytes. Its packaging
filter excludes FastAPI, Uvicorn, Pydantic, Qt WebEngine, Qt Quick 3D, charting,
PDF, and virtual-keyboard capabilities.

This private development build is not Authenticode-signed, so Windows may
identify the publisher as unknown.

## Safety boundary

- The large Inbox received read-only structural inventory only; one explicitly
  authorized known-checksum file was cataloged and moved as the bounded proof
- The only content inference was the explicitly requested five-asset Codex
  subagent pilot; it is recorded as external inference
- No production watcher, scheduled task, or cloud connector was added
- One exact `J:\Inbox` location was moved to an approved `J:\Library`
  destination; its filename and SHA-256 were preserved and all other duplicate
  locations remain
- Backup, the explicit candidate-manifest import, schema migration, and seeded
  Beacon conversations were the only catalog writes
- Preview remains read-only; thumbnail writes stay in the runtime derivative tree
- AI output remains candidate data separate from verified technical facts
- Organization suggestions did not perform file operations
- Beacon replies cannot directly authorize or perform file operations
- Context edits do not rewrite embedded source-media metadata
- Managed moves require recorded policy and exact per-operation evidence
- Backup requires explicit confirmation and is integrity-checked before success
- Restore and backup deletion remain absent
