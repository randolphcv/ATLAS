# Archive Intake Jobs

Beacon 0.9.0 adds explicit, durable recursive catalog jobs to the native
Overview. Intake remains catalog-only: it records identity, technical metadata,
locations, and separate derivatives without moving, renaming, editing, or
deleting a source file.

## Safety boundary

- The packaged app accepts intake roots only at or below `J:\Inbox`.
- Directory links, file links, and Windows reparse points are excluded.
- The New Intake dialog defaults to a representative 25-file scope.
- Leaving the file limit blank is the explicit action that snapshots every
  discovered regular file.
- A snapshot records each relative path, byte size, modified time, total byte
  count, and a deterministic SHA-256 signature.
- Before cataloging an item, Beacon verifies that its size and modified time
  still match the snapshot. A changed item fails visibly instead of silently
  cataloging different bytes.
- Existing catalog identity remains SHA-256 based, and `catalog_file` verifies
  that source stats do not change while hashing.

## Job states

`Ready` means a snapshot exists but has not started. `Running` reports the
current path and durable item counts. `Paused` is safe to resume. `Cancelled`
retains completed and pending work. `Needs retry` or `Failed` retains an error
for each failed item. `Complete` means every snapshotted item was cataloged.

Cancel requests are honored between files so a checksum operation is never
abandoned halfway through a database transition. Retry resets only failed
items; completed items are not repeated. If the app or computer stops
unexpectedly, any item left in `running` is reset to `pending` and the job
opens as `Paused` on the next launch.

Closing the app requests a pause and waits for the current file operation to
reach its safe boundary.

## First production test

Do not begin with the complete ATLAS Inbox. After reviewing the 0.9.0 native
interface, create a 25-file `J:\Inbox` snapshot, start it, exercise Cancel and
Resume, inspect failures and catalog results, and verify source hashes for the
sample. Remove the limit only after that bounded proof is accepted.
