# Controlled Media Use Test 01

Verified on the Windows ATLAS host on 2026-07-23.

## Scope

Five media copies explicitly supplied in the approved ATLAS test-drop folder
were copied—not moved—to an isolated NVMe runtime:

```text
C:\ProgramData\ATLAS\Beacon\use-tests\UseTest-01-20260723-004437\
```

The set contained JPEG images, PCM audio, H.264 video, and one renamed
byte-for-byte duplicate. No production inbox, library, or unrelated ATLAS path
was read.

## Verified outcome

- five stable source files totaling 94,061,069 bytes;
- every NVMe copy matched its ATLAS source SHA-256;
- four permanent asset rows and five observed locations;
- one checksum duplicate group with two paths;
- JPEG image kind and dimensions extracted;
- WAV codec and duration extracted;
- MP4 codec, dimensions, and duration extracted;
- four unique image/video/audio thumbnail derivatives created, verified, and
  hashed with source-checksum lineage;
- three catalog passes retained four asset rows and five location rows;
- zero catalog failures;
- schema-3 SQLite integrity and foreign-key checks passed;
- a local online database backup passed integrity verification;
- all five ATLAS source hashes still matched after the complete run.

## Finding and correction

The first pass showed that Beacon's FFprobe allowlist did not include still
images. Beacon 0.3.1 adds explicit JPEG, PNG, TIFF, GIF, BMP, and WebP probing,
preserves the `image` kind, and suppresses FFprobe's meaningless single-frame
duration. Two automated tests cover the correction.

The complete suite now passes 30 tests with real FFprobe and FFmpeg enabled.

## Native application verification

The source client and the frozen Beacon 0.6.0 executable were both rendered
against the use-test database. The library correctly showed image, video, and
audio technical metadata, displayed all four unique thumbnails, and exposed
both locations for the renamed duplicate.

The native temporary preview was exercised for a full image, audio with
waveform/playback/scrubbing, and video with playback/scrubbing. Automated
visual checks used muted playback; ordinary interactive playback remains
enabled. The synthetic text fixture was rendered as bounded, selectable,
read-only plain text. The fallback path for binary file types exposes metadata
without opening the source in an editor.

Space was also exercised as an application-level shortcut while the Preview
button held keyboard focus. It opened and closed the selected asset instead of
re-pressing the focused button.

The later bounded librarian pilot attached one checksum-bound candidate result
to each of the four unique media identities plus the synthetic note. The
renamed duplicate remained one asset with two locations and one analysis. See
[`AI_ANALYSIS_PILOT.md`](AI_ANALYSIS_PILOT.md).

The initial standalone launch exposed that UseTest-01 was still intentionally
isolated from Beacon's live database. No media or catalog records were lost.
After a verified live-database backup, the five approved NVMe locations were
cataloged into the live database. The exact no-argument packaged launch then
showed five total assets: four unique media assets plus the synthetic note. The
Library now labels that context **Live catalog**.

Private screenshots and detailed filenames remain only in the isolated runtime
evidence folder; they are intentionally excluded from Git.

Release executable:

```text
C:\Development\ATLAS\dist\releases\0.6.0\ATLAS Beacon\ATLAS Beacon.exe
```

Release package:

```text
C:\Development\ATLAS\dist\ATLAS-Beacon-0.6.0-win64.zip
```

Executable SHA-256:

```text
D353EC59051C1978AACE0DC452E6B881CC6C6E740382BD6DB4EEF2B118787FDB
```

Package SHA-256:

```text
F22B1DE8309D86674B8B07708CEF2B5555AB16E5D271BEDD96A736689F2F2020
```

The private development build remains unsigned.
