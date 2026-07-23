from __future__ import annotations

import hashlib
import os
import stat
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import CatalogResult, catalog_file
from .database import connect, migrate, record_event

Cataloger = Callable[..., CatalogResult]
ProgressCallback = Callable[[], None]


@dataclass(frozen=True)
class IntakeSnapshot:
    source_root: str
    sha256: str
    total_items: int
    total_bytes: int
    limited: bool


@dataclass(frozen=True)
class IntakeRunResult:
    job_id: str
    state: str
    completed: int
    failed: int
    pending: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_reparse_point(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return True
    attributes = getattr(value, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _same_or_descendant(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath(
            (os.path.normcase(str(path)), os.path.normcase(str(root)))
        ) == os.path.normcase(str(root))
    except ValueError:
        return False


def _resolve_source_root(
    source_root: Path,
    allowed_roots: Iterable[Path],
) -> Path:
    source = source_root.resolve(strict=True)
    if not source.is_dir():
        raise NotADirectoryError(str(source))
    if _is_reparse_point(source):
        raise ValueError(f"intake root cannot be a link or reparse point: {source}")
    allowed = tuple(Path(root).resolve(strict=True) for root in allowed_roots)
    if not allowed:
        raise ValueError("no approved intake roots are configured")
    if not any(_same_or_descendant(source, root) for root in allowed):
        approved = ", ".join(str(root) for root in allowed)
        raise ValueError(f"intake root must stay within: {approved}")
    return source


def _discover(
    source_root: Path,
    item_limit: int | None,
) -> tuple[list[tuple[Path, str, int, int]], IntakeSnapshot]:
    if item_limit is not None and item_limit <= 0:
        raise ValueError("item limit must be a positive number")
    candidates: list[tuple[Path, str, int, int]] = []
    digest = hashlib.sha256()
    total_bytes = 0

    for current, directories, filenames in os.walk(
        source_root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        safe_directories: list[str] = []
        for name in sorted(directories, key=str.casefold):
            candidate = current_path / name
            if not _is_reparse_point(candidate):
                safe_directories.append(name)
        directories[:] = safe_directories

        for name in sorted(filenames, key=str.casefold):
            candidate = current_path / name
            if _is_reparse_point(candidate) or not candidate.is_file():
                continue
            item_stat = candidate.stat()
            relative = candidate.relative_to(source_root).as_posix()
            candidates.append(
                (candidate, relative, item_stat.st_size, item_stat.st_mtime_ns)
            )
    candidates.sort(key=lambda item: item[1].casefold())
    limited = item_limit is not None and len(candidates) > item_limit
    items = candidates[:item_limit] if item_limit is not None else candidates
    for _, relative, size_bytes, modified_ns in items:
        total_bytes += size_bytes
        digest.update(relative.encode("utf-8", errors="surrogatepass"))
        digest.update(b"\0")
        digest.update(str(size_bytes).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(modified_ns).encode("ascii"))
        digest.update(b"\n")

    return items, IntakeSnapshot(
        source_root=str(source_root),
        sha256=digest.hexdigest(),
        total_items=len(items),
        total_bytes=total_bytes,
        limited=limited,
    )


def create_intake_job(
    db_path: Path,
    *,
    source_root: Path,
    allowed_roots: Iterable[Path],
    item_limit: int | None = None,
    requested_by: str = "human",
) -> str:
    source = _resolve_source_root(source_root, allowed_roots)
    items, snapshot = _discover(source, item_limit)
    job_id = str(uuid.uuid4())
    now = _utc_now()
    initial_state = "queued" if items else "complete"

    with connect(db_path) as connection:
        migrate(connection)
        connection.execute(
            """
            INSERT INTO intake_jobs(
                id, source_root, mode, state, snapshot_sha256,
                total_items, total_bytes, item_limit, cancel_requested,
                requested_by, created_at, updated_at, completed_at
            ) VALUES (?, ?, 'catalog_only', ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                job_id,
                str(source),
                initial_state,
                snapshot.sha256,
                snapshot.total_items,
                snapshot.total_bytes,
                item_limit,
                requested_by,
                now,
                now,
                now if not items else None,
            ),
        )
        connection.executemany(
            """
            INSERT INTO intake_items(
                id, job_id, source_path, relative_path, size_bytes,
                modified_ns, state, attempts
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0)
            """,
            (
                (
                    str(uuid.uuid5(uuid.UUID(job_id), relative)),
                    job_id,
                    str(path),
                    relative,
                    size_bytes,
                    modified_ns,
                )
                for path, relative, size_bytes, modified_ns in items
            ),
        )
        record_event(
            connection,
            kind="intake_job",
            state="complete" if not items else "queued",
            message=(
                f"Created catalog intake for {snapshot.total_items:,} files"
                + (" (bounded scope)" if snapshot.limited else "")
            ),
            details={
                "job_id": job_id,
                "source_root": str(source),
                "snapshot_sha256": snapshot.sha256,
                "total_items": snapshot.total_items,
                "total_bytes": snapshot.total_bytes,
                "item_limit": item_limit,
                "mode": "catalog_only",
            },
        )
    return job_id


def _counts(connection: Any, job_id: str) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT state, COUNT(*) AS count
        FROM intake_items WHERE job_id = ? GROUP BY state
        """,
        (job_id,),
    ).fetchall()
    values = {str(row["state"]): int(row["count"]) for row in rows}
    return {
        "complete": values.get("complete", 0),
        "failed": values.get("failed", 0),
        "pending": values.get("pending", 0),
        "running": values.get("running", 0),
    }


def list_intake_jobs(db_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            """
            SELECT
                jobs.*,
                SUM(CASE WHEN items.state = 'complete' THEN 1 ELSE 0 END)
                    AS completed_count,
                SUM(CASE WHEN items.state = 'failed' THEN 1 ELSE 0 END)
                    AS failed_count,
                SUM(CASE WHEN items.state = 'pending' THEN 1 ELSE 0 END)
                    AS pending_count,
                SUM(CASE WHEN items.state = 'running' THEN 1 ELSE 0 END)
                    AS running_count,
                COALESCE(SUM(
                    CASE WHEN items.state = 'complete'
                         THEN items.size_bytes ELSE 0 END
                ), 0) AS completed_bytes
            FROM intake_jobs jobs
            LEFT JOIN intake_items items ON items.job_id = jobs.id
            GROUP BY jobs.id
            ORDER BY jobs.updated_at DESC
            LIMIT ?
            """,
            (max(1, min(limit, 200)),),
        ).fetchall()
    return [dict(row) for row in rows]


def intake_job_detail(db_path: Path, job_id: str) -> dict[str, Any] | None:
    jobs = list_intake_jobs(db_path, limit=200)
    job = next((item for item in jobs if item["id"] == job_id), None)
    if job is None:
        return None
    with connect(db_path) as connection:
        migrate(connection)
        failures = connection.execute(
            """
            SELECT relative_path, error, attempts
            FROM intake_items
            WHERE job_id = ? AND state = 'failed'
            ORDER BY relative_path LIMIT 10
            """,
            (job_id,),
        ).fetchall()
    job["failures"] = [dict(row) for row in failures]
    return job


def recover_intake_jobs(db_path: Path) -> int:
    now = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            "SELECT id FROM intake_jobs WHERE state = 'running'"
        ).fetchall()
        job_ids = [str(row["id"]) for row in rows]
        if not job_ids:
            return 0
        placeholders = ",".join("?" for _ in job_ids)
        connection.execute(
            f"""
            UPDATE intake_items
            SET state = 'pending', started_at = NULL
            WHERE state = 'running' AND job_id IN ({placeholders})
            """,
            job_ids,
        )
        connection.execute(
            f"""
            UPDATE intake_jobs
            SET state = 'paused', current_path = NULL,
                cancel_requested = 0, updated_at = ?,
                error = 'Interrupted before the prior app session closed'
            WHERE id IN ({placeholders})
            """,
            (now, *job_ids),
        )
        for job_id in job_ids:
            record_event(
                connection,
                kind="intake_job",
                state="paused",
                message="Recovered an interrupted intake; it is ready to resume",
                details={"job_id": job_id},
            )
    return len(job_ids)


def request_intake_cancel(db_path: Path, job_id: str) -> None:
    now = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            "SELECT state FROM intake_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise LookupError("intake job was not found")
        state = str(row["state"])
        if state in {"complete", "failed"}:
            raise ValueError(f"a {state} intake cannot be cancelled")
        if state == "running":
            connection.execute(
                """
                UPDATE intake_jobs SET cancel_requested = 1, updated_at = ?
                WHERE id = ?
                """,
                (now, job_id),
            )
        else:
            connection.execute(
                """
                UPDATE intake_jobs
                SET state = 'cancelled', cancel_requested = 1,
                    current_path = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, job_id),
            )


def pause_intake_job(db_path: Path, job_id: str) -> None:
    now = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            "SELECT state FROM intake_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise LookupError("intake job was not found")
        if row["state"] != "running":
            return
        connection.execute(
            """
            UPDATE intake_jobs
            SET state = 'paused', updated_at = ?,
                error = 'Paused when the desktop app closed'
            WHERE id = ?
            """,
            (now, job_id),
        )


def resume_intake_job(db_path: Path, job_id: str) -> None:
    now = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            "SELECT state FROM intake_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise LookupError("intake job was not found")
        state = str(row["state"])
        if state not in {"queued", "paused", "cancelled", "partial"}:
            raise ValueError(f"a {state} intake cannot be resumed")
        connection.execute(
            """
            UPDATE intake_jobs
            SET state = 'queued', cancel_requested = 0, current_path = NULL,
                updated_at = ?, completed_at = NULL, error = NULL
            WHERE id = ?
            """,
            (now, job_id),
        )


def retry_intake_failures(db_path: Path, job_id: str) -> int:
    now = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            "SELECT state FROM intake_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise LookupError("intake job was not found")
        if row["state"] == "running":
            raise ValueError("cancel the running intake before retrying failures")
        cursor = connection.execute(
            """
            UPDATE intake_items
            SET state = 'pending', error = NULL,
                started_at = NULL, completed_at = NULL
            WHERE job_id = ? AND state = 'failed'
            """,
            (job_id,),
        )
        if cursor.rowcount == 0:
            raise ValueError("this intake has no failed files to retry")
        connection.execute(
            """
            UPDATE intake_jobs
            SET state = 'queued', cancel_requested = 0, current_path = NULL,
                updated_at = ?, completed_at = NULL, error = NULL
            WHERE id = ?
            """,
            (now, job_id),
        )
        return int(cursor.rowcount)


def _finish_state(connection: Any, job_id: str) -> IntakeRunResult:
    counts = _counts(connection, job_id)
    if counts["pending"] or counts["running"]:
        state = "paused"
        completed_at = None
    elif counts["failed"]:
        state = "partial" if counts["complete"] else "failed"
        completed_at = _utc_now()
    else:
        state = "complete"
        completed_at = _utc_now()
    connection.execute(
        """
        UPDATE intake_jobs
        SET state = ?, current_path = NULL, cancel_requested = 0,
            updated_at = ?, completed_at = ?, error = NULL
        WHERE id = ?
        """,
        (state, _utc_now(), completed_at, job_id),
    )
    return IntakeRunResult(
        job_id=job_id,
        state=state,
        completed=counts["complete"],
        failed=counts["failed"],
        pending=counts["pending"],
    )


def run_intake_job(
    db_path: Path,
    job_id: str,
    *,
    cataloger: Cataloger = catalog_file,
    include_media_probe: bool = True,
    include_thumbnail_generation: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> IntakeRunResult:
    recover_intake_jobs(db_path)
    resume_intake_job(db_path, job_id)
    started_event_recorded = False

    while True:
        with connect(db_path) as connection:
            migrate(connection)
            job = connection.execute(
                """
                SELECT state, cancel_requested, started_at
                FROM intake_jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            if job is None:
                raise LookupError("intake job was not found")
            if job["state"] == "paused":
                counts = _counts(connection, job_id)
                connection.execute(
                    """
                    UPDATE intake_jobs
                    SET current_path = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (_utc_now(), job_id),
                )
                result = IntakeRunResult(
                    job_id, "paused",
                    counts["complete"], counts["failed"], counts["pending"],
                )
                if progress_callback:
                    progress_callback()
                return result
            if int(job["cancel_requested"]):
                now = _utc_now()
                counts = _counts(connection, job_id)
                connection.execute(
                    """
                    UPDATE intake_jobs
                    SET state = 'cancelled', current_path = NULL,
                        updated_at = ?, error = NULL
                    WHERE id = ?
                    """,
                    (now, job_id),
                )
                record_event(
                    connection,
                    kind="intake_job",
                    state="cancelled",
                    message="Catalog intake cancelled between files",
                    details={"job_id": job_id, **counts},
                )
                result = IntakeRunResult(
                    job_id, "cancelled",
                    counts["complete"], counts["failed"], counts["pending"],
                )
                if progress_callback:
                    progress_callback()
                return result

            item = connection.execute(
                """
                SELECT id, source_path, relative_path, size_bytes, modified_ns
                FROM intake_items
                WHERE job_id = ? AND state = 'pending'
                ORDER BY relative_path LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if item is None:
                result = _finish_state(connection, job_id)
                record_event(
                    connection,
                    kind="intake_job",
                    state=result.state,
                    message=(
                        f"Catalog intake finished: {result.completed:,} complete, "
                        f"{result.failed:,} failed"
                    ),
                    details={
                        "job_id": job_id,
                        "completed": result.completed,
                        "failed": result.failed,
                    },
                )
                if progress_callback:
                    progress_callback()
                return result

            now = _utc_now()
            connection.execute(
                """
                UPDATE intake_items
                SET state = 'running', attempts = attempts + 1,
                    started_at = ?, error = NULL
                WHERE id = ?
                """,
                (now, item["id"]),
            )
            connection.execute(
                """
                UPDATE intake_jobs
                SET state = 'running', current_path = ?, updated_at = ?,
                    started_at = COALESCE(started_at, ?), error = NULL
                WHERE id = ?
                """,
                (item["source_path"], now, now, job_id),
            )
            if not started_event_recorded and job["started_at"] is None:
                record_event(
                    connection,
                    kind="intake_job",
                    state="running",
                    message="Catalog intake started",
                    location_path=item["source_path"],
                    details={"job_id": job_id},
                )
                started_event_recorded = True

        source = Path(str(item["source_path"]))
        try:
            current = source.stat()
            if _is_reparse_point(source) or not source.is_file():
                raise ValueError("source is no longer a regular non-link file")
            if (current.st_size, current.st_mtime_ns) != (
                int(item["size_bytes"]),
                int(item["modified_ns"]),
            ):
                raise RuntimeError("source changed after the intake snapshot")
            cataloged = cataloger(
                source,
                db_path,
                stability_seconds=0,
                include_media_probe=include_media_probe,
                include_thumbnail_generation=include_thumbnail_generation,
            )
            with connect(db_path) as connection:
                migrate(connection)
                now = _utc_now()
                connection.execute(
                    """
                    UPDATE intake_items
                    SET state = 'complete', asset_id = ?, error = NULL,
                        completed_at = ?
                    WHERE id = ?
                    """,
                    (cataloged.asset_id, now, item["id"]),
                )
                connection.execute(
                    "UPDATE intake_jobs SET updated_at = ? WHERE id = ?",
                    (now, job_id),
                )
        except Exception as error:
            with connect(db_path) as connection:
                migrate(connection)
                now = _utc_now()
                connection.execute(
                    """
                    UPDATE intake_items
                    SET state = 'failed', error = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (str(error)[:2000], now, item["id"]),
                )
                connection.execute(
                    """
                    UPDATE intake_jobs SET updated_at = ?, error = ?
                    WHERE id = ?
                    """,
                    (now, str(error)[:2000], job_id),
                )
        if progress_callback:
            progress_callback()
