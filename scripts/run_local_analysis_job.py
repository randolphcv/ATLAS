from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from beacon.database import database_integrity
from beacon.local_analysis import run_local_analysis_job


def emit(path: Path, event: str, **details: object) -> None:
    line = json.dumps(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **details,
        },
        sort_keys=True,
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    emit(args.log, "start", job_id=args.job)
    try:
        result = run_local_analysis_job(
            args.db,
            args.job,
            stop_on_item_error=True,
        )
        health = database_integrity(args.db)
        emit(
            args.log,
            "finish",
            **asdict(result),
            database_health=health,
        )
        return 0 if result.state == "complete" and health["state"] == "healthy" else 1
    except Exception as error:
        emit(args.log, "stopped", error=str(error))
        return 1


if __name__ == "__main__":
    sys.exit(main())
