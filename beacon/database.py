from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 3


@dataclass(frozen=True)
class BackupResult:
    path: str
    size_bytes: int
    sha256: str
    integrity: str
    created_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def migrate(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL UNIQUE,
            size_bytes INTEGER NOT NULL,
            media_metadata_json TEXT,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id TEXT NOT NULL REFERENCES assets(id),
            path TEXT NOT NULL UNIQUE,
            modified_ns INTEGER NOT NULL,
            observed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_locations_asset_id
            ON locations(asset_id);
        CREATE TABLE IF NOT EXISTS system_events (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            state TEXT NOT NULL,
            message TEXT NOT NULL,
            asset_id TEXT REFERENCES assets(id),
            location_path TEXT,
            details_json TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_system_events_created_at
            ON system_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_system_events_asset_id
            ON system_events(asset_id);
        CREATE TABLE IF NOT EXISTS derivatives (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            path TEXT NOT NULL UNIQUE,
            source_sha256 TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            generator TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('complete')),
            details_json TEXT,
            created_at TEXT NOT NULL,
            verified_at TEXT NOT NULL,
            UNIQUE(asset_id, kind, source_sha256)
        );
        CREATE INDEX IF NOT EXISTS idx_derivatives_asset_kind
            ON derivatives(asset_id, kind);
        """
    )
    for version in range(1, SCHEMA_VERSION + 1):
        connection.execute(
            "INSERT OR IGNORE INTO schema_version(version) VALUES (?)",
            (version,),
        )
    connection.commit()


def record_event(
    connection: sqlite3.Connection,
    *,
    kind: str,
    state: str,
    message: str,
    asset_id: str | None = None,
    location_path: str | None = None,
    details: dict[str, object] | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO system_events(
            id, kind, state, message, asset_id, location_path, details_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            kind,
            state,
            message,
            asset_id,
            location_path,
            json.dumps(details, sort_keys=True) if details else None,
            _utc_now(),
        ),
    )
    return event_id


def database_integrity(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "state": "missing",
            "integrity": "missing",
            "foreign_key_errors": 0,
            "size_bytes": 0,
            "schema_version": 0,
        }
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(path, timeout=30)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = len(
            connection.execute("PRAGMA foreign_key_check").fetchall()
        )
        schema_version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_version"
        ).fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    except sqlite3.Error as error:
        return {
            "state": "attention",
            "integrity": str(error),
            "foreign_key_errors": None,
            "size_bytes": path.stat().st_size,
            "schema_version": None,
            "journal_mode": None,
        }
    finally:
        if connection is not None:
            connection.close()
    return {
        "state": (
            "healthy"
            if integrity == "ok" and foreign_key_errors == 0
            else "attention"
        ),
        "integrity": integrity,
        "foreign_key_errors": foreign_key_errors,
        "size_bytes": path.stat().st_size,
        "schema_version": schema_version,
        "journal_mode": journal_mode,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(db_path: Path, backup_dir: Path) -> BackupResult:
    if not db_path.exists():
        raise FileNotFoundError(f"database does not exist: {db_path}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = backup_dir / f"beacon-{timestamp}.db"
    partial = backup_dir / f".{destination.name}.partial"
    try:
        source = sqlite3.connect(db_path, timeout=30)
        target = sqlite3.connect(partial)
        try:
            source.execute("PRAGMA busy_timeout = 30000")
            source.backup(target, pages=256, sleep=0.05)
            target.commit()
        finally:
            target.close()
            source.close()
        verification = database_integrity(partial)
        if verification["state"] != "healthy":
            raise sqlite3.DatabaseError(
                f"backup verification failed: {verification['integrity']}"
            )
        os.replace(partial, destination)
        result = BackupResult(
            path=str(destination),
            size_bytes=destination.stat().st_size,
            sha256=_sha256(destination),
            integrity=str(verification["integrity"]),
            created_at=_utc_now(),
        )
        with connect(db_path) as connection:
            migrate(connection)
            record_event(
                connection,
                kind="backup",
                state="complete",
                message=f"Verified backup created: {destination.name}",
                details=asdict(result),
            )
        return result
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def list_backups(backup_dir: Path) -> list[dict[str, object]]:
    if not backup_dir.exists():
        return []
    results: list[dict[str, object]] = []
    for path in sorted(backup_dir.glob("beacon-*.db"), reverse=True):
        results.append(
            {
                "name": path.name,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    return results
