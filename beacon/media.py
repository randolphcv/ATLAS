from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

AUDIO_VIDEO_EXTENSIONS = {
    ".aac",
    ".avi",
    ".flac",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".wav",
    ".webm",
}

IMAGE_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}

SUPPORTED_MEDIA_EXTENSIONS = AUDIO_VIDEO_EXTENSIONS | IMAGE_EXTENSIONS


def should_probe(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS


def probe(path: Path) -> dict[str, Any] | None:
    if not should_probe(path):
        return None
    if path.suffix.lower() in {".heic", ".heif"}:
        try:
            from pillow_heif import open_heif

            image = open_heif(path)
            return {
                "beacon_kind": "image",
                "format": {
                    "format_name": "heif",
                    "format_long_name": "High Efficiency Image File Format",
                },
                "streams": [
                    {
                        "codec_name": "hevc",
                        "codec_type": "image",
                        "height": int(image.size[1]),
                        "width": int(image.size[0]),
                    }
                ],
            }
        except (ImportError, OSError, ValueError) as error:
            return {"error": str(error), "returncode": None}
    executable = os.environ.get("BEACON_FFPROBE") or shutil.which("ffprobe")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": str(error), "returncode": None}
    if result.returncode != 0:
        return {"error": result.stderr.strip(), "returncode": result.returncode}
    try:
        metadata = json.loads(result.stdout)
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            metadata["beacon_kind"] = "image"
        return metadata
    except json.JSONDecodeError as error:
        return {"error": f"invalid ffprobe JSON: {error}", "returncode": 0}
