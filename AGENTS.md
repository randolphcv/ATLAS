# ATLAS Repository Instructions

- Identity boundary: **Ultron** means Codex on the Windows ATLAS workstation;
  **Jarvis** means Codex on Connor's MacBook; **Beacon** remains the ATLAS
  librarian product/runtime. Never use these names interchangeably.
- The Windows hostname is currently `DESKTOP-8B4OJIR`. Connor has requested
  `Ultron`, but do not treat that OS rename as active until it is verified
  after a Windows restart.
- Treat `J:\` as protected managed storage. Beacon may perform audited,
  checksum-verified, same-volume moves into approved archive roots after
  successful analysis when the existing hierarchy makes placement unambiguous.
  Never edit or delete originals or change DrivePool configuration.
- Develop and test on the NVMe with synthetic fixtures unless Connor approves an exact production path.
- Catalog observation is read-only. Managed placement is a separate, audited
  analysis-commit operation; ambiguous placement requires clarification.
- Keep source, runtime data, derivatives, backups, and originals in separate locations.
- Make jobs restartable and idempotent. Verify source bytes before declaring work complete.
- Store secrets outside Git. Core catalog behavior must work without cloud access.
- Update documentation and
  `J:\System\Documentation\ATLAS\ATLAS_PROJECT_MEMORY.md` only after live
  verification.
