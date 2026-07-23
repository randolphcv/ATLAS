from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any

from .database import connect, migrate, record_event
from .identity import asset_uuid
from .media import probe
from .stability import wait_until_stable

LOGGER = logging.getLogger("beacon.catalog")


@dataclass(frozen=True)
class CatalogResult:
    asset_id: str
    sha256: str
    path: str
    duplicate_content: bool
    repeated_location: bool


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def catalog_file(
    source: Path,
    db_path: Path,
    stability_seconds: float = 2.0,
    include_media_probe: bool = True,
) -> CatalogResult:
    source = source.resolve(strict=True)
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"not a regular non-symlink file: {source}")

    stable_stat = wait_until_stable(source, interval_seconds=stability_seconds)
    checksum = sha256_file(source)
    after_hash = source.stat()
    if (after_hash.st_size, after_hash.st_mtime_ns) != (
        stable_stat.st_size,
        stable_stat.st_mtime_ns,
    ):
        raise RuntimeError(f"file changed while hashing: {source}")

    identifier = asset_uuid(checksum)
    media: dict[str, Any] | None = probe(source) if include_media_probe else None
    media_json = json.dumps(media, sort_keys=True) if media is not None else None
    now = _utc_now()

    with connect(db_path) as connection:
        migrate(connection)
        duplicate = connection.execute(
            "SELECT 1 FROM assets WHERE sha256 = ?", (checksum,)
        ).fetchone() is not None
        repeated = connection.execute(
            "SELECT 1 FROM locations WHERE path = ?", (str(source),)
        ).fetchone() is not None
        connection.execute(
            """
            INSERT INTO assets(
                id, sha256, size_bytes, media_metadata_json, created_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(sha256) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                media_metadata_json = COALESCE(
                    excluded.media_metadata_json, assets.media_metadata_json
                )
            """,
            (identifier, checksum, after_hash.st_size, media_json, now, now),
        )
        connection.execute(
            """
            INSERT INTO locations(asset_id, path, modified_ns, observed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                asset_id = excluded.asset_id,
                modified_ns = excluded.modified_ns,
                observed_at = excluded.observed_at
            """,
            (identifier, str(source), after_hash.st_mtime_ns, now),
        )
        record_event(
            connection,
            kind="catalog",
            state="complete",
            message=f"Cataloged {source.name}",
            asset_id=identifier,
            location_path=str(source),
            details={
                "duplicate_content": duplicate,
                "repeated_location": repeated,
                "sha256": checksum,
                "size_bytes": after_hash.st_size,
            },
        )
    LOGGER.info(
        "cataloged asset_id=%s path=%s duplicate=%s repeated=%s",
        identifier,
        source,
        duplicate,
        repeated,
    )
    return CatalogResult(identifier, checksum, str(source), duplicate, repeated)


def scan_directory(
    inbox: Path,
    db_path: Path,
    stability_seconds: float = 2.0,
) -> tuple[list[CatalogResult], list[tuple[str, str]]]:
    try:
        inbox = inbox.resolve(strict=True)
    except OSError as error:
        message = f"inbox unavailable: {error}"
        LOGGER.error("scan failed path=%s error=%s", inbox, message)
        return [], [(str(inbox), message)]
    if not inbox.is_dir():
        message = "inbox is not a directory"
        LOGGER.error("scan failed path=%s error=%s", inbox, message)
        return [], [(str(inbox), message)]
    results: list[CatalogResult] = []
    errors: list[tuple[str, str]] = []
    for candidate in sorted(inbox.iterdir()):
        if not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            results.append(catalog_file(candidate, db_path, stability_seconds))
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
            LOGGER.exception("catalog failed path=%s", candidate)
            errors.append((str(candidate), str(error)))
    return results, errors


def watch_directory(
    inbox: Path,
    db_path: Path,
    stability_seconds: float = 2.0,
    poll_seconds: float = 1.0,
    max_cycles: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[int, int]:
    """Watch a directory in the foreground and catalog new or changed files."""
    seen: dict[str, tuple[int, int]] = {}
    cataloged = 0
    error_count = 0
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        try:
            resolved = inbox.resolve(strict=True)
            if not resolved.is_dir():
                raise NotADirectoryError(str(resolved))
            candidates = sorted(resolved.iterdir())
        except OSError as error:
            error_count += 1
            LOGGER.error("watch inbox unavailable path=%s error=%s", inbox, error)
            candidates = []

        for candidate in candidates:
            if not candidate.is_file() or candidate.is_symlink():
                continue
            try:
                stat = candidate.stat()
                current = (stat.st_size, stat.st_mtime_ns)
                if seen.get(str(candidate)) == current:
                    continue
                catalog_file(candidate, db_path, stability_seconds)
                stable = candidate.stat()
                seen[str(candidate)] = (stable.st_size, stable.st_mtime_ns)
                cataloged += 1
            except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
                error_count += 1
                LOGGER.exception("watch catalog failed path=%s", candidate)

        cycles += 1
        if max_cycles is None or cycles < max_cycles:
            sleep(poll_seconds)
    return cataloged, error_count
