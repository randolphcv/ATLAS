from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .database import connect, migrate
from .identity import atlas_uri

RAW_PHOTO_EXTENSIONS = {
    ".3fr", ".arw", ".cr2", ".cr3", ".dng", ".erf", ".fff", ".iiq",
    ".kdc", ".mef", ".mos", ".mrw", ".nef", ".nrw", ".orf", ".pef",
    ".raf", ".raw", ".rw2", ".sr2", ".srf", ".x3f",
}
PHOTO_EXTENSIONS = RAW_PHOTO_EXTENSIONS | {
    ".avif", ".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png",
    ".tif", ".tiff", ".webp",
}
VIDEO_EXTENSIONS = {
    ".3g2", ".3gp", ".avi", ".braw", ".crm", ".m2ts", ".m4v", ".mkv",
    ".mov", ".mp4", ".mts", ".mxf", ".r3d", ".webm", ".wmv",
}
AUDIO_EXTENSIONS = {
    ".aac", ".aif", ".aiff", ".alac", ".flac", ".m4a", ".mp3", ".ogg",
    ".opus", ".wav", ".wma",
}
SUPPORT_FILE_EXTENSIONS = {
    ".aae",
    ".cfa",
    ".cos",
    ".dop",
    ".mie",
    ".pek",
    ".pp3",
    ".thm",
    ".xmp",
}


def _media_summary(value: str | None) -> dict[str, Any]:
    if not value:
        return {
            "kind": "file",
            "codec": None,
            "duration_seconds": None,
            "dimensions": None,
            "probe_error": None,
            "media_metadata": None,
        }
    metadata = json.loads(value)
    streams = metadata.get("streams") or []
    stream = next(
        (
            candidate
            for preferred_kind in ("video", "image", "audio")
            for candidate in streams
            if candidate.get("codec_type") == preferred_kind
        ),
        streams[0] if streams else {},
    )
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
        "media_metadata": metadata,
    }


def _asset_from_row(row: sqlite3.Row) -> dict[str, Any]:
    media = _media_summary(row["media_metadata_json"])
    path = row["primary_path"]
    metadata_json = (
        row["editable_metadata_json"]
        if "editable_metadata_json" in row.keys()
        else None
    )
    editable_metadata = json.loads(metadata_json) if metadata_json else {}
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
        "thumbnail_path": row["thumbnail_path"],
        "preview_video_path": (
            row["preview_video_path"]
            if "preview_video_path" in row.keys()
            else None
        ),
        "editable_metadata": editable_metadata,
        "analyzed": bool(row["analyzed"]) if "analyzed" in row.keys() else False,
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
        analysis_failures = connection.execute(
            """
            SELECT COUNT(*) FROM local_analysis_items
            WHERE state='failed' AND job_id=(
                SELECT id FROM local_analysis_jobs
                ORDER BY updated_at DESC LIMIT 1
            )
            """
        ).fetchone()[0]
        intake_failures = connection.execute(
            """
            SELECT COUNT(*) FROM intake_items
            WHERE state='failed' AND job_id=(
                SELECT id FROM intake_jobs ORDER BY updated_at DESC LIMIT 1
            )
            """
        ).fetchone()[0]
        failures = int(analysis_failures) + int(intake_failures)
        recorded_failures = connection.execute(
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
        "recorded_failures": recorded_failures,
        "last_activity_at": last_activity,
    }


