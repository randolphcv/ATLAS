from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any

from .catalog import sha256_file
from .database import connect, migrate, record_event
from .media import probe
from .processes import hidden_creation_flags

LOGGER = logging.getLogger("beacon.preview_derivatives")
GENERATOR = "beacon-ffmpeg-cfr-preview-v2"
DERIVATIVE_KIND = "preview_video"
QUICKTIME_EXTENSIONS = {".mov", ".m4v", ".mp4"}
APPLE_COMPATIBILITY_FRAME_RATE = 59.0
GENERAL_COMPATIBILITY_FRAME_RATE = 90.0


@dataclass(frozen=True)
class VideoPreviewResult:
    path: str
    sha256: str
    size_bytes: int
    source_sha256: str
    generator: str
    created: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview_directory(db_path: Path) -> Path:
    configured = os.environ.get("BEACON_PREVIEW_ROOT")
    if configured:
        return Path(configured)
    return db_path.resolve().parent / "derivatives" / "previews"


def _rate(value: object) -> float:
    try:
        return float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return 0.0


def needs_video_compatibility_preview(
    source: Path,
    media_metadata: dict[str, Any] | None,
) -> bool:
    """Identify Apple/high-frame-rate QuickTime that needs stable CFR playback."""
    if source.suffix.lower() not in QUICKTIME_EXTENSIONS or not media_metadata:
        return False
    streams = media_metadata.get("streams") or []
    video_streams = [
        stream for stream in streams if stream.get("codec_type") == "video"
    ]
    if not video_streams:
        return False
    frame_rate = max(
        (
            _rate(stream.get(field))
            for stream in video_streams
            for field in ("r_frame_rate", "avg_frame_rate")
        ),
        default=0.0,
    )
    serialized = json.dumps(media_metadata, sort_keys=True).lower()
    apple_quicktime = (
        "com.apple.quicktime" in serialized
        or '"make": "apple"' in serialized
        or '"manufacturer": "apple"' in serialized
    )
    return frame_rate >= GENERAL_COMPATIBILITY_FRAME_RATE or (
        apple_quicktime and frame_rate >= APPLE_COMPATIBILITY_FRAME_RATE
    )


