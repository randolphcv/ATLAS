from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import librosa
import numpy as np

WORKER_VERSION = "beacon-music-v3"
PITCH_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized(value: np.ndarray) -> np.ndarray:
    total = float(np.linalg.norm(value))
    return value / total if total else value


def _key(chroma: np.ndarray) -> tuple[str, float]:
    mean = _normalized(np.mean(chroma, axis=1))
    candidates: list[tuple[float, str]] = []
    for root in range(12):
        candidates.append(
            (float(np.dot(mean, _normalized(np.roll(MAJOR_PROFILE, root)))), f"{PITCH_NAMES[root]} major")
        )
        candidates.append(
            (float(np.dot(mean, _normalized(np.roll(MINOR_PROFILE, root)))), f"{PITCH_NAMES[root]} minor")
        )
    candidates.sort(reverse=True)
    confidence = max(0.0, min(1.0, (candidates[0][0] - candidates[1][0]) * 4))
    return candidates[0][1], confidence


def _chord_templates() -> list[tuple[str, np.ndarray]]:
    templates = []
    for root in range(12):
        for label, intervals in (("", (0, 4, 7)), ("m", (0, 3, 7))):
            template = np.zeros(12)
            template[[(root + interval) % 12 for interval in intervals]] = 1
            templates.append((f"{PITCH_NAMES[root]}{label}", _normalized(template)))
    return templates


def _chords(
    chroma: np.ndarray, beat_frames: np.ndarray, frame_times: np.ndarray
) -> tuple[list[dict[str, Any]], float]:
    if chroma.shape[1] == 0:
        return [], 0.0
    boundaries = np.unique(
        np.concatenate(([0], beat_frames.astype(int), [chroma.shape[1]]))
    )
    templates = _chord_templates()
    sequence: list[dict[str, Any]] = []
    confidences = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        if end <= start:
            continue
        vector = _normalized(np.mean(chroma[:, start:end], axis=1))
        scores = sorted(
            ((float(np.dot(vector, template)), name) for name, template in templates),
            reverse=True,
        )
        confidence = max(0.0, min(1.0, (scores[0][0] - scores[1][0]) * 3))
        confidences.append(confidence)
        item = {
            "chord": scores[0][1],
            "start_seconds": round(float(frame_times[min(start, len(frame_times) - 1)]), 3),
            "confidence": round(confidence, 3),
        }
        if sequence and sequence[-1]["chord"] == item["chord"]:
            continue
        sequence.append(item)
    return sequence[:512], float(np.mean(confidences)) if confidences else 0.0


def _note_summary(note_events: list[Any]) -> dict[str, Any]:
    pitches = [int(event[2]) for event in note_events if len(event) >= 3]
    if not pitches:
        return {"note_count": 0, "pitch_range": "", "prominent_notes": []}
    counts = np.bincount(pitches, minlength=128)
    prominent = [
        librosa.midi_to_note(index)
        for index in np.argsort(counts)[::-1]
        if counts[index] > 0
    ][:12]
    return {
        "note_count": len(pitches),
        "pitch_range": f"{librosa.midi_to_note(min(pitches))}–{librosa.midi_to_note(max(pitches))}",
        "prominent_notes": prominent,
    }


def analyze(
    source: Path, output: Path, *, full: bool, stems_enabled: bool
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    y, sample_rate = librosa.load(source, sr=22_050, mono=True)
    if not len(y):
        raise ValueError("Decoded audio is empty.")
    hop = 2048
    harmonic, percussive = librosa.effects.hpss(y)
    tempo, beats = librosa.beat.beat_track(y=percussive, sr=sample_rate, hop_length=hop)
    tempo_value = float(np.asarray(tempo).reshape(-1)[0])
    chroma = librosa.feature.chroma_stft(y=harmonic, sr=sample_rate, hop_length=hop)
    frame_times = librosa.frames_to_time(
        np.arange(chroma.shape[1]), sr=sample_rate, hop_length=hop
    )
    key, key_confidence = _key(chroma)
    chords, chord_confidence = _chords(chroma, beats, frame_times)
    flatness = float(np.mean(librosa.feature.spectral_flatness(y=y)))
    chroma_peak = float(np.mean(np.max(chroma, axis=0)))
    beat_strength = min(1.0, len(beats) / max(1.0, len(y) / sample_rate / 2))
    music_confidence = max(
        0.0,
        min(
            1.0,
            0.10 * min(1.0, chroma_peak * 2.2)
            + 0.10 * (1.0 - min(1.0, flatness * 5))
            + 0.10 * beat_strength
            + 0.40 * chord_confidence
            + 0.30 * key_confidence,
        ),
    )
    result: dict[str, Any] = {
        "worker_version": WORKER_VERSION,
        "status": "complete",
        "duration_seconds": round(len(y) / sample_rate, 3),
        "bpm": round(tempo_value, 2) if math.isfinite(tempo_value) else None,
        "beat_count": int(len(beats)),
        "key": key,
        "key_confidence": round(key_confidence, 3),
        "chord_confidence": round(chord_confidence, 3),
        "chords": chords,
        "music_confidence": round(music_confidence, 3),
        "derivatives": [],
        "notes": {"note_count": 0, "pitch_range": "", "prominent_notes": []},
        "stems": [],
    }
    if full and music_confidence >= 0.42:
        import basic_pitch
        from basic_pitch.inference import predict

        onnx_model = (
            Path(basic_pitch.__file__).parent
            / "saved_models"
            / "icassp_2022"
            / "nmp.onnx"
        )
        _, midi, note_events = predict(
            str(source), model_or_model_path=onnx_model
        )
        midi_path = output / "transcription.mid"
        midi.write(str(midi_path))
        result["notes"] = _note_summary(note_events)
        note_density = min(
            1.0,
            result["notes"]["note_count"]
            / max(1.0, result["duration_seconds"])
            * 2,
        )
        music_confidence = min(
            1.0, 0.65 * music_confidence + 0.35 * note_density
        )
        result["music_confidence"] = round(music_confidence, 3)
        result["derivatives"].append(
            {
                "kind": "music_midi",
                "path": str(midi_path),
                "sha256": _sha256(midi_path),
                "size_bytes": midi_path.stat().st_size,
            }
        )
    if stems_enabled and music_confidence >= 0.60:
        stems_root = output / "stems"
        command = [
            sys.executable,
            "-m",
            "demucs",
            "--device",
            "cuda",
            "--name",
            "htdemucs",
            "--out",
            str(stems_root),
            str(source),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=7200)
        if completed.returncode != 0:
            result["stem_error"] = (completed.stderr or completed.stdout)[-2000:]
        else:
            for stem in sorted(stems_root.rglob("*.wav")):
                entry = {
                    "kind": f"music_stem_{stem.stem}",
                    "path": str(stem),
                    "sha256": _sha256(stem),
                    "size_bytes": stem.stat().st_size,
                }
                result["stems"].append(entry)
                result["derivatives"].append(entry)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--stems", action="store_true")
    args = parser.parse_args()
    if args.status:
        import torch

        print(
            json.dumps(
                {
                    "worker_version": WORKER_VERSION,
                    "python": sys.version.split()[0],
                    "cuda_available": torch.cuda.is_available(),
                    "cuda_device": (
                        torch.cuda.get_device_name(0)
                        if torch.cuda.is_available()
                        else ""
                    ),
                }
            )
        )
        return 0
    if not args.source or not args.output:
        parser.error("--source and --output are required")
    print(
        json.dumps(
            analyze(
                args.source,
                args.output,
                full=args.full,
                stems_enabled=args.stems,
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
