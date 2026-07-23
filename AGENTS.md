# ATLAS Repository Instructions

- Treat `J:\` as protected managed storage. Never modify originals or DrivePool configuration.
- Develop and test on the NVMe with synthetic fixtures unless Connor approves an exact production path.
- Beacon cataloging is read-only: never rename, move, edit, or delete observed files.
- Keep source, runtime data, derivatives, backups, and originals in separate locations.
- Make jobs restartable and idempotent. Verify source bytes before declaring work complete.
- Store secrets outside Git. Core catalog behavior must work without cloud access.
- Update documentation and
  `J:\System\Documentation\ATLAS\ATLAS_PROJECT_MEMORY.md` only after live
  verification.
