from __future__ import annotations

import json
import io
import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import sha256_file
from .database import connect, migrate, record_event
from .media import probe

LOGGER = logging.getLogger("beacon.thumbnails")
GENERATOR = "beacon-ffmpeg-thumbnail-v1"
RAW_GENERATOR = "beacon-rawpy-thumbnail-v1"
HEIF_GENERATOR = "beacon-pillow-heif-jpeg-thumbnail-v2"
THUMBNAIL_SIZE = (640, 360)
HEIF_EXTENSIONS = {".heic", ".heif"}
RAW_EXTENSIONS = {
    ".3fr", ".arw", ".cr2", ".cr3", ".dng", ".erf", ".fff", ".iiq",
    ".kdc", ".mef", ".mos", ".mrw", ".nef", ".nrw", ".orf", ".pef",
    ".raf", ".raw", ".rw2", ".sr2", ".srf", ".x3f",
}


@dataclass(frozen=True)
class ThumbnailResult:
    path: str
    sha256: str
    size_bytes: int
    source_sha256: str
    generator: str
    created: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _thumbnail_directory(db_path: Path) -> Path:
    configured = os.environ.get("BEACON_THUMBNAIL_ROOT")
    if configured:
        return Path(configured)
    program_data = Path(
        os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    ) / "ATLAS" / "Beacon" / "beacon.db"
    archive_root = Path(r"J:\Beacon\Thumbnails")
    try:
        if db_path.resolve() == program_data.resolve() and archive_root.parent.is_dir():
            return archive_root
    except OSError:
        pass
    return db_path.resolve().parent / "derivatives" / "thumbnails"


def _media_kind(
    metadata: dict[str, Any] | None,
    source: Path | None = None,
) -> str | None:
    if source is not None and source.suffix.lower() in (
        RAW_EXTENSIONS | HEIF_EXTENSIONS
    ):
        return "image"
    if not metadata or metadata.get("error"):
        return None
    if metadata.get("beacon_kind") == "image":
        return "image"
    streams = metadata.get("streams") or []
    kinds = {stream.get("codec_type") for stream in streams}
    if "video" in kinds:
        return "video"
    if "audio" in kinds:
        return "audio"
    return None


def _render_raw_thumbnail(source: Path, temporary: Path) -> None:
    import rawpy
    from PIL import Image

    with rawpy.imread(str(source)) as raw:
        try:
            thumb = raw.extract_thumb()
            image = Image.open(io.BytesIO(thumb.data)).convert("RGB")
        except (rawpy.LibRawNoThumbnailError, OSError, ValueError):
            image = Image.fromarray(
                raw.postprocess(
                    use_camera_wb=True,
                    half_size=True,
                    no_auto_bright=False,
                    output_bps=8,
                )
            )
    image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", THUMBNAIL_SIZE, "#0B1015")
    canvas.paste(
        image,
        ((THUMBNAIL_SIZE[0] - image.width) // 2,
         (THUMBNAIL_SIZE[1] - image.height) // 2),
    )
    canvas.save(temporary, format="PNG", optimize=True)


def _render_heif_thumbnail(source: Path, temporary: Path) -> None:
    from PIL import Image
    from pillow_heif import open_heif

    image = open_heif(source).to_pillow().convert("RGB")
    image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
    image.save(
        temporary,
        format="JPEG",
        quality=86,
        optimize=False,
        progressive=False,
    )


def _existing_thumbnail(
    db_path: Path,
    *,
    asset_id: str,
    source_sha256: str,
) -> ThumbnailResult | None:
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            """
            SELECT path, sha256, size_bytes, source_sha256, generator
            FROM derivatives
            WHERE asset_id = ? AND kind = 'thumbnail'
              AND source_sha256 = ? AND state = 'complete'
            """,
            (asset_id, source_sha256),
        ).fetchone()
    if row is None:
        return None
    path = Path(row["path"])
    if not path.is_file():
        return None
    if path.stat().st_size != row["size_bytes"]:
        return None
    if sha256_file(path) != row["sha256"]:
        return None
    return ThumbnailResult(
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
    kind: str,
) -> list[str]:
    width, height = THUMBNAIL_SIZE
    common = [executable, "-hide_banner", "-loglevel", "error", "-y"]
    if kind == "audio":
        return [
            *common,
            "-i",
            str(source),
            "-filter_complex",
            (
                "aformat=channel_layouts=mono,"
                f"showwavespic=s={width}x{height}:colors=0x64AEB1"
            ),
            "-frames:v",
            "1",
            str(temporary),
        ]
    seek = ["-ss", "1"] if kind == "video" else []
    return [
        *common,
        *seek,
        "-i",
        str(source),
        "-vf",
        (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x0B1015"
        ),
        "-frames:v",
        "1",
        str(temporary),
    ]


