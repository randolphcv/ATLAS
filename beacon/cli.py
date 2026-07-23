from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from .catalog import catalog_file, scan_directory, watch_directory
from .database import connect, migrate
from .identity import atlas_uri


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="beacon")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--log-file", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("--db", type=Path, required=True)

    add = commands.add_parser("add")
    add.add_argument("path", type=Path)
    add.add_argument("--db", type=Path, required=True)
    add.add_argument("--stability-seconds", type=float, default=2.0)

    scan = commands.add_parser("scan")
    scan.add_argument("inbox", type=Path)
    scan.add_argument("--db", type=Path, required=True)
    scan.add_argument("--stability-seconds", type=float, default=2.0)

    watch = commands.add_parser("watch")
    watch.add_argument("inbox", type=Path)
    watch.add_argument("--db", type=Path, required=True)
    watch.add_argument("--stability-seconds", type=float, default=2.0)
    watch.add_argument("--poll-seconds", type=float, default=1.0)
    watch.add_argument(
        "--once",
        action="store_true",
        help="process one polling cycle and exit",
    )

    listing = commands.add_parser("list")
    listing.add_argument("--db", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("asset_id")
    inspect.add_argument("--db", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.log_file:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )
    if args.command == "init":
        with connect(args.db) as connection:
            migrate(connection)
        print(f"initialized {args.db.resolve()}")
        return 0
    if args.command == "add":
        result = catalog_file(args.path, args.db, args.stability_seconds)
        print(json.dumps(result.__dict__, indent=2))
        return 0
    if args.command == "scan":
        results, errors = scan_directory(
            args.inbox, args.db, args.stability_seconds
        )
        print(json.dumps({"cataloged": len(results), "errors": errors}, indent=2))
        return 1 if errors else 0
    if args.command == "watch":
        try:
            cataloged, errors = watch_directory(
                args.inbox,
                args.db,
                args.stability_seconds,
                args.poll_seconds,
                max_cycles=1 if args.once else None,
            )
        except KeyboardInterrupt:
            print("watch stopped")
            return 130
        print(json.dumps({"cataloged": cataloged, "errors": errors}, indent=2))
        return 1 if errors else 0

    with connect(args.db) as connection:
        migrate(connection)
        if args.command == "list":
            rows = connection.execute(
                """
                SELECT a.id, a.sha256, a.size_bytes, COUNT(l.id) AS locations
                FROM assets a LEFT JOIN locations l ON l.asset_id = a.id
                GROUP BY a.id ORDER BY a.created_at
                """
            ).fetchall()
            for row in rows:
                print(
                    f"{atlas_uri(row['id'])} {row['size_bytes']} bytes "
                    f"{row['locations']} location(s) sha256={row['sha256']}"
                )
            return 0
        row = connection.execute(
            "SELECT * FROM assets WHERE id = ?", (args.asset_id,)
        ).fetchone()
        if row is None:
            print(f"asset not found: {args.asset_id}")
            return 2
        locations = connection.execute(
            "SELECT path, modified_ns, observed_at FROM locations WHERE asset_id = ?",
            (args.asset_id,),
        ).fetchall()
        payload = dict(row)
        payload["atlas_uri"] = atlas_uri(row["id"])
        payload["locations"] = [dict(location) for location in locations]
        print(json.dumps(payload, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
