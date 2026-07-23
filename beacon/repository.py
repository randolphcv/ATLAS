from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .database import connect, migrate
from .identity import atlas_uri


def _media_summary(value: str | None) -> dict[str, Any]:
    if not value:
        return {
            "kind": "file",
            "codec": None,
            "duration_seconds": None,
            "dimensions": None,
            "probe_error": None,
        }
    metadata = json.loads(value)
    streams = metadata.get("streams") or []
    stream = streams[0] if streams else {}
    codec_type = metadata.get("beacon_kind") or stream.get("codec_type")
    width = stream.get("width")
    height = stream.get("height")
    duration = stream.get("duration") or (metadata.get("format") or {}).get("duration")
    try:
        duration_seconds = round(float(duration), 3) if duration is not None else None
    except (TypeError, ValueError):
        duration_seconds = None
    if codec_type == "image":
        duration_seconds = None
    return {
        "kind": codec_type or ("error" if metadata.get("error") else "file"),
        "codec": stream.get("codec_name"),
        "duration_seconds": duration_seconds,
        "dimensions": f"{width} × {height}" if width and height else None,
        "probe_error": metadata.get("error"),
    }


def _asset_from_row(row: sqlite3.Row) -> dict[str, Any]:
    media = _media_summary(row["media_metadata_json"])
    path = row["primary_path"]
    return {
        "id": row["id"],
        "atlas_uri": atlas_uri(row["id"]),
        "sha256": row["sha256"],
        "size_bytes": row["size_bytes"],
        "created_at": row["created_at"],
        "last_seen_at": row["last_seen_at"],
        "primary_path": path,
        "filename": Path(path).name if path else "Unknown asset",
        "location_count": row["location_count"],
        **media,
    }


def catalog_summary(db_path: Path) -> dict[str, Any]:
    with connect(db_path) as connection:
        migrate(connection)
        counts = connection.execute(
            """
            SELECT
                COUNT(*) AS assets,
                COALESCE(SUM(size_bytes), 0) AS total_bytes
            FROM assets
            """
        ).fetchone()
        locations = connection.execute(
            "SELECT COUNT(*) FROM locations"
        ).fetchone()[0]
        duplicates = connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT asset_id FROM locations
                GROUP BY asset_id HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        failures = connection.execute(
            "SELECT COUNT(*) FROM system_events WHERE state = 'failed'"
        ).fetchone()[0]
        last_activity = connection.execute(
            "SELECT MAX(created_at) FROM system_events"
        ).fetchone()[0]
    return {
        "assets": counts["assets"],
        "locations": locations,
        "duplicate_groups": duplicates,
        "total_bytes": counts["total_bytes"],
        "failures": failures,
        "last_activity_at": last_activity,
    }


def search_assets(
    db_path: Path,
    *,
    query: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    pattern = f"%{query.strip()}%"
    where = """
        WHERE ? = '%%'
           OR a.id LIKE ?
           OR a.sha256 LIKE ?
           OR EXISTS (
               SELECT 1 FROM locations searched
               WHERE searched.asset_id = a.id AND searched.path LIKE ?
           )
    """
    with connect(db_path) as connection:
        migrate(connection)
        total = connection.execute(
            f"SELECT COUNT(*) FROM assets a {where}",
            (pattern, pattern, pattern, pattern),
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT
                a.*,
                MIN(l.path) AS primary_path,
                COUNT(l.id) AS location_count
            FROM assets a
            LEFT JOIN locations l ON l.asset_id = a.id
            {where}
            GROUP BY a.id
            ORDER BY a.last_seen_at DESC
            LIMIT ? OFFSET ?
            """,
            (pattern, pattern, pattern, pattern, limit, offset),
        ).fetchall()
    return {
        "items": [_asset_from_row(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def asset_detail(db_path: Path, asset_id: str) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            """
            SELECT
                a.*,
                MIN(l.path) AS primary_path,
                COUNT(l.id) AS location_count
            FROM assets a
            LEFT JOIN locations l ON l.asset_id = a.id
            WHERE a.id = ?
            GROUP BY a.id
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        result = _asset_from_row(row)
        result["locations"] = [
            dict(location)
            for location in connection.execute(
                """
                SELECT path, modified_ns, observed_at
                FROM locations WHERE asset_id = ? ORDER BY path
                """,
                (asset_id,),
            ).fetchall()
        ]
        result["events"] = [
            dict(event)
            for event in connection.execute(
                """
                SELECT id, kind, state, message, created_at
                FROM system_events
                WHERE asset_id = ?
                ORDER BY created_at DESC LIMIT 20
                """,
                (asset_id,),
            ).fetchall()
        ]
        return result


def recent_events(db_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 100))
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            """
            SELECT id, kind, state, message, asset_id, location_path, created_at
            FROM system_events ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
