from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def probe(path: Path) -> dict[str, Any] | None:
    executable = shutil.which("ffprobe")
    if executable is None:
        return None
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
    if result.returncode != 0:
        return {"error": result.stderr.strip(), "returncode": result.returncode}
    return json.loads(result.stdout)

