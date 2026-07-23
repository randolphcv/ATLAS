from __future__ import annotations

import argparse
import logging
import os
import socket
import threading
import webbrowser
from pathlib import Path
from typing import Sequence

import uvicorn

from .api import AppSettings, create_app

DEFAULT_RUNTIME = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "ATLAS" / "Beacon"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="beacon-dashboard")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("BEACON_DB", DEFAULT_RUNTIME / "beacon.db")),
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path(
            os.environ.get("BEACON_BACKUP_DIR", DEFAULT_RUNTIME / "backups")
        ),
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise SystemExit("port must be between 1 and 65535")
    if not _port_available(args.port):
        raise SystemExit(
            f"port {args.port} is already in use; Beacon may already be running"
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = AppSettings(
        db_path=args.db.resolve(),
        backup_dir=args.backup_dir.resolve(),
    )
    app = create_app(settings)
    url = f"http://127.0.0.1:{args.port}"
    print("ATLAS Beacon is running locally.")
    print(f"Dashboard: {url}")
    print(f"Database:  {settings.db_path}")
    print("Close this window or press Ctrl+C to stop Beacon.")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        server_header=False,
        date_header=False,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