def ensure_thumbnail(
    source: Path,
    db_path: Path,
    *,
    asset_id: str,
    source_sha256: str,
    media_metadata: dict[str, Any] | None,
) -> ThumbnailResult | None:
    """Create and verify a separate preview derivative without editing the source."""
    kind = _media_kind(media_metadata, source)
    if kind is None:
        return None
    is_raw = source.suffix.lower() in RAW_EXTENSIONS
    is_heif = source.suffix.lower() in HEIF_EXTENSIONS
    executable = os.environ.get("BEACON_FFMPEG") or shutil.which("ffmpeg")
    if executable is None and not (is_raw or is_heif):
        LOGGER.warning("thumbnail skipped because ffmpeg is unavailable")
        return None

    existing = _existing_thumbnail(
        db_path,
        asset_id=asset_id,
        source_sha256=source_sha256,
    )
    if existing is not None:
        return existing

    source = source.resolve(strict=True)
    source_stat = source.stat()
    thumbnail_dir = _thumbnail_directory(db_path)
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    output_suffix = ".jpg" if is_heif else ".png"
    destination = thumbnail_dir / f"{asset_id}{output_suffix}"
    temporary = (
        thumbnail_dir
        / f".{asset_id}.{uuid.uuid4().hex}.partial{output_suffix}"
    )
    try:
        generator = (
            RAW_GENERATOR
            if is_raw
            else HEIF_GENERATOR
            if is_heif
            else GENERATOR
        )
        if is_raw:
            _render_raw_thumbnail(source, temporary)
        elif is_heif:
            _render_heif_thumbnail(source, temporary)
        else:
            completed = subprocess.run(
                _ffmpeg_command(str(executable), source, temporary, kind),
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    completed.stderr.strip()
                    or f"ffmpeg exited with code {completed.returncode}"
                )
        verification = probe(temporary)
        if (
            verification is None
            or verification.get("error")
            or not temporary.is_file()
            or temporary.stat().st_size == 0
        ):
            raise RuntimeError("thumbnail verification failed")
        stream = (verification.get("streams") or [{}])[0]
        if not stream.get("width") or not stream.get("height"):
            raise RuntimeError("thumbnail has no verified dimensions")
        after_stat = source.stat()
        if (after_stat.st_size, after_stat.st_mtime_ns) != (
            source_stat.st_size,
            source_stat.st_mtime_ns,
        ):
            raise RuntimeError("source changed while thumbnail was generated")

        derivative_sha256 = sha256_file(temporary)
        derivative_size = temporary.stat().st_size
        os.replace(temporary, destination)
        now = _utc_now()
        details = {
            "format": "jpeg" if is_heif else "png",
            "height": int(stream["height"]),
            "media_kind": kind,
            "width": int(stream["width"]),
        }
        with connect(db_path) as connection:
            migrate(connection)
            connection.execute(
                """
                INSERT INTO derivatives(
                    id, asset_id, kind, path, source_sha256, sha256,
                    size_bytes, generator, state, details_json,
                    created_at, verified_at
                ) VALUES (?, ?, 'thumbnail', ?, ?, ?, ?, ?, 'complete', ?, ?, ?)
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
                    str(destination),
                    source_sha256,
                    derivative_sha256,
                    derivative_size,
                    generator,
                    json.dumps(details, sort_keys=True),
                    now,
                    now,
                ),
            )
            record_event(
                connection,
                kind="thumbnail",
                state="complete",
                message="Verified thumbnail derivative created",
                asset_id=asset_id,
                location_path=str(destination),
                details={
                    **details,
                    "generator": generator,
                    "sha256": derivative_sha256,
                    "size_bytes": derivative_size,
                    "source_sha256": source_sha256,
                },
            )
        return ThumbnailResult(
            path=str(destination),
            sha256=derivative_sha256,
            size_bytes=derivative_size,
            source_sha256=source_sha256,
            generator=generator,
            created=True,
        )
    except (
        ImportError,
        OSError,
        RuntimeError,
        ValueError,
        subprocess.TimeoutExpired,
    ) as error:
        temporary.unlink(missing_ok=True)
        LOGGER.exception("thumbnail generation failed asset_id=%s", asset_id)
        with connect(db_path) as connection:
            migrate(connection)
            record_event(
                connection,
                kind="thumbnail",
                state="failed",
                message=f"Thumbnail generation failed: {error}",
                asset_id=asset_id,
                location_path=str(source),
                details={
                    "generator": (
                        RAW_GENERATOR
                        if source.suffix.lower() in RAW_EXTENSIONS
                        else HEIF_GENERATOR
                        if source.suffix.lower() in HEIF_EXTENSIONS
                        else GENERATOR
                    ),
                    "source_sha256": source_sha256,
                },
            )
        return None
