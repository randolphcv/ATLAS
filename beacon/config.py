"""Deployment configuration.

AGENTS.md section 3 forbids a deployment path in this repository, and section
10 requires that no module hardcode a drive letter or an archive path. Every
location Beacon touches is resolved here, from environment variables or from a
settings file at the runtime root.

Three locations, per AGENTS.md section 5:

- **repository** — source. Never written to at runtime. Not resolved here.
- **runtime root** — configuration, working cache, application logs. Local and
  disposable. Derived from the platform's program-data directory.
- **archive root** — originals, derivative content, the catalog of record, and
  archive-scoped logs. Configured per deployment; there is no safe default.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

LOGGER = logging.getLogger("beacon.config")

ARCHIVE_ROOT_SETTING = "BEACON_ARCHIVE_ROOT"
SETTINGS_FILENAME = "settings.json"

# Directory names beneath an archive root. Names, not paths.
INBOX_DIRNAME = "Inbox"
LIBRARY_DIRNAME = "Library"
ASSETS_DIRNAME = "Assets"
PROJECTS_DIRNAME = "Projects"
BEACON_DIRNAME = "Beacon"
CATALOG_FILENAME = "beacon.db"

# Subdirectories of <ARCHIVE_ROOT>/Beacon, matching the documented archive
# tree in docs/ATLAS_PROJECT_MEMORY.md.
DATABASE_DIRNAME = "Database"
THUMBNAILS_DIRNAME = "Thumbnails"
PROXIES_DIRNAME = "Proxies"
TRANSCRIPTS_DIRNAME = "Transcripts"
LOGS_DIRNAME = "Logs"
DERIVATIVES_DIRNAME = "Derivatives"

_warned: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key not in _warned:
        _warned.add(key)
        LOGGER.warning(message)


def program_data_root() -> Path:
    """Platform program-data directory, without naming a drive."""
    configured = os.environ.get("PROGRAMDATA")
    if configured:
        return Path(configured)
    return Path(os.sep) / "ProgramData"


def runtime_root() -> Path:
    """Local, disposable runtime state. Configuration lives here."""
    configured = os.environ.get("BEACON_RUNTIME_ROOT")
    if configured:
        return Path(configured)
    return program_data_root() / "ATLAS" / BEACON_DIRNAME


def settings_path() -> Path:
    return runtime_root() / SETTINGS_FILENAME


def load_settings() -> dict[str, str]:
    """Read the deployment settings file. Absent or unreadable means empty."""
    path = settings_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v is not None}


def _setting(name: str) -> str | None:
    """Environment first, then the settings file. Blank counts as unset."""
    value = os.environ.get(name)
    if value and value.strip():
        return value.strip()
    value = load_settings().get(name)
    if value and value.strip():
        return value.strip()
    return None


def configured_archive_root() -> Path | None:
    """The archive root, or None when this deployment has not set one."""
    value = _setting(ARCHIVE_ROOT_SETTING)
    return Path(value) if value else None


def archive_root() -> Path:
    """The archive root, degrading to a local placeholder with a warning.

    There is no safe default for an archive root: guessing a volume would be
    worse than failing. When the setting is absent this returns a location
    beneath the runtime root so imports and tests still resolve, and warns
    naming the setting to add. Archive operations against it will find nothing.
    """
    configured = configured_archive_root()
    if configured is not None:
        return configured
    _warn_once(
        "archive_root",
        f"{ARCHIVE_ROOT_SETTING} is not configured. Archive operations are "
        f"unavailable until it is set, in the environment or in "
        f"{settings_path()}.",
    )
    return runtime_root() / "archive-root-not-configured"


def archive_root_is_configured() -> bool:
    return configured_archive_root() is not None


def inbox_root() -> Path:
    value = _setting("BEACON_INBOX")
    return Path(value) if value else archive_root() / INBOX_DIRNAME


def library_root() -> Path:
    return archive_root() / LIBRARY_DIRNAME


def assets_root() -> Path:
    return archive_root() / ASSETS_DIRNAME


def projects_root() -> Path:
    return archive_root() / PROJECTS_DIRNAME


def approved_destination_roots() -> tuple[Path, ...]:
    """Managed placement may only write beneath these."""
    return (library_root(), assets_root(), projects_root())


def catalog_path() -> Path:
    """The catalog of record.

    Preference order: explicit setting, then beneath the archive root when one
    is configured, then the historical local runtime location. The last case
    warns rather than silently stranding an installation that predates the
    archive-root setting.
    """
    value = _setting("BEACON_DB")
    if value:
        return Path(value)
    if archive_root_is_configured():
        return (
            archive_root() / BEACON_DIRNAME / DATABASE_DIRNAME
            / CATALOG_FILENAME
        )
    legacy = runtime_root() / CATALOG_FILENAME
    _warn_once(
        "catalog_path",
        f"Using the local catalog at {legacy}. The catalog belongs at the "
        f"archive root. Set {ARCHIVE_ROOT_SETTING}, or BEACON_DB, in "
        f"{settings_path()}.",
    )
    return legacy


def _derivative_location(setting: str, name: str, legacy_name: str) -> Path:
    """Derivative content belongs at the archive root. AGENTS.md section 4."""
    value = _setting(setting)
    if value:
        return Path(value)
    if archive_root_is_configured():
        return archive_root() / BEACON_DIRNAME / name
    legacy = runtime_root() / legacy_name
    _warn_once(
        f"derivative:{name}",
        f"Using the local {name} directory at {legacy}. Derivative content "
        f"belongs at the archive root. Set {ARCHIVE_ROOT_SETTING}, or "
        f"{setting}, in {settings_path()}.",
    )
    return legacy


def backups_dir() -> Path:
    return _derivative_location(
        "BEACON_BACKUP_DIR", f"{DATABASE_DIRNAME}/backups", "backups"
    )


def derivatives_root() -> Path:
    return _derivative_location(
        "BEACON_DERIVATIVES_DIR", DERIVATIVES_DIRNAME, "derivatives"
    )


def thumbnails_dir() -> Path:
    value = _setting("BEACON_THUMBNAIL_ROOT")
    if value:
        return Path(value)
    return _derivative_location(
        "BEACON_THUMBNAIL_ROOT", THUMBNAILS_DIRNAME, "derivatives/thumbnails"
    )


def previews_dir() -> Path:
    return _derivative_location(
        "BEACON_PREVIEW_DIR", PROXIES_DIRNAME, "derivatives/previews"
    )


def transcripts_dir() -> Path:
    return _derivative_location(
        "BEACON_TRANSCRIPT_DIR", TRANSCRIPTS_DIRNAME, "derivatives/transcripts"
    )


def archive_log_dir() -> Path:
    """Logs that record archive content: real filenames and paths."""
    return _derivative_location("BEACON_ARCHIVE_LOG_DIR", LOGS_DIRNAME, "logs")


def runtime_log_dir() -> Path:
    """Logs that record only program behavior. Local and disposable."""
    value = _setting("BEACON_RUNTIME_LOG_DIR")
    return Path(value) if value else runtime_root() / "logs"


_LIKE_ESCAPE = "~"


def _like_prefix(path: Path) -> str:
    """Lowercased SQL LIKE prefix matching everything beneath a directory.

    SQLite treats a backslash as an ordinary character, so a Windows separator
    needs no escaping. The LIKE wildcards do: ``_`` is common in folder names
    and would otherwise match any single character.
    """
    text = str(path).rstrip("\\/").casefold()
    for special in (_LIKE_ESCAPE, "%", "_"):
        text = text.replace(special, _LIKE_ESCAPE + special)
    return text.replace("'", "''") + os.sep + "%"


def location_rank_sql(column: str) -> str:
    """CASE expression ranking a location column by archive tier.

    Placed locations rank first, then approved archive destinations, then the
    Inbox, then anything else. Prefixes come from configuration, so no drive
    letter appears in source.

    The prefixes are interpolated rather than bound. They are trusted
    deployment configuration, not user input, and the surrounding queries bind
    their own parameters positionally; adding more would reorder every call
    site. Quotes are doubled and LIKE wildcards escaped regardless.
    """
    clause = f"' ESCAPE '{_LIKE_ESCAPE}'"
    approved = " OR ".join(
        f"lower({column}) LIKE '{_like_prefix(root)}{clause}"
        for root in approved_destination_roots()
    )
    inbox = f"lower({column}) LIKE '{_like_prefix(inbox_root())}{clause}"
    return (
        "CASE\n"
        f"    WHEN {approved}\n"
        "    THEN 1\n"
        f"    WHEN {inbox}\n"
        "    THEN 2\n"
        "    ELSE 3\n"
        "END"
    )


def archive_tier_when_sql(column: str, first_rank: int = 1) -> str:
    """The archive-tier WHEN clauses of a location ranking CASE.

    Returned without CASE/END so a caller can keep its own leading branches,
    such as ranking an audited managed-move destination ahead of everything.
    ``first_rank`` is the rank given to an approved destination; the Inbox
    takes the next value.
    """
    clause = f"' ESCAPE '{_LIKE_ESCAPE}'"
    approved = "\n  OR ".join(
        f"lower({column}) LIKE '{_like_prefix(root)}{clause}"
        for root in approved_destination_roots()
    )
    inbox = f"lower({column}) LIKE '{_like_prefix(inbox_root())}{clause}"
    return (
        f"WHEN {approved}\nTHEN {first_rank}\n"
        f"WHEN {inbox}\nTHEN {first_rank + 1}"
    )
