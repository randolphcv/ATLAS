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

The complete suite now passes 20 tests with real FFprobe and FFmpeg enabled.

## Native application verification

The source client and the frozen Beacon 0.4.0 executable were both rendered
against the use-test database. The library correctly showed image, video, and
audio technical metadata, displayed all four unique thumbnails, and exposed
both locations for the renamed duplicate.

The native temporary preview was exercised for a full image, audio with
waveform/playback/scrubbing, and video with playback/scrubbing. Automated
visual checks used muted playback; ordinary interactive playback remains
enabled. The fallback path for other file types exposes metadata without
opening the source in an editor.

Private screenshots and detailed filenames remain only in the isolated runtime
evidence folder; they are intentionally excluded from Git.

Release executable:

```text
C:\Development\ATLAS\dist\releases\0.4.0\ATLAS Beacon\ATLAS Beacon.exe
```

Release package:

```text
C:\Development\ATLAS\dist\ATLAS-Beacon-0.4.0-win64.zip
```

Executable SHA-256:

```text
426D7DC8DE87685F7436AB1D246833BC7E7C5C2B29AB58F08700880B97FD2570
```

Package SHA-256:

```text
0F38CFA8CA75C5B17CC37DC21484DA3F1ABD7D6B935A28A44F000239D49BEB2F
```

The private development build remains unsigned.
