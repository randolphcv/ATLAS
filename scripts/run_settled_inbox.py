from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from beacon.database import create_backup, database_integrity
from beacon.intake import create_intake_job, run_intake_job
from beacon.local_analysis import create_local_analysis_job, run_local_analysis_job


ACTIVE_STATES = ("queued", "running", "paused")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(log_path: Path, event: str, **details: object) -> None:
    line = json.dumps({"at": now(), "event": event, **details}, sort_keys=True)
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def inbox_snapshot(inbox: Path) -> tuple[int, int, int]:
    count = 0
    total_bytes = 0
    zero_bytes = 0
    for path in inbox.rglob("*"):
        if not path.is_file():
            continue
        size = path.stat().st_size
        count += 1
        total_bytes += size
        zero_bytes += size == 0
    return count, total_bytes, zero_bytes


def guard(db_path: Path, inbox: Path) -> None:
    if not inbox.is_dir():
        raise RuntimeError(f"Inbox is unavailable: {inbox}")
    health = database_integrity(db_path)
    if health["integrity"] != "ok" or health["foreign_key_errors"]:
        raise RuntimeError(f"database validation failed: {health}")


def ensure_idle(db_path: Path) -> None:
    placeholders = ",".join("?" for _ in ACTIVE_STATES)
    with sqlite3.connect(db_path) as connection:
        for table in ("intake_jobs", "local_analysis_jobs"):
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE state IN ({placeholders})",
                ACTIVE_STATES,
            ).fetchone()[0]
            if count:
                raise RuntimeError(f"{table} already has {count} active job(s)")


def wait_until_settled(
    inbox: Path,
    log_path: Path,
    *,
    interval_seconds: int,
    required_samples: int,
) -> tuple[int, int, int]:
    previous: tuple[int, int, int] | None = None
    matching = 0
    while True:
        current = inbox_snapshot(inbox)
        if current == previous and current[2] == 0:
            matching += 1
        else:
            matching = 0
        emit(
            log_path,
            "settle_check",
            files=current[0],
            bytes=current[1],
            zero_byte_files=current[2],
            matching_samples=matching,
            required_samples=required_samples,
        )
        if current[0] and matching >= required_samples:
            return current
        if not current[0]:
            return current
        previous = current
        time.sleep(interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wait for a stable Inbox, then durably intake and analyze it."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--inbox", type=Path, required=True)
    parser.add_argument("--model", default="qwen2.5vl:7b")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--settled-samples", type=int, default=5)
    args = parser.parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)

    try:
        guard(args.db, args.inbox)
        ensure_idle(args.db)
        settled = wait_until_settled(
            args.inbox,
            args.log,
            interval_seconds=args.interval_seconds,
            required_samples=args.settled_samples,
        )
        if settled[0] == 0:
            emit(args.log, "complete", message="Inbox is already empty")
            return 0

        guard(args.db, args.inbox)
        backup = create_backup(args.db, args.backup_dir)
        emit(
            args.log,
            "backup_complete",
            path=str(backup.path),
            sha256=backup.sha256,
            size_bytes=backup.size_bytes,
        )
        job_id = create_intake_job(
            args.db,
            source_root=args.inbox,
            allowed_roots=(args.inbox,),
            requested_by="settled Inbox handoff",
        )
        emit(args.log, "intake_created", job_id=job_id, files=settled[0], bytes=settled[1])
        intake = run_intake_job(args.db, job_id)
        emit(args.log, "intake_finished", **intake.__dict__)
        if intake.state != "complete" or intake.failed:
            raise RuntimeError(f"intake stopped in state {intake.state}")

        analysis_id = create_local_analysis_job(
            args.db,
            model=args.model,
            requested_by="settled Inbox handoff",
        )
        emit(args.log, "analysis_created", job_id=analysis_id, model=args.model)
        analysis = run_local_analysis_job(
            args.db,
            analysis_id,
            stop_on_item_error=True,
        )
        emit(args.log, "analysis_finished", **analysis.__dict__)
        if analysis.state != "complete" or analysis.failed:
            raise RuntimeError(f"analysis stopped in state {analysis.state}")

        remaining = inbox_snapshot(args.inbox)
        if remaining[0]:
            raise RuntimeError(
                f"analysis completed but Inbox still contains {remaining[0]} files"
            )
        guard(args.db, args.inbox)
        emit(args.log, "complete", files=0, bytes=0)
        return 0
    except Exception as error:
        emit(args.log, "stopped", error=str(error), traceback=traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
