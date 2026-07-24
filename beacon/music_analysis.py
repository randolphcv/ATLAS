from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import sha256_file
from .database import connect, migrate, record_event

WORKER_VERSION = "beacon-music-v3"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def runtime_root() -> Path:
    return Path(
        os.environ.get(
            "BEACON_MUSIC_RUNTIME",
            r"C:\ProgramData\ATLAS\MusicRuntime",
        )
    )


def runtime_python() -> Path:
    return Path(
        os.environ.get(
            "BEACON_MUSIC_PYTHON",
            str(runtime_root() / "venv" / "Scripts" / "python.exe"),
        )
    )


def runtime_worker() -> Path:
    return Path(
        os.environ.get(
            "BEACON_MUSIC_WORKER",
            str(runtime_root() / "music_worker.py"),
        )
    )


def runtime_status(timeout: float = 30) -> dict[str, Any]:
    python = runtime_python()
    worker = runtime_worker()
    if not python.is_file() or not worker.is_file():
        return {
            "available": False,
            "error": "The isolated music runtime is not installed.",
        }
    completed = subprocess.run(
        [str(python), str(worker), "--status"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        return {
            "available": False,
            "error": (completed.stderr or completed.stdout)[-1000:],
        }
    try:
        value = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        return {"available": False, "error": f"Invalid runtime response: {error}"}
    return {"available": True, **value}


def get_asset_music_analysis(
    db_path: Path,
    asset_id: str,
    *,
    source_sha256: str,
) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            """
            SELECT result_json FROM asset_music_analysis
            WHERE asset_id=? AND source_sha256=? AND worker_version=?
            ORDER BY verified_at DESC LIMIT 1
            """,
            (asset_id, source_sha256, WORKER_VERSION),
        ).fetchone()
    return json.loads(row["result_json"]) if row else None


def analyze_asset_music(
    db_path: Path,
    *,
    asset_id: str,
    source_path: Path,
    source_sha256: str,
    full: bool = True,
    stems: bool = False,
    timeout: float = 7200,
) -> dict[str, Any]:
    cached = get_asset_music_analysis(
        db_path, asset_id, source_sha256=source_sha256
    )
    if cached:
        return {**cached, "cache_status": "cached"}
    status = runtime_status()
    if not status.get("available"):
        return {
            "status": "unavailable",
            "error": status.get("error") or "Music runtime unavailable.",
        }
    source = source_path.resolve(strict=True)
    if sha256_file(source) != source_sha256:
        raise ValueError("source bytes changed before music analysis")
    output = (
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        / "ATLAS"
        / "Beacon"
        / "derivatives"
        / "music"
        / asset_id
        / source_sha256
    )
    output.mkdir(parents=True, exist_ok=True)
    minimum_free = 50 * 1024**3 if stems else 10 * 1024**3
    if shutil.disk_usage(output).free < minimum_free:
        raise RuntimeError(
            "Insufficient derivative free space for local music analysis."
        )
    command = [
        str(runtime_python()),
        str(runtime_worker()),
        "--source",
        str(source),
        "--output",
        str(output),
    ]
    if full:
        command.append("--full")
    if stems:
        command.append("--stems")
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            "Local music analysis failed: "
            + (completed.stderr or completed.stdout)[-2000:]
        )
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid music worker response: {error}") from error
    if result.get("worker_version") != WORKER_VERSION:
        raise RuntimeError("Music worker version does not match Beacon.")
    for derivative in result.get("derivatives") or []:
        path = Path(str(derivative.get("path") or "")).resolve(strict=True)
        try:
            path.relative_to(output.resolve())
        except ValueError as error:
            raise RuntimeError("Music derivative escaped its output root.") from error
        if sha256_file(path) != derivative.get("sha256"):
            raise RuntimeError(f"Music derivative checksum mismatch: {path}")
    if sha256_file(source) != source_sha256:
        raise ValueError("source bytes changed during music analysis")
    encoded = _canonical_json(result)
    result_sha256 = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    timestamp = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        connection.execute(
            """
            INSERT INTO asset_music_analysis(
                id,asset_id,source_sha256,worker_version,result_json,
                result_sha256,created_at,verified_at
            ) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(asset_id,source_sha256,worker_version) DO UPDATE SET
                result_json=excluded.result_json,
                result_sha256=excluded.result_sha256,
                verified_at=excluded.verified_at
            """,
            (
                str(uuid.uuid4()),
                asset_id,
                source_sha256,
                WORKER_VERSION,
                encoded,
                result_sha256,
                timestamp,
                timestamp,
            ),
        )
        for derivative in result.get("derivatives") or []:
            connection.execute(
                """
                INSERT INTO derivatives(
                    id,asset_id,kind,path,source_sha256,sha256,size_bytes,
                    generator,state,details_json,created_at,verified_at
                ) VALUES (?,?,?,?,?,?,?,?, 'complete',?,?,?)
                ON CONFLICT(asset_id,kind,source_sha256) DO UPDATE SET
                    path=excluded.path,sha256=excluded.sha256,
                    size_bytes=excluded.size_bytes,
                    verified_at=excluded.verified_at
                """,
                (
                    str(uuid.uuid4()),
                    asset_id,
                    derivative["kind"],
                    derivative["path"],
                    source_sha256,
                    derivative["sha256"],
                    int(derivative["size_bytes"]),
                    WORKER_VERSION,
                    _canonical_json({"music_analysis": True}),
                    timestamp,
                    timestamp,
                ),
            )
        record_event(
            connection,
            kind="music_analysis",
            state="complete",
            message=(
                f"Local music analysis completed: "
                f"{result.get('key') or 'key unknown'}, "
                f"{result.get('bpm') or 'tempo unknown'} BPM"
            ),
            asset_id=asset_id,
            location_path=str(source),
            details={
                "worker_version": WORKER_VERSION,
                "music_confidence": result.get("music_confidence"),
                "derivatives": len(result.get("derivatives") or []),
            },
        )
    return {**result, "cache_status": "created"}
