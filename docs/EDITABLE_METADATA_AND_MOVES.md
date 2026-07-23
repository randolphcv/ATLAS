# Editable Metadata and Managed Moves

Beacon keeps three different kinds of information deliberately separate:

1. **Verified facts** — checksum, byte size, codec, duration, dimensions,
   observed locations, and derivative lineage. These are locked evidence.
2. **AI candidates** — suggested titles, descriptions, tags, privacy flags, and
   organization ideas with confidence and provenance.
3. **Editable context** — the human-controlled catalog record used for finding,
   understanding, and organizing an asset.

## Editable context

The native Library editor currently supports:

- display title and description;
- media category;
- tags and people;
- date/time context and place;
- client and project;
- rights and restrictions;
- freeform notes;
- approved organization directory.

Every save creates an immutable revision record. Search includes the current
editable metadata. Context attaches to the asset UUID, so it survives location
changes and checksum-identical duplicate paths.

Beacon does not rewrite EXIF, XMP, ID3, QuickTime atoms, or other embedded
source-media headers. A future embedded-metadata writer would require its own
format-specific, backup-aware design.

## Managed moves

Managed moves are enabled only by recorded policy and remain separate from AI
suggestions. A move requires an exact cataloged location and an approved
directory under:

- `J:\Library`
- `J:\Assets`
- `J:\Projects`

Beacon preserves the source filename, refuses to overwrite or silently merge an
identical destination, rejects reparse-point traversal, verifies the source
checksum, performs a same-volume rename, verifies the destination checksum, and
then updates the catalog and operation ledger.

If a failure occurs after the filesystem move, Beacon attempts to restore the
source before recording failure. Other observed locations for the asset are
preserved.

## First live proof

After an independently stable Inbox inventory, one known checksum-identical
portrait location completed the full catalog-to-managed-location path. Its
destination hash matched the catalog, its prior test locations remained, its
editable metadata revision remained attached, and the live schema passed
integrity and foreign-key checks.

Private names, rights details, and the full Inbox manifest stay in the runtime
database and private validation records, not in repository documentation.
