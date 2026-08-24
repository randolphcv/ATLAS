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


LIST_ENTRY_LIMIT = 300
LIST_LENGTH_LIMIT = 200


def _correction(field: str, action: str, detail: str) -> dict[str, str]:
    """One recorded change Beacon made to untrusted input. Never silent."""
    return {"field": field, "action": action, "detail": detail}


def _normalize_list(
    value: object,
    field: str,
    *,
    degrade: bool = False,
    corrections: list[dict[str, str]] | None = None,
) -> list[str]:
    label = field.replace("_", " ")
    if value is None:
        return []
    if isinstance(value, str):
        values = value.splitlines()
    elif isinstance(value, list):
        values = value
    else:
        if not degrade:
            raise ValueError(f"{label.title()} must be a list.")
        corrections.append(
            _correction(
                field,
                "dropped_field",
                f"expected a list, received {type(value).__name__}",
            )
        )
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    dropped = 0
    longest = 0
    for item in values:
        text = " ".join(str(item).split()).strip()
        if not text:
            continue
        if len(text) > LIST_ENTRY_LIMIT:
            if not degrade:
                raise ValueError(
                    f"Each {label} entry must be {LIST_ENTRY_LIMIT} "
                    "characters or fewer."
                )
            # An entry this long is a sentence, not a tag. Truncating it would
            # produce a worse tag than having none, so it is dropped whole and
            # the valid entries are kept.
            dropped += 1
            longest = max(longest, len(text))
            continue
        key = text.casefold()
        if key not in seen:
            normalized.append(text)
            seen.add(key)
    if dropped:
        corrections.append(
            _correction(
                field,
                "dropped_entries",
                f"dropped {dropped} entry/entries over {LIST_ENTRY_LIMIT} "
                f"characters (longest {longest}); kept {len(normalized)}",
            )
        )
    if len(normalized) > LIST_LENGTH_LIMIT:
        if not degrade:
            raise ValueError(
                f"{label.title()} is limited to {LIST_LENGTH_LIMIT} entries."
            )
        corrections.append(
            _correction(
                field,
                "truncated_list",
                f"{len(normalized)} entries reduced to {LIST_LENGTH_LIMIT}",
            )
        )
        normalized = normalized[:LIST_LENGTH_LIMIT]
    return normalized


def _normalize(
    value: Mapping[str, object],
    *,
    degrade: bool,
    corrections: list[dict[str, str]],
) -> dict[str, Any]:
    unknown = set(value) - METADATA_FIELDS
    if unknown:
        if not degrade:
            raise ValueError(
                f"Unsupported metadata fields: {', '.join(sorted(unknown))}"
            )
        corrections.append(
            _correction(
                "*",
                "dropped_unknown_fields",
                f"ignored {len(unknown)} unsupported field(s): "
                f"{', '.join(sorted(unknown))}",
            )
        )
    result = empty_metadata()
    for field, limit in TEXT_LIMITS.items():
        raw = value.get(field)
        if isinstance(raw, (list, dict, tuple, set)):
            if not degrade:
                raise ValueError(
                    f"{field.replace('_', ' ').title()} must be text."
                )
            corrections.append(
                _correction(
                    field,
                    "dropped_field",
                    f"expected text, received {type(raw).__name__}",
                )
            )
            continue
        text = str(raw or "").strip()
        if len(text) > limit:
            if not degrade:
                raise ValueError(
                    f"{field.replace('_', ' ').title()} must be "
                    f"{limit:,} characters or fewer."
                )
            # Prose truncates cleanly; a shortened title still describes the
            # asset, which is worth more than discarding the whole analysis.
            corrections.append(
                _correction(
                    field,
                    "truncated",
                    f"{len(text)} characters truncated to {limit}",
                )
            )
            text = text[:limit].rstrip()
        result[field] = text
    for field in LIST_FIELDS:
        result[field] = _normalize_list(
            value.get(field),
            field,
            degrade=degrade,
            corrections=corrections,
        )
    return result


def normalize_metadata(value: Mapping[str, object]) -> dict[str, Any]:
    """Strict normalization. Human edits must be told when they are invalid."""
    return _normalize(value, degrade=False, corrections=[])


