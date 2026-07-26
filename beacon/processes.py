from __future__ import annotations

import os
import subprocess


def hidden_creation_flags() -> int:
    """Prevent packaged background helpers from opening Windows consoles."""
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
