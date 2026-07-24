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

SCHEMA_VERSION = 11


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
    try:
        existing_version = int(
            connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version"
            ).fetchone()[0]
        )
    except sqlite3.OperationalError:
        existing_version = 0
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
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id TEXT PRIMARY KEY,
            manifest_sha256 TEXT NOT NULL UNIQUE,
            analyzer TEXT NOT NULL,
            analyzer_version TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            execution_location TEXT NOT NULL,
            external_inference INTEGER NOT NULL
                CHECK(external_inference IN (0, 1)),
            authorization TEXT,
            state TEXT NOT NULL
                CHECK(state IN ('running', 'complete', 'partial', 'failed')),
            scope_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_analysis_runs_created_at
            ON analysis_runs(created_at DESC);
        CREATE TABLE IF NOT EXISTS analysis_results (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
            asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            source_sha256 TEXT NOT NULL,
            analysis_kind TEXT NOT NULL,
            fingerprint TEXT NOT NULL UNIQUE,
            payload_json TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
            review_state TEXT NOT NULL
                CHECK(review_state IN (
                    'candidate', 'approved', 'rejected', 'superseded'
                )),
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            UNIQUE(run_id, asset_id, analysis_kind)
        );
        CREATE INDEX IF NOT EXISTS idx_analysis_results_asset_created
            ON analysis_results(asset_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_analysis_results_review_state
            ON analysis_results(review_state);
        CREATE TABLE IF NOT EXISTS beacon_threads (
            id TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN (
                'blocker', 'question', 'clarification', 'approval', 'request'
            )),
            priority TEXT NOT NULL CHECK(priority IN (
                'normal', 'important', 'urgent'
            )),
            state TEXT NOT NULL CHECK(state IN (
                'awaiting_human', 'queued_for_beacon', 'resolved', 'closed'
            )),
            origin TEXT NOT NULL CHECK(origin IN (
                'beacon', 'human', 'system'
            )),
            requires_approval INTEGER NOT NULL DEFAULT 0
                CHECK(requires_approval IN (0, 1)),
            asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
            seed_key TEXT UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_beacon_threads_state_updated
            ON beacon_threads(state, updated_at DESC);
        CREATE TABLE IF NOT EXISTS beacon_messages (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL
                REFERENCES beacon_threads(id) ON DELETE CASCADE,
            author TEXT NOT NULL CHECK(author IN (
                'beacon', 'human', 'system'
            )),
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_beacon_messages_thread_created
            ON beacon_messages(thread_id, created_at);
        CREATE TABLE IF NOT EXISTS beacon_policies (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_reference TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS asset_metadata (
            asset_id TEXT PRIMARY KEY
                REFERENCES assets(id) ON DELETE CASCADE,
            metadata_json TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK(revision >= 1),
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS asset_metadata_revisions (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL
                REFERENCES assets(id) ON DELETE CASCADE,
            revision INTEGER NOT NULL CHECK(revision >= 1),
            metadata_json TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(asset_id, revision)
        );
        CREATE INDEX IF NOT EXISTS idx_asset_metadata_revisions_asset
            ON asset_metadata_revisions(asset_id, revision DESC);
        CREATE TABLE IF NOT EXISTS asset_metadata_field_authority (
            asset_id TEXT NOT NULL
                REFERENCES assets(id) ON DELETE CASCADE,
            field TEXT NOT NULL,
            authority TEXT NOT NULL CHECK(authority IN ('ai', 'human')),
            source_reference TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(asset_id, field)
        );
        CREATE TABLE IF NOT EXISTS managed_moves (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL REFERENCES assets(id),
            source_path TEXT NOT NULL,
            destination_path TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN (
                'planned', 'running', 'complete', 'failed', 'rolled_back'
            )),
            requested_by TEXT NOT NULL,
            authorization TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_managed_moves_asset_created
            ON managed_moves(asset_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_managed_moves_state
            ON managed_moves(state);
        CREATE TABLE IF NOT EXISTS intake_jobs (
            id TEXT PRIMARY KEY,
            source_root TEXT NOT NULL,
            mode TEXT NOT NULL CHECK(mode IN ('catalog_only')),
            state TEXT NOT NULL CHECK(state IN (
                'queued', 'running', 'paused', 'complete',
                'partial', 'failed', 'cancelled'
            )),
            snapshot_sha256 TEXT NOT NULL,
            total_items INTEGER NOT NULL CHECK(total_items >= 0),
            total_bytes INTEGER NOT NULL CHECK(total_bytes >= 0),
            item_limit INTEGER CHECK(item_limit IS NULL OR item_limit > 0),
            current_path TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0
                CHECK(cancel_requested IN (0, 1)),
            requested_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_intake_jobs_state_updated
            ON intake_jobs(state, updated_at DESC);
        CREATE TABLE IF NOT EXISTS intake_items (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL
                REFERENCES intake_jobs(id) ON DELETE CASCADE,
            source_path TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
            modified_ns INTEGER NOT NULL,
            state TEXT NOT NULL CHECK(state IN (
                'pending', 'running', 'complete', 'failed'
            )),
            attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
            asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
            error TEXT,
            started_at TEXT,
            completed_at TEXT,
            UNIQUE(job_id, source_path)
        );
        CREATE INDEX IF NOT EXISTS idx_intake_items_job_state_path
            ON intake_items(job_id, state, relative_path);
        CREATE TABLE IF NOT EXISTS local_analysis_jobs (
            id TEXT PRIMARY KEY,
            state TEXT NOT NULL CHECK(state IN (
                'queued', 'running', 'paused', 'complete',
                'partial', 'failed', 'cancelled'
            )),
            model TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            scope_sha256 TEXT NOT NULL,
            total_items INTEGER NOT NULL CHECK(total_items >= 0),
            cancel_requested INTEGER NOT NULL DEFAULT 0
                CHECK(cancel_requested IN (0, 1)),
            current_asset_id TEXT REFERENCES assets(id) ON DELETE SET NULL,
            requested_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            analysis_run_id TEXT REFERENCES analysis_runs(id) ON DELETE SET NULL,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_local_analysis_jobs_state_updated
            ON local_analysis_jobs(state, updated_at DESC);
        CREATE TABLE IF NOT EXISTS local_analysis_items (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL
                REFERENCES local_analysis_jobs(id) ON DELETE CASCADE,
            asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            source_sha256 TEXT NOT NULL,
            source_path TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN (
                'pending', 'running', 'complete', 'failed'
            )),
            attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
            result_json TEXT,
            error TEXT,
            started_at TEXT,
            completed_at TEXT,
            UNIQUE(job_id, asset_id)
        );
        CREATE INDEX IF NOT EXISTS idx_local_analysis_items_job_state
            ON local_analysis_items(job_id, state, asset_id);
        CREATE TABLE IF NOT EXISTS asset_transcripts (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            source_sha256 TEXT NOT NULL,
            text TEXT NOT NULL,
            text_sha256 TEXT NOT NULL,
            language TEXT,
            language_probability REAL,
            generator TEXT NOT NULL,
            created_at TEXT NOT NULL,
            verified_at TEXT NOT NULL,
            UNIQUE(asset_id, source_sha256, generator)
        );
        CREATE INDEX IF NOT EXISTS idx_asset_transcripts_asset
            ON asset_transcripts(asset_id, verified_at DESC);
        """
    )
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(local_analysis_jobs)")
    }
    if "worker_pid" not in columns:
        connection.execute(
            "ALTER TABLE local_analysis_jobs ADD COLUMN worker_pid INTEGER"
        )
    if existing_version < 9:
        now = _utc_now()
        for row in connection.execute(
            """
            SELECT asset_id,metadata_json,updated_by FROM asset_metadata
            WHERE lower(updated_by) != 'beacon local analyzer'
            """
        ):
            try:
                stored = json.loads(row["metadata_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            connection.executemany(
                """
                INSERT OR IGNORE INTO asset_metadata_field_authority(
                    asset_id,field,authority,source_reference,updated_at
                ) VALUES (?, ?, 'human', 'schema-9-backfill', ?)
                """,
                (
                    (row["asset_id"], field, now)
                    for field, value in stored.items()
                    if value not in (None, "", [])
                ),
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
