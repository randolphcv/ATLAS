# ATLAS

ATLAS is a local-first creative archive. Beacon is its replaceable librarian: it
observes and catalogs files without owning or changing originals.

## Phase 1 milestone

Phase 0/1 now proves one safe vertical slice against synthetic fixtures:

- wait for a file to become stable;
- calculate SHA-256 and assign `atlas://asset/<uuid>`;
- record filesystem and optional `ffprobe` metadata in SQLite;
- recognize duplicate content and repeated scans;
- list and inspect catalog records from a CLI;
- leave every source byte unchanged.

No cloud service, watcher against `J:\`, or Windows service is enabled.
The verified acceptance evidence is recorded in
[`docs/PHASE1_VERIFICATION.md`](docs/PHASE1_VERIFICATION.md).

## Development

```powershell
cd C:\Development\ATLAS
python -m unittest discover -s tests -v
python -m beacon.cli init --db .\sandbox\beacon.db
python -m beacon.cli --log-file .\sandbox\beacon.log scan .\sandbox\inbox --db .\sandbox\beacon.db
python -m beacon.cli --log-file .\sandbox\beacon.log watch .\sandbox\inbox --db .\sandbox\beacon.db
python -m beacon.cli list --db .\sandbox\beacon.db
```

Use only generated test files until a production scope is explicitly approved.
The watcher runs as an ordinary foreground application and stops with `Ctrl+C`.
