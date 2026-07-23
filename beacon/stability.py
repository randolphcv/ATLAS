from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable


def signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def wait_until_stable(
    path: Path,
    interval_seconds: float = 2.0,
    observations: int = 2,
    sleep: Callable[[float], None] = time.sleep,
) -> os.stat_result:
    if observations < 2:
        raise ValueError("observations must be at least 2")
    previous = signature(path)
    matches = 1
    while matches < observations:
        sleep(interval_seconds)
        current = signature(path)
        if current == previous:
            matches += 1
        else:
            previous = current
            matches = 1
    return path.stat()

