from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from beacon.config import inbox_root
from beacon.database import connect, migrate, record_event
from beacon.local_analysis import _record_analysis_placement_failure
from beacon.managed_moves import (
    analysis_placement_for,
    commit_analyzed_file,
    destination_directory_blocked,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_log(path: Path | None, event: str, **details: Any) -> None:
    payload = {"at": _utc_now(), "event": event, **details}
    line = json.dumps(payload, sort_keys=True)
    print(line, flush=True)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")


def _latest_completed_run(db_path: Path) -> tuple[str, str]:
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id,analysis_run_id FROM local_analysis_jobs
            WHERE state IN ('complete','partial') AND analysis_run_id IS NOT NULL
            ORDER BY updated_at DESC LIMIT 1
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("No completed local analysis run is available.")
    return str(row["id"]), str(row["analysis_run_id"])


def _pending_locations(db_path: Path, run_id: str) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT locations.asset_id,locations.path AS source_path,
                   assets.size_bytes,results.confidence
            FROM analysis_results results
            JOIN assets ON assets.id=results.asset_id
            JOIN locations ON locations.asset_id=results.asset_id
            WHERE results.run_id=? AND locations.path LIKE ?
            ORDER BY locations.path COLLATE NOCASE
            """,
            (run_id, f"{inbox_root()}{os.sep}%"),
        ).fetchall()
    return [dict(row) for row in rows]


def _resolve_matching_blocker(
    db_path: Path,
    *,
    run_id: str,
    asset_id: str,
    source_path: Path,
) -> None:
    fingerprint = hashlib.sha256(
        str(source_path).encode("utf-8")
    ).hexdigest()[:16]
    seed_key = f"analysis-placement-error:{run_id}:{asset_id}:{fingerprint}"
    timestamp = _utc_now()
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE beacon_threads
            SET state='resolved',updated_at=?,resolved_at=?
            WHERE seed_key=? AND state NOT IN ('resolved','closed')
            """,
            (timestamp, timestamp, seed_key),
        )


def retry_deferred_placements(
    db_path: Path,
    *,
    limit: int | None,
    log_path: Path | None,
) -> dict[str, Any]:
    job_id, run_id = _latest_completed_run(db_path)
    candidates = _pending_locations(db_path, run_id)
    if limit is not None:
        candidates = candidates[:limit]
    batch_id = str(uuid.uuid4())
    summary = {
        "batch_id": batch_id,
        "job_id": job_id,
        "analysis_run_id": run_id,
        "selected": len(candidates),
        "moved": 0,
        "skipped": 0,
        "failed": 0,
        "deferred": 0,
        "bytes_moved": 0,
    }
    blocked_directories: set[str] = set()
    with connect(db_path) as connection:
        migrate(connection)
        record_event(
            connection,
            kind="managed_move_retry_batch",
            state="running",
            message="Beacon started deferred analyzed-file placements.",
            details=summary,
        )
    _write_log(log_path, "start", **summary)

    for index, candidate in enumerate(candidates, start=1):
        asset_id = str(candidate["asset_id"])
        source_path = Path(str(candidate["source_path"]))
        placement = analysis_placement_for(source_path)
        if placement.destination_directory is None:
            summary["skipped"] += 1
            continue
        destination_key = str(placement.destination_directory).casefold()
        if destination_key in blocked_directories:
            summary["deferred"] += 1
            continue
        try:
            moved, _reason = commit_analyzed_file(
                db_path,
                asset_id=asset_id,
                source_path=source_path,
                confidence=float(candidate["confidence"]),
                analysis_run_id=run_id,
            )
        except Exception as error:
            summary["failed"] += 1
            if destination_directory_blocked(error):
                blocked_directories.add(destination_key)
            _record_analysis_placement_failure(
                db_path,
                run_id=run_id,
                asset_id=asset_id,
                source_path=source_path,
                error=error,
            )
            _write_log(
                log_path,
                "placement_failed",
                index=index,
                asset_id=asset_id,
                source_path=str(source_path),
                error=str(error)[:1900],
            )
            continue
        if moved is None:
            summary["skipped"] += 1
            continue
        summary["moved"] += 1
        summary["bytes_moved"] += int(candidate["size_bytes"] or 0)
        _resolve_matching_blocker(
            db_path,
            run_id=run_id,
            asset_id=asset_id,
            source_path=source_path,
        )
        if summary["moved"] % 25 == 0:
            _write_log(log_path, "progress", index=index, **summary)

    state = "complete" if summary["failed"] == 0 else "partial"
    with connect(db_path) as connection:
        record_event(
            connection,
            kind="managed_move_retry_batch",
            state=state,
            message=(
                "Beacon finished deferred analyzed-file placements."
                if state == "complete"
                else "Beacon deferred analyzed-file placements with failures."
            ),
            details=summary,
        )
    _write_log(log_path, "finish", state=state, **summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retry checksum-verified placements for analyzed Inbox files."
    )
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    try:
        retry_deferred_placements(
            args.db,
            limit=args.limit,
            log_path=args.log,
        )
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        _write_log(args.log, "fatal", error=str(error)[:1900])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
