from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

SUPPORTED_MEDIA_EXTENSIONS = {
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


def should_probe(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS


def probe(path: Path) -> dict[str, Any] | None:
    if not should_probe(path):
        return None
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
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return {"error": f"invalid ffprobe JSON: {error}", "returncode": 0}
