# Local Music Intelligence

Beacon 0.13 uses a separate Python 3.11 runtime at:

`C:\ProgramData\ATLAS\MusicRuntime`

This boundary keeps the music stack and its large CUDA/TensorFlow dependencies
out of Beacon's packaged Python 3.12 application. Recreate or repair it with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\setup_music_runtime.ps1
```

## Staged analysis

1. Librosa computes rhythm, chroma, estimated BPM, key, and a beat-aligned
   major/minor chord path.
2. Weakly tonal or unstable audio stops at this inexpensive stage.
3. Confidently musical audio runs Spotify Basic Pitch through its ONNX model
   and saves a verified MIDI derivative.
4. Music that remains confident after note transcription runs Demucs on the
   RTX 3060 and saves verified bass, drums, vocals, and other stems.

Every result is bound to the catalog asset UUID and source SHA-256. Beacon
re-hashes the source before and after analysis, hashes every derivative, and
stores derivatives outside the original hierarchy. Reanalysis reuses the
result only when the source hash and worker version both match.

Key, chord, tempo, and melody output are estimates. The UI exposes confidence
and keeps these results separate from locked technical facts.

## Licensing boundary

- Demucs is used as an isolated local model runner.
- Basic Pitch is Apache-2.0 licensed.
- Librosa provides the first BPM/key/chord implementation.
- Essentia is not installed or distributed in Beacon 0.13 because its AGPL
  license and Windows packaging require a deliberate product-distribution
  decision. It remains a possible replaceable adapter.

## Verified calibration

The first synthetic fixture was a 16-second C-major four-chord progression.
Beacon estimated C major and approximately 92 BPM, emitted MIDI with 12 note
events, and produced four verified Demucs stems.

The first bounded live check used a six-second cataloged spoken recording. The
initial gate was too permissive. Worker v2 reduced its music confidence from
84% to 31% using key and chord stability, correctly skipping MIDI and stem
generation. This calibration is retained as the regression boundary.