@lru_cache(maxsize=4)
def _accelerated_encoder(executable: str) -> str | None:
    try:
        completed = subprocess.run(
            [executable, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            creationflags=hidden_creation_flags(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode == 0 and "h264_nvenc" in completed.stdout:
        return "h264_nvenc"
    return None


def _existing_preview(
    db_path: Path,
    *,
    asset_id: str,
    source_sha256: str,
) -> VideoPreviewResult | None:
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            """
            SELECT path, sha256, size_bytes, source_sha256, generator
            FROM derivatives
            WHERE asset_id = ? AND kind = ?
              AND source_sha256 = ? AND state = 'complete'
            """,
            (asset_id, DERIVATIVE_KIND, source_sha256),
        ).fetchone()
    if row is None:
        return None
    path = Path(row["path"])
    if not path.is_file() or path.stat().st_size != row["size_bytes"]:
        return None
    if sha256_file(path) != row["sha256"]:
        return None
    return VideoPreviewResult(
        path=str(path),
        sha256=row["sha256"],
        size_bytes=row["size_bytes"],
        source_sha256=row["source_sha256"],
        generator=row["generator"],
        created=False,
    )


def _ffmpeg_command(
    executable: str,
    source: Path,
    temporary: Path,
    *,
    encoder: str,
) -> list[str]:
    command = [
        executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-sn",
        "-dn",
        "-vf",
        (
            "fps=30,"
            "scale=1280:720:force_original_aspect_ratio=decrease:"
            "force_divisible_by=2"
        ),
        "-c:v",
        encoder,
    ]
    if encoder == "h264_nvenc":
        command.extend(
            [
                "-preset",
                "p1",
                "-tune",
                "ll",
                "-rc",
                "vbr",
                "-cq",
                "30",
                "-b:v",
                "0",
            ]
        )
    else:
        command.extend(
            [
                "-preset",
                "ultrafast",
                "-crf",
                "30",
            ]
        )
    command.extend(
        [
        "-pix_fmt",
        "yuv420p",
        "-fps_mode",
        "cfr",
        "-g",
        "60",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(temporary),
        ]
    )
    return command


def ensure_video_preview(
    source: Path,
    db_path: Path,
    *,
    asset_id: str,
    source_sha256: str,
) -> VideoPreviewResult:
    """Create an atomic checksum-bound CFR proxy without changing the source."""
    executable = os.environ.get("BEACON_FFMPEG") or shutil.which("ffmpeg")
    if executable is None:
        raise RuntimeError("FFmpeg is unavailable for compatible video preview")

    existing = _existing_preview(
        db_path,
        asset_id=asset_id,
        source_sha256=source_sha256,
    )
    if existing is not None:
        return existing

    source = source.resolve(strict=True)
    source_stat = source.stat()
    preview_dir = _preview_directory(db_path)
    preview_dir.mkdir(parents=True, exist_ok=True)
    required_free = max(512 * 1024 * 1024, source_stat.st_size)
    if shutil.disk_usage(preview_dir).free < required_free:
        raise RuntimeError("Insufficient free space for compatible video preview")

    destination = preview_dir / f"{asset_id}.mp4"
    temporary = preview_dir / f".{asset_id}.{uuid.uuid4().hex}.partial.mp4"
    try:
        encoders = [
            encoder
            for encoder in (
                _accelerated_encoder(str(executable)),
                "libx264",
            )
            if encoder
        ]
        completed: subprocess.CompletedProcess[str] | None = None
        selected_encoder = ""
        errors: list[str] = []
        for encoder in dict.fromkeys(encoders):
            temporary.unlink(missing_ok=True)
            completed = subprocess.run(
                _ffmpeg_command(
                    str(executable),
                    source,
                    temporary,
                    encoder=encoder,
                ),
                capture_output=True,
                text=True,
                check=False,
                timeout=1800,
                creationflags=hidden_creation_flags(),
            )
            if completed.returncode == 0 and temporary.is_file():
                selected_encoder = encoder
                break
            errors.append(
                completed.stderr.strip()
                or f"{encoder} exited with code {completed.returncode}"
            )
        if completed is None or not selected_encoder:
            raise RuntimeError(
                " ; ".join(errors)
                or "FFmpeg could not create a compatible preview"
            )
        verification = probe(temporary)
        if (
            verification is None
            or verification.get("error")
            or not temporary.is_file()
            or temporary.stat().st_size == 0
        ):
            raise RuntimeError("compatible video preview verification failed")
        video_stream = next(
            (
                stream
                for stream in verification.get("streams") or []
                if stream.get("codec_type") == "video"
            ),
            None,
        )
        if video_stream is None or video_stream.get("codec_name") != "h264":
            raise RuntimeError("compatible video preview is not verified H.264")
        after_stat = source.stat()
        if (after_stat.st_size, after_stat.st_mtime_ns) != (
            source_stat.st_size,
            source_stat.st_mtime_ns,
        ):
            raise RuntimeError("source changed while video preview was generated")

        derivative_sha256 = sha256_file(temporary)
        derivative_size = temporary.stat().st_size
        os.replace(temporary, destination)
        now = _utc_now()
        details = {
            "codec": "h264",
            "encoder": selected_encoder,
            "frame_rate": 30,
            "maximum_dimensions": "1280x720",
            "media_kind": "video",
            "purpose": "stable local QuickTime preview",
        }
        with connect(db_path) as connection:
            migrate(connection)
            connection.execute(
                """
                INSERT INTO derivatives(
                    id, asset_id, kind, path, source_sha256, sha256,
                    size_bytes, generator, state, details_json,
                    created_at, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'complete', ?, ?, ?)
                ON CONFLICT(asset_id, kind, source_sha256) DO UPDATE SET
                    path = excluded.path,
                    sha256 = excluded.sha256,
                    size_bytes = excluded.size_bytes,
                    generator = excluded.generator,
                    state = excluded.state,
                    details_json = excluded.details_json,
                    verified_at = excluded.verified_at
                """,
                (
                    str(uuid.uuid4()),
                    asset_id,
                    DERIVATIVE_KIND,
                    str(destination),
                    source_sha256,
                    derivative_sha256,
                    derivative_size,
                    GENERATOR,
                    json.dumps(details, sort_keys=True),
                    now,
                    now,
                ),
            )
            record_event(
                connection,
                kind="preview",
                state="complete",
                message="Verified compatible video preview created",
                asset_id=asset_id,
                location_path=str(destination),
                details={
                    **details,
                    "generator": GENERATOR,
                    "sha256": derivative_sha256,
                    "size_bytes": derivative_size,
                    "source_sha256": source_sha256,
                },
            )
        return VideoPreviewResult(
            path=str(destination),
            sha256=derivative_sha256,
            size_bytes=derivative_size,
            source_sha256=source_sha256,
            generator=GENERATOR,
            created=True,
        )
    except (
        OSError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as error:
        temporary.unlink(missing_ok=True)
        LOGGER.exception("video preview generation failed asset_id=%s", asset_id)
        with connect(db_path) as connection:
            migrate(connection)
            record_event(
                connection,
                kind="preview",
                state="failed",
                message=f"Compatible video preview failed: {error}",
                asset_id=asset_id,
                location_path=str(source),
                details={
                    "generator": GENERATOR,
                    "source_sha256": source_sha256,
                },
            )
        raise
