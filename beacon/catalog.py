from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import connect, migrate
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
    inbox = inbox.resolve(strict=True)
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