def normalize_metadata_degraded(
    value: Mapping[str, object],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Lenient normalization for untrusted input, with every change recorded.

    A local model is an untrusted input source: over-long strings, wrong types
    and missing keys are normal output, not exceptional conditions. This path
    corrects the offending field and reports what it did rather than raising
    past the item being processed. See AGENTS.md section 10.
    """
    corrections: list[dict[str, str]] = []
    return _normalize(value, degrade=True, corrections=corrections), corrections


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
    degrade: bool = False,
) -> dict[str, Any]:
    """Persist editable metadata.

    ``degrade`` marks the value as untrusted input, typically local model
    output. Offending fields are corrected instead of raising, and every
    correction is returned and written to the audit trail.
    """
    if degrade:
        metadata, corrections = normalize_metadata_degraded(value)
    else:
        metadata, corrections = normalize_metadata(value), []
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
                "corrections": corrections,
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
        authority = (
            "ai" if updated_by.strip().casefold().startswith("beacon") else "human"
        )
        connection.executemany(
            """
            INSERT INTO asset_metadata_field_authority(
                asset_id,field,authority,source_reference,updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(asset_id,field) DO UPDATE SET
                authority=excluded.authority,
                source_reference=excluded.source_reference,
                updated_at=excluded.updated_at
            """,
            (
                (asset_id, field, authority, source, timestamp)
                for field in changed
            ),
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
                "corrections": corrections,
            },
        )
        if corrections:
            record_event(
                connection,
                kind="metadata_correction",
                state="complete",
                message=(
                    f"Beacon corrected {len(corrections)} field(s) of "
                    "untrusted analysis output before saving"
                ),
                asset_id=asset_id,
                details={
                    "revision": revision,
                    "source": source,
                    "updated_by": updated_by,
                    "corrections": corrections,
                },
            )
    return {
        **metadata,
        "revision": revision,
        "updated_by": updated_by,
        "updated_at": timestamp,
        "unchanged": False,
        "corrections": corrections,
    }


def apply_analysis_metadata(
    db_path: Path,
    asset_id: str,
    payload: Mapping[str, object],
    *,
    run_id: str,
) -> dict[str, Any]:
    """Refresh AI-owned editable fields while preserving every human-owned field."""
    current = get_asset_metadata(db_path, asset_id)
    editable = {
        key: current[key]
        for key in METADATA_FIELDS
    }
    with connect(db_path) as connection:
        authority = {
            row["field"]: row["authority"]
            for row in connection.execute(
                """
                SELECT field,authority FROM asset_metadata_field_authority
                WHERE asset_id=?
                """,
                (asset_id,),
            )
        }

    proposed: dict[str, object] = {
        "display_title": payload.get("title"),
        "description": payload.get("description"),
        "media_category": payload.get("media_category"),
        "tags": payload.get("tags"),
    }
    stock = payload.get("stock_metadata")
    if isinstance(stock, Mapping):
        lines: list[str] = ["Beacon stock/B-roll analysis:"]
        for key, value in stock.items():
            if value in (None, "", []):
                continue
            label = str(key).replace("_", " ").title()
            rendered = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
            lines.append(f"{label}: {rendered}")
        if len(lines) > 1:
            proposed["notes"] = "\n".join(lines)

    for field, value in proposed.items():
        if value is None or authority.get(field) == "human":
            continue
        if field in LIST_FIELDS:
            editable[field] = value
        else:
            text = str(value).strip()
            if text:
                editable[field] = text
    return save_asset_metadata(
        db_path,
        asset_id,
        editable,
        updated_by="Beacon local analyzer",
        source=f"analysis_run:{run_id}",
        degrade=True,
    )


def apply_analysis_organization_path(
    db_path: Path,
    asset_id: str,
    destination_directory: Path,
    *,
    run_id: str,
) -> dict[str, Any]:
    """Record the committed final directory unless a human owns that field."""
    current = get_asset_metadata(db_path, asset_id)
    with connect(db_path) as connection:
        authority = connection.execute(
            """
            SELECT authority FROM asset_metadata_field_authority
            WHERE asset_id=? AND field='organization_path'
            """,
            (asset_id,),
        ).fetchone()
    if authority is not None and authority["authority"] == "human":
        return current
    editable = {key: current[key] for key in METADATA_FIELDS}
    editable["organization_path"] = str(destination_directory)
    return save_asset_metadata(
        db_path,
        asset_id,
        editable,
        updated_by="Beacon local analyzer",
        source=f"analysis_move:{run_id}",
    )


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
