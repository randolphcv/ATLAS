from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import connect, migrate, record_event

TEXT_LIMITS = {
    "display_title": 300,
    "description": 8000,
    "media_category": 300,
    "event_date": 100,
    "place": 500,
    "client": 500,
    "project": 500,
    "rights": 4000,
    "notes": 8000,
    "organization_path": 1000,
}
LIST_FIELDS = {"tags", "people"}
METADATA_FIELDS = {*TEXT_LIMITS, *LIST_FIELDS}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_metadata() -> dict[str, Any]:
    return {
        "display_title": "",
        "description": "",
        "media_category": "",
        "tags": [],
        "people": [],
        "event_date": "",
        "place": "",
        "client": "",
        "project": "",
        "rights": "",
        "notes": "",
        "organization_path": "",
    }


def _normalize_list(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = value.splitlines()
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError(f"{field.replace('_', ' ').title()} must be a list.")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = " ".join(str(item).split()).strip()
        if not text:
            continue
        if len(text) > 300:
            raise ValueError(
                f"Each {field.replace('_', ' ')} entry must be 300 characters or fewer."
            )
        key = text.casefold()
        if key not in seen:
            normalized.append(text)
            seen.add(key)
    if len(normalized) > 200:
        raise ValueError(f"{field.replace('_', ' ').title()} is limited to 200 entries.")
    return normalized


def normalize_metadata(value: Mapping[str, object]) -> dict[str, Any]:
    unknown = set(value) - METADATA_FIELDS
    if unknown:
        raise ValueError(f"Unsupported metadata fields: {', '.join(sorted(unknown))}")
    result = empty_metadata()
    for field, limit in TEXT_LIMITS.items():
        text = str(value.get(field) or "").strip()
        if len(text) > limit:
            raise ValueError(
                f"{field.replace('_', ' ').title()} must be {limit:,} characters or fewer."
            )
        result[field] = text
    for field in LIST_FIELDS:
        result[field] = _normalize_list(value.get(field), field)
    return result


def get_asset_metadata(db_path: Path, asset_id: str) -> dict[str, Any]:
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            """
            SELECT metadata_json, revision, updated_by, updated_at
            FROM asset_metadata WHERE asset_id = ?
            """,
            (asset_id,),
        ).fetchone()
    if row is None:
        return {
            **empty_metadata(),
            "revision": 0,
            "updated_by": "",
            "updated_at": "",
        }
    payload = empty_metadata()
    stored = json.loads(row["metadata_json"])
    payload.update({key: stored.get(key, payload[key]) for key in payload})
    return {
        **payload,
        "revision": int(row["revision"]),
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
    }


def save_asset_metadata(
    db_path: Path,
    asset_id: str,
    value: Mapping[str, object],
    *,
    updated_by: str,
    source: str,
) -> dict[str, Any]:
    metadata = normalize_metadata(value)
    timestamp = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        asset = connection.execute(
            "SELECT id FROM assets WHERE id = ?",
            (asset_id,),
        ).fetchone()
        if asset is None:
            raise LookupError("Asset was not found.")
        existing = connection.execute(
            "SELECT metadata_json, revision FROM asset_metadata WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        previous = json.loads(existing["metadata_json"]) if existing else {}
        if existing and normalize_metadata(previous) == metadata:
            return {
                **metadata,
                "revision": int(existing["revision"]),
                "updated_by": updated_by,
                "updated_at": timestamp,
                "unchanged": True,
            }
        revision = int(existing["revision"]) + 1 if existing else 1
        encoded = json.dumps(metadata, sort_keys=True, ensure_ascii=False)
        connection.execute(
            """
            INSERT INTO asset_metadata(
                asset_id, metadata_json, revision, updated_by, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
                metadata_json = excluded.metadata_json,
                revision = excluded.revision,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (asset_id, encoded, revision, updated_by, timestamp),
        )
        connection.execute(
            """
            INSERT INTO asset_metadata_revisions(
                id, asset_id, revision, metadata_json,
                updated_by, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                asset_id,
                revision,
                encoded,
                updated_by,
                source,
                timestamp,
            ),
        )
        changed = sorted(
            field
            for field in METADATA_FIELDS
            if previous.get(field, empty_metadata()[field]) != metadata[field]
        )
        record_event(
            connection,
            kind="metadata",
            state="complete",
            message=f"Editable metadata saved (revision {revision})",
            asset_id=asset_id,
            details={
                "revision": revision,
                "updated_by": updated_by,
                "source": source,
                "changed_fields": changed,
            },
        )
    return {
        **metadata,
        "revision": revision,
        "updated_by": updated_by,
        "updated_at": timestamp,
        "unchanged": False,
    }


def set_policy(
    db_path: Path,
    key: str,
    value: object,
    *,
    source_kind: str,
    source_reference: str = "",
) -> None:
    key = key.strip()
    if not key or len(key) > 200:
        raise ValueError("Policy key must contain 1 to 200 characters.")
    timestamp = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        connection.execute(
            """
            INSERT INTO beacon_policies(
                key, value_json, source_kind, source_reference, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                source_kind = excluded.source_kind,
                source_reference = excluded.source_reference,
                updated_at = excluded.updated_at
            """,
            (
                key,
                json.dumps(value, sort_keys=True, ensure_ascii=False),
                source_kind,
                source_reference.strip(),
                timestamp,
            ),
        )


def get_policy(db_path: Path, key: str) -> object | None:
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            "SELECT value_json FROM beacon_policies WHERE key = ?",
            (key,),
        ).fetchone()
    return json.loads(row["value_json"]) if row else None
