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
SYSTEM_DIRNAME = "System"
CATALOG_FILENAME = "beacon.db"

# Subdirectories of <ARCHIVE_ROOT>/Beacon, matching the documented archive
# tree in docs/ATLAS_PROJECT_MEMORY.md. System state lives under
# <ARCHIVE_ROOT>/System/Beacon; these hold bulk derivative content.
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
    """Read the deployment settings file. Absent means empty.

    A settings file that exists but cannot be read is reported. Treating a
    malformed file as an absent one makes a typo look identical to an
    unconfigured deployment, and the operator then reads advice telling them to
    add a setting they have already added.
    """
    path = settings_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _warn_once(
            "settings_unreadable",
            f"{path} exists but could not be read ({error}). Beacon is "
            f"behaving as though it is not configured. Note that a Windows "
            f"path in JSON needs its separators doubled.",
        )
        return {}
    if not isinstance(raw, dict):
        _warn_once(
            "settings_not_object",
            f"{path} must contain a JSON object of setting names to values. "
            f"Beacon is behaving as though it is not configured.",
        )
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


class CatalogNotConfiguredError(RuntimeError):
    """No catalog location could be determined and none may be guessed.

    Raised rather than falling back to a local path. A silently created empty
    catalog reports itself healthy, which is exactly how a broken configuration
    came to look like a working one.
    """


def system_beacon_dir() -> Path:
    """<ARCHIVE_ROOT>/System/Beacon - system state, not content.

    Namespaced under System so future modules sit beside Beacon rather than
    colonising System directly.
    """
    return archive_root() / SYSTEM_DIRNAME / BEACON_DIRNAME


def resolve_catalog_path() -> Path | None:
    """The catalog of record, or None when it cannot be determined.

    Order:
      1. explicit configuration - BEACON_DB in the environment, then
         settings.json;
      2. otherwise <ARCHIVE_ROOT>/System/Beacon/beacon.db, when an archive root
         is known;
      3. otherwise None. The caller must ask the user. There is no local
         fallback: the catalog's home is the archive volume.
    """
    value = _setting("BEACON_DB")
    if value:
        return Path(value)
    if archive_root_is_configured():
        return system_beacon_dir() / CATALOG_FILENAME
    return None


def catalog_path() -> Path:
    """The catalog of record. Raises when it cannot be determined."""
    resolved = resolve_catalog_path()
    if resolved is None:
        raise CatalogNotConfiguredError(catalog_advice())
    return resolved


def catalog_advice() -> str:
    """Plain-language instruction for an unresolvable catalog."""
    sep = os.sep
    expected = sep.join(
        ("<ARCHIVE_ROOT>", SYSTEM_DIRNAME, BEACON_DIRNAME, CATALOG_FILENAME)
    )
    example = f'{{"{ARCHIVE_ROOT_SETTING}": "<ARCHIVE_ROOT>"}}'
    lines = [
        "Beacon cannot find a catalog because no archive location is "
        "configured.",
        "",
        f"Set {ARCHIVE_ROOT_SETTING} to the archive volume, either as an "
        "environment variable or in:",
        f"    {settings_path()}",
        "",
        "For example:",
        f"    {example}",
        "",
        "Beacon then expects the catalog at:",
        f"    {expected}",
        "",
        "To point at a catalog directly instead, set BEACON_DB to its full "
        "path.",
    ]
    return chr(10).join(lines)


def catalog_status() -> dict[str, object]:
    """Diagnostic for the desktop's missing-catalog state."""
    resolved = resolve_catalog_path()
    return {
        "configured": resolved is not None,
        "path": str(resolved) if resolved else "",
        "exists": bool(resolved and resolved.is_file()),
        "archive_root_configured": archive_root_is_configured(),
        "settings_path": str(settings_path()),
        "setting": ARCHIVE_ROOT_SETTING,
        "advice": catalog_advice(),
    }


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
    """Catalog backups live beside the catalog, under System."""
    value = _setting("BEACON_BACKUP_DIR")
    if value:
        return Path(value)
    if archive_root_is_configured():
        return system_beacon_dir() / "backups"
    raise CatalogNotConfiguredError(catalog_advice())


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


LIKE_ESCAPE = "~"


def like_prefix_pattern(path: str | Path) -> str:
    """Lowercased SQL LIKE pattern matching everything beneath a directory.

    Safe to bind as a query parameter, so it accepts an operator-supplied
    prefix as well as a configured root. Pair it with ``ESCAPE
    '<LIKE_ESCAPE>'`` in the query.

    SQLite treats a backslash as an ordinary character, so a Windows separator
    needs no escaping. The LIKE wildcards do: ``_`` is common in folder names
    and would otherwise match any single character.

    Any trailing separator is stripped before exactly one is appended, so a
    prefix written with a trailing separator and the same prefix written
    without one produce an identical pattern.
    """
    text = str(path).rstrip("\\/").casefold()
    for special in (LIKE_ESCAPE, "%", "_"):
        text = text.replace(special, LIKE_ESCAPE + special)
    return text + os.sep + "%"


def _like_prefix(path: Path) -> str:
    """``like_prefix_pattern`` for a pattern interpolated into SQL text.

    Identical to the bindable form except that single quotes are doubled,
    which is correct inside a quoted SQL literal and wrong for a bound
    parameter, where it would match a path that does not exist.
    """
    return like_prefix_pattern(path).replace("'", "''")


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
    clause = f"' ESCAPE '{LIKE_ESCAPE}'"
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
    clause = f"' ESCAPE '{LIKE_ESCAPE}'"
    approved = "\n  OR ".join(
        f"lower({column}) LIKE '{_like_prefix(root)}{clause}"
        for root in approved_destination_roots()
    )
    inbox = f"lower({column}) LIKE '{_like_prefix(inbox_root())}{clause}"
    return (
        f"WHEN {approved}\nTHEN {first_rank}\n"
        f"WHEN {inbox}\nTHEN {first_rank + 1}"
    )
