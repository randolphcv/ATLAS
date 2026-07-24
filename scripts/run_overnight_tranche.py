from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from beacon.database import database_integrity
from beacon.intake import intake_job_detail, run_intake_job
from beacon.local_analysis import create_local_analysis_job, run_local_analysis_job


MIN_FREE_BYTES = 10 * 1024**3


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(log_path: Path, event: str, **details: object) -> None:
    line = json.dumps({"at": now(), "event": event, **details}, sort_keys=True)
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def guard(db_path: Path, inbox: Path) -> None:
    if not inbox.is_dir():
        raise RuntimeError(f"Inbox drive is unavailable: {inbox}")
    if shutil.disk_usage(db_path.parent).free < MIN_FREE_BYTES:
        raise RuntimeError("C: free space fell below the 10 GiB safety floor")
    health = database_integrity(db_path)
    if health["integrity"] != "ok":
        raise RuntimeError(f"database integrity failed: {health['integrity']}")
    if health["foreign_key_errors"]:
        raise RuntimeError("database foreign-key validation failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--inbox", type=Path, required=True)
    parser.add_argument("--intake-job", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)

    try:
        guard(args.db, args.inbox)
        detail = intake_job_detail(args.db, args.intake_job)
        if detail is None:
            raise LookupError("intake job was not found")
        if int(detail["total_items"]) != 250 or int(detail["item_limit"]) != 250:
            raise RuntimeError("overnight intake must be frozen at exactly 250 files")
        emit(
            args.log,
            "intake_start",
            job_id=args.intake_job,
            snapshot_sha256=detail["snapshot_sha256"],
            total_items=detail["total_items"],
            total_bytes=detail["total_bytes"],
        )

        intake = run_intake_job(
            args.db,
            args.intake_job,
            progress_callback=lambda: guard(args.db, args.inbox),
        )
        emit(args.log, "intake_finish", **intake.__dict__)
        if intake.state != "complete" or intake.failed:
            raise RuntimeError(f"intake stopped in state {intake.state}")

        guard(args.db, args.inbox)
        analysis_job = create_local_analysis_job(
            args.db,
            model=args.model,
            requested_by="human-approved overnight tranche",
        )
        with sqlite3.connect(args.db) as connection:
            total = connection.execute(
                "SELECT total_items FROM local_analysis_jobs WHERE id=?",
                (analysis_job,),
            ).fetchone()[0]
        emit(args.log, "analysis_created", job_id=analysis_job, total_items=total)
        analysis = run_local_analysis_job(
            args.db,
            analysis_job,
            progress_callback=lambda: guard(args.db, args.inbox),
            stop_on_item_error=True,
        )
        emit(args.log, "analysis_finish", **analysis.__dict__)
        guard(args.db, args.inbox)
        if analysis.state != "complete" or analysis.failed:
            raise RuntimeError(f"analysis stopped in state {analysis.state}")
        return 0
    except Exception as error:
        emit(
            args.log,
            "stopped",
            error=str(error),
            traceback=traceback.format_exc(),
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