def search_assets(
    db_path: Path,
    *,
    query: str = "",
    path_prefix: str = "",
    file_type: str = "all",
    include_hidden: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    pattern = f"%{query.strip()}%"
    prefix_pattern = f"{path_prefix.rstrip(chr(92))}{chr(92)}%" if path_prefix else "%"
    extension_groups = {
        "photo": PHOTO_EXTENSIONS,
        "raw": RAW_PHOTO_EXTENSIONS,
        "video": VIDEO_EXTENSIONS,
        "audio": AUDIO_EXTENSIONS,
    }
    selected_extensions = extension_groups.get(file_type, set())
    extension_clause = ""
    extension_parameters: list[str] = []
    if selected_extensions:
        extension_clause = " AND EXISTS (SELECT 1 FROM locations typed WHERE typed.asset_id=a.id AND (" + " OR ".join(
            "lower(typed.path) LIKE ?" for _ in selected_extensions
        ) + "))"
        extension_parameters = [f"%{suffix}" for suffix in sorted(selected_extensions)]
    elif file_type == "other":
        known = sorted(PHOTO_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS)
        extension_clause = " AND NOT EXISTS (SELECT 1 FROM locations typed WHERE typed.asset_id=a.id AND (" + " OR ".join(
            "lower(typed.path) LIKE ?" for _ in known
        ) + "))"
        extension_parameters = [f"%{suffix}" for suffix in known]
    hidden_clause = ""
    hidden_parameters: list[str] = []
    if not include_hidden:
        hidden_clause = """
        AND EXISTS (
            SELECT 1 FROM locations visible
            WHERE visible.asset_id=a.id
              AND NOT (
        """ + " OR ".join(
            "lower(visible.path) LIKE ?" for _ in SUPPORT_FILE_EXTENSIONS
        ) + """
              )
        )
        """
        hidden_parameters = [
            f"%{suffix}" for suffix in sorted(SUPPORT_FILE_EXTENSIONS)
        ]
    where = """
        WHERE (? = '%%'
           OR a.id LIKE ?
           OR a.sha256 LIKE ?
           OR EXISTS (
               SELECT 1 FROM locations searched
               WHERE searched.asset_id = a.id AND searched.path LIKE ?
           )
           OR EXISTS (
               SELECT 1 FROM analysis_results analyzed
               WHERE analyzed.asset_id = a.id
                 AND analyzed.review_state IN ('candidate', 'approved')
                 AND analyzed.payload_json LIKE ?
           )
           OR EXISTS (
               SELECT 1 FROM asset_metadata editable
               WHERE editable.asset_id = a.id
                 AND editable.metadata_json LIKE ?
           )
           OR EXISTS (
               SELECT 1 FROM asset_transcripts transcript
               WHERE transcript.asset_id = a.id
                 AND transcript.text LIKE ?
           )
    ) AND EXISTS (
        SELECT 1 FROM locations scoped
        WHERE scoped.asset_id=a.id AND lower(scoped.path) LIKE lower(?)
    )
    """ + extension_clause + hidden_clause
    parameters = [
        pattern, pattern, pattern, pattern, pattern, pattern, pattern,
        prefix_pattern,
        *extension_parameters,
        *hidden_parameters,
    ]
    with connect(db_path) as connection:
        migrate(connection)
        total = connection.execute(
            f"SELECT COUNT(*) FROM assets a {where}",
            parameters,
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT
                a.*,
                (
                    SELECT preferred.path
                    FROM locations preferred
                    WHERE preferred.asset_id = a.id
                    ORDER BY
                        CASE
                            WHEN EXISTS (
                                SELECT 1 FROM managed_moves managed
                                WHERE managed.asset_id = preferred.asset_id
                                  AND managed.destination_path = preferred.path
                                  AND managed.state = 'complete'
                            )
                            THEN 0
                            WHEN lower(preferred.path) LIKE 'j:\\library\\%'
                              OR lower(preferred.path) LIKE 'j:\\assets\\%'
                              OR lower(preferred.path) LIKE 'j:\\projects\\%'
                            THEN 1
                            WHEN lower(preferred.path) LIKE 'j:\\inbox\\%'
                            THEN 2
                            ELSE 3
                        END,
                        preferred.observed_at DESC,
                        preferred.path
                    LIMIT 1
                ) AS primary_path,
                COUNT(l.id) AS location_count,
                (
                    SELECT d.path FROM derivatives d
                    WHERE d.asset_id = a.id
                      AND d.kind = 'thumbnail'
                      AND d.state = 'complete'
                    ORDER BY d.verified_at DESC LIMIT 1
                ) AS thumbnail_path
                ,(
                    SELECT d.path FROM derivatives d
                    WHERE d.asset_id = a.id
                      AND d.kind = 'preview_video'
                      AND d.state = 'complete'
                    ORDER BY d.verified_at DESC LIMIT 1
                ) AS preview_video_path
                ,(
                    SELECT editable.metadata_json
                    FROM asset_metadata editable
                    WHERE editable.asset_id = a.id
                ) AS editable_metadata_json
                ,EXISTS (
                    SELECT 1 FROM analysis_results analyzed
                    WHERE analyzed.asset_id=a.id
                      AND analyzed.analysis_kind='contextual_metadata'
                      AND analyzed.review_state IN ('candidate','approved')
                ) AS analyzed
            FROM assets a
            LEFT JOIN locations l ON l.asset_id = a.id
            {where}
            GROUP BY a.id
            ORDER BY a.last_seen_at DESC
            LIMIT ? OFFSET ?
            """,
            (
                *parameters,
                limit,
                offset,
            ),
        ).fetchall()
    return {
        "items": [_asset_from_row(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def library_folders(
    db_path: Path,
    path_prefix: str = "J:\\",
    *,
    include_hidden: bool = False,
) -> list[dict[str, Any]]:
    """Return direct catalog-backed child folders beneath a Windows path."""
    base = path_prefix.rstrip("\\")
    prefix = f"{base}\\"
    counts: dict[str, set[str]] = {}
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            """
            SELECT asset_id,path FROM locations
            WHERE lower(path) LIKE lower(?)
            ORDER BY path COLLATE NOCASE
            """,
            (f"{prefix}%",),
        ).fetchall()
    for row in rows:
        path = str(row["path"])
        if (
            not include_hidden
            and Path(path).suffix.lower() in SUPPORT_FILE_EXTENSIONS
        ):
            continue
        remainder = path[len(prefix):] if path.lower().startswith(prefix.lower()) else ""
        if "\\" not in remainder:
            continue
        child = remainder.split("\\", 1)[0]
        child_path = f"{base}\\{child}"
        counts.setdefault(child_path, set()).add(str(row["asset_id"]))
    return [
        {
            "name": Path(folder).name,
            "path": folder,
            "asset_count": len(asset_ids),
        }
        for folder, asset_ids in sorted(counts.items(), key=lambda item: item[0].lower())
    ]


def missing_thumbnail_assets(
    db_path: Path,
    *,
    extensions: set[str],
    limit: int = 250,
) -> list[dict[str, Any]]:
    """Return checksum-bound image sources that lack a completed thumbnail."""
    normalized = {suffix.lower() for suffix in extensions}
    if not normalized:
        return []
    patterns = [f"%{suffix}" for suffix in sorted(normalized)]
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            f"""
            SELECT a.id, a.sha256, a.media_metadata_json,
                   (
                       SELECT preferred.path
                       FROM locations preferred
                       WHERE preferred.asset_id=a.id
                         AND (
                           {" OR ".join(
                               "lower(preferred.path) LIKE ?"
                               for _ in patterns
                           )}
                         )
                       ORDER BY preferred.observed_at DESC
                       LIMIT 1
                   ) AS source_path
            FROM assets a
            WHERE EXISTS (
                SELECT 1 FROM locations typed
                WHERE typed.asset_id=a.id
                  AND (
                    {" OR ".join(
                        "lower(typed.path) LIKE ?" for _ in patterns
                    )}
                  )
            )
              AND NOT EXISTS (
                SELECT 1 FROM derivatives d
                WHERE d.asset_id=a.id
                  AND d.kind='thumbnail'
                  AND d.state='complete'
                  AND d.source_sha256=a.sha256
              )
            ORDER BY a.last_seen_at DESC
            LIMIT ?
            """,
            (*patterns, *patterns, max(1, min(limit, 1000))),
        ).fetchall()
    return [
        {
            "asset_id": row["id"],
            "source_sha256": row["sha256"],
            "source_path": row["source_path"],
            "media_metadata": json.loads(
                row["media_metadata_json"] or "{}"
            ),
        }
        for row in rows
        if row["source_path"]
    ]


def asset_detail(db_path: Path, asset_id: str) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            """
            SELECT
                a.*,
                (
                    SELECT preferred.path
                    FROM locations preferred
                    WHERE preferred.asset_id = a.id
                    ORDER BY
                        CASE
                            WHEN EXISTS (
                                SELECT 1 FROM managed_moves managed
                                WHERE managed.asset_id = preferred.asset_id
                                  AND managed.destination_path = preferred.path
                                  AND managed.state = 'complete'
                            )
                            THEN 0
                            WHEN lower(preferred.path) LIKE 'j:\\library\\%'
                              OR lower(preferred.path) LIKE 'j:\\assets\\%'
                              OR lower(preferred.path) LIKE 'j:\\projects\\%'
                            THEN 1
                            WHEN lower(preferred.path) LIKE 'j:\\inbox\\%'
                            THEN 2
                            ELSE 3
                        END,
                        preferred.observed_at DESC,
                        preferred.path
                    LIMIT 1
                ) AS primary_path,
                COUNT(l.id) AS location_count,
                (
                    SELECT d.path FROM derivatives d
                    WHERE d.asset_id = a.id
                      AND d.kind = 'thumbnail'
                      AND d.state = 'complete'
                    ORDER BY d.verified_at DESC LIMIT 1
                ) AS thumbnail_path
                ,(
                    SELECT editable.metadata_json
                    FROM asset_metadata editable
                    WHERE editable.asset_id = a.id
                ) AS editable_metadata_json
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
        analysis_rows = connection.execute(
            """
            SELECT
                r.id,
                r.analysis_kind,
                r.confidence,
                r.review_state,
                r.created_at,
                r.payload_json,
                r.provenance_json,
                runs.analyzer,
                runs.analyzer_version,
                runs.policy_version,
                runs.execution_location,
                runs.external_inference
            FROM analysis_results r
            JOIN analysis_runs runs ON runs.id = r.run_id
            WHERE r.asset_id = ?
            ORDER BY
                CASE r.review_state
                    WHEN 'approved' THEN 0
                    WHEN 'candidate' THEN 1
                    ELSE 2
                END,
                r.created_at DESC
            """,
            (asset_id,),
        ).fetchall()
        result["analysis"] = []
        for analysis in analysis_rows:
            item = dict(analysis)
            item["payload"] = json.loads(item.pop("payload_json"))
            item["provenance"] = json.loads(item.pop("provenance_json"))
            item["external_inference"] = bool(item["external_inference"])
            result["analysis"].append(item)
        transcript = connection.execute(
            """
            SELECT id,text,text_sha256,language,language_probability,
                   generator,created_at,verified_at
            FROM asset_transcripts
            WHERE asset_id=? AND source_sha256=?
            ORDER BY verified_at DESC LIMIT 1
            """,
            (asset_id, result["sha256"]),
        ).fetchone()
        result["transcript"] = dict(transcript) if transcript else {}
        music = connection.execute(
            """
            SELECT result_json,worker_version,verified_at
            FROM asset_music_analysis
            WHERE asset_id=? AND source_sha256=?
            ORDER BY verified_at DESC LIMIT 1
            """,
            (asset_id, result["sha256"]),
        ).fetchone()
        result["music_analysis"] = (
            {
                **json.loads(music["result_json"]),
                "worker_version": music["worker_version"],
                "verified_at": music["verified_at"],
            }
            if music
            else {}
        )
        editable = connection.execute(
            """
            SELECT metadata_json, revision, updated_by, updated_at
            FROM asset_metadata WHERE asset_id = ?
            """,
            (asset_id,),
        ).fetchone()
        if editable is None:
            result["editable_metadata"] = {}
            result["metadata_revision"] = 0
            result["metadata_updated_by"] = ""
            result["metadata_updated_at"] = ""
        else:
            result["editable_metadata"] = json.loads(editable["metadata_json"])
            result["metadata_revision"] = int(editable["revision"])
            result["metadata_updated_by"] = editable["updated_by"]
            result["metadata_updated_at"] = editable["updated_at"]
        result["moves"] = [
            dict(move)
            for move in connection.execute(
                """
                SELECT id, source_path, destination_path, state,
                       requested_by, authorization, error,
                       created_at, completed_at
                FROM managed_moves
                WHERE asset_id = ?
                ORDER BY created_at DESC
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
