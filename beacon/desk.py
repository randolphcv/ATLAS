from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import connect, migrate, record_event

SUBJECT_LIMIT = 160
MESSAGE_LIMIT = 8000
THREAD_NAMESPACE = uuid.UUID("4f6b6eb5-5bc4-4f5f-a20c-fc6cbb66563d")

KINDS = {"blocker", "question", "clarification", "approval", "request"}
PRIORITIES = {"normal", "important", "urgent"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_text(value: str, *, label: str, limit: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required.")
    if len(normalized) > limit:
        raise ValueError(f"{label} must be {limit:,} characters or fewer.")
    return normalized


def _validate_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized not in KINDS:
        raise ValueError(f"Unsupported Beacon thread kind: {kind}")
    return normalized


def _validate_priority(priority: str) -> str:
    normalized = priority.strip().lower()
    if normalized not in PRIORITIES:
        raise ValueError(f"Unsupported Beacon thread priority: {priority}")
    return normalized


def _insert_thread(
    connection: Any,
    *,
    thread_id: str,
    subject: str,
    body: str,
    kind: str,
    priority: str,
    state: str,
    origin: str,
    author: str,
    requires_approval: bool,
    seed_key: str | None = None,
    asset_id: str | None = None,
) -> None:
    timestamp = _utc_now()
    connection.execute(
        """
        INSERT INTO beacon_threads(
            id, subject, kind, priority, state, origin,
            requires_approval, asset_id, seed_key, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            thread_id,
            subject,
            kind,
            priority,
            state,
            origin,
            int(requires_approval),
            asset_id,
            seed_key,
            timestamp,
            timestamp,
        ),
    )
    connection.execute(
        """
        INSERT INTO beacon_messages(id, thread_id, author, body, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), thread_id, author, body, timestamp),
    )


def create_human_thread(
    db_path: Path,
    *,
    subject: str,
    body: str,
    kind: str = "request",
    priority: str = "normal",
) -> str:
    subject = _required_text(subject, label="Subject", limit=SUBJECT_LIMIT)
    body = _required_text(body, label="Message", limit=MESSAGE_LIMIT)
    kind = _validate_kind(kind)
    priority = _validate_priority(priority)
    thread_id = str(uuid.uuid4())
    with connect(db_path) as connection:
        migrate(connection)
        _insert_thread(
            connection,
            thread_id=thread_id,
            subject=subject,
            body=body,
            kind=kind,
            priority=priority,
            state="queued_for_beacon",
            origin="human",
            author="human",
            requires_approval=False,
        )
        record_event(
            connection,
            kind="beacon_desk",
            state="complete",
            message=f"New request saved for Beacon: {subject}",
            details={"thread_id": thread_id, "action": "created"},
        )
    return thread_id


def reply_to_thread(db_path: Path, thread_id: str, body: str) -> str:
    body = _required_text(body, label="Reply", limit=MESSAGE_LIMIT)
    message_id = str(uuid.uuid4())
    timestamp = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        thread = connection.execute(
            "SELECT subject, state FROM beacon_threads WHERE id = ?",
            (thread_id,),
        ).fetchone()
        if thread is None:
            raise LookupError("Beacon thread was not found.")
        if thread["state"] in {"resolved", "closed"}:
            raise ValueError("Closed Beacon threads cannot receive replies.")
        connection.execute(
            """
            INSERT INTO beacon_messages(id, thread_id, author, body, created_at)
            VALUES (?, ?, 'human', ?, ?)
            """,
            (message_id, thread_id, body, timestamp),
        )
        connection.execute(
            """
            UPDATE beacon_threads
            SET state = 'queued_for_beacon', updated_at = ?, resolved_at = NULL
            WHERE id = ?
            """,
            (timestamp, thread_id),
        )
        record_event(
            connection,
            kind="beacon_desk",
            state="complete",
            message=f"Human reply saved for Beacon: {thread['subject']}",
            details={
                "thread_id": thread_id,
                "message_id": message_id,
                "action": "human_reply",
                "file_action_authorized": False,
            },
        )
    return message_id


def add_beacon_message(
    db_path: Path,
    thread_id: str,
    body: str,
    *,
    needs_human: bool = True,
    result_cards: Iterable[Mapping[str, object]] = (),
) -> str:
    """Worker boundary for a future Beacon process; never performs file actions."""
    body = _required_text(body, label="Message", limit=MESSAGE_LIMIT)
    message_id = str(uuid.uuid4())
    timestamp = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        thread = connection.execute(
            "SELECT id FROM beacon_threads WHERE id = ?",
            (thread_id,),
        ).fetchone()
        if thread is None:
            raise LookupError("Beacon thread was not found.")
        connection.execute(
            """
            INSERT INTO beacon_messages(id, thread_id, author, body, created_at)
            VALUES (?, ?, 'beacon', ?, ?)
            """,
            (message_id, thread_id, body, timestamp),
        )
        connection.execute(
            """
            UPDATE beacon_threads
            SET state = ?, updated_at = ?, resolved_at = NULL
            WHERE id = ?
            """,
            (
                "awaiting_human" if needs_human else "queued_for_beacon",
                timestamp,
                thread_id,
            ),
        )
        _insert_result_cards(connection, message_id, result_cards)
    return message_id


def _insert_result_cards(
    connection: Any,
    message_id: str,
    cards: Iterable[Mapping[str, object]],
) -> None:
    prepared = list(cards)
    if len(prepared) > 12:
        raise ValueError("Beacon messages may reference at most 12 assets.")
    for rank, card in enumerate(prepared, start=1):
        asset_id = _required_text(
            str(card.get("asset_id") or ""),
            label="Result asset ID",
            limit=64,
        )
        reason = _required_text(
            str(card.get("match_reason") or ""),
            label="Result match reason",
            limit=500,
        )
        matched_path = str(card.get("matched_path") or "").strip() or None
        if matched_path and len(matched_path) > 2000:
            raise ValueError("Result path must be 2,000 characters or fewer.")
        exists = connection.execute(
            "SELECT 1 FROM assets WHERE id=?",
            (asset_id,),
        ).fetchone()
        if exists is None:
            raise LookupError(f"Catalog result asset was not found: {asset_id}")
        connection.execute(
            """
            INSERT INTO beacon_message_assets(
                message_id,asset_id,rank,match_reason,matched_path
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, asset_id, rank, reason, matched_path),
        )


def resolve_thread(db_path: Path, thread_id: str) -> None:
    timestamp = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        thread = connection.execute(
            "SELECT subject, state FROM beacon_threads WHERE id = ?",
            (thread_id,),
        ).fetchone()
        if thread is None:
            raise LookupError("Beacon thread was not found.")
        if thread["state"] in {"resolved", "closed"}:
            return
        connection.execute(
            """
            UPDATE beacon_threads
            SET state = 'resolved', updated_at = ?, resolved_at = ?
            WHERE id = ?
            """,
            (timestamp, timestamp, thread_id),
        )
        record_event(
            connection,
            kind="beacon_desk",
            state="complete",
            message=f"Beacon thread resolved: {thread['subject']}",
            details={"thread_id": thread_id, "action": "resolved"},
        )


def list_threads(
    db_path: Path,
    *,
    include_closed: bool = False,
) -> list[dict[str, Any]]:
    where = "" if include_closed else "WHERE t.state NOT IN ('resolved', 'closed')"
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            f"""
            SELECT
                t.*,
                (
                    SELECT body
                    FROM beacon_messages latest
                    WHERE latest.thread_id = t.id
                    ORDER BY latest.created_at DESC, latest.rowid DESC
                    LIMIT 1
                ) AS latest_message,
                (
                    SELECT COUNT(*)
                    FROM beacon_messages count_messages
                    WHERE count_messages.thread_id = t.id
                ) AS message_count
            FROM beacon_threads t
            {where}
            ORDER BY
                CASE t.state
                    WHEN 'awaiting_human' THEN 0
                    WHEN 'queued_for_beacon' THEN 1
                    ELSE 2
                END,
                CASE t.priority
                    WHEN 'urgent' THEN 0
                    WHEN 'important' THEN 1
                    ELSE 2
                END,
                t.updated_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def thread_detail(db_path: Path, thread_id: str) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        migrate(connection)
        thread = connection.execute(
            "SELECT * FROM beacon_threads WHERE id = ?",
            (thread_id,),
        ).fetchone()
        if thread is None:
            return None
        messages = connection.execute(
            """
            SELECT * FROM beacon_messages
            WHERE thread_id = ?
            ORDER BY created_at, rowid
            """,
            (thread_id,),
        ).fetchall()
        cards = connection.execute(
            """
            SELECT
                cards.message_id,cards.asset_id,cards.rank,
                cards.match_reason,cards.matched_path,
                assets.sha256,assets.size_bytes,
                (
                    SELECT preferred.path FROM locations preferred
                    WHERE preferred.asset_id=cards.asset_id
                    ORDER BY
                        CASE
                            WHEN lower(preferred.path) LIKE 'j:\\library\\%'
                              OR lower(preferred.path) LIKE 'j:\\assets\\%'
                              OR lower(preferred.path) LIKE 'j:\\projects\\%'
                            THEN 0
                            WHEN lower(preferred.path) LIKE 'j:\\inbox\\%'
                            THEN 1
                            ELSE 2
                        END,
                        preferred.observed_at DESC
                    LIMIT 1
                ) AS current_path,
                (
                    SELECT metadata_json FROM asset_metadata
                    WHERE asset_id=cards.asset_id
                ) AS metadata_json,
                (
                    SELECT path FROM derivatives
                    WHERE asset_id=cards.asset_id
                      AND kind='thumbnail' AND state='complete'
                    ORDER BY verified_at DESC LIMIT 1
                ) AS thumbnail_path
            FROM beacon_message_assets cards
            JOIN assets ON assets.id=cards.asset_id
            WHERE cards.message_id IN (
                SELECT id FROM beacon_messages WHERE thread_id=?
            )
            ORDER BY cards.message_id,cards.rank
            """,
            (thread_id,),
        ).fetchall()
    cards_by_message: dict[str, list[dict[str, Any]]] = {}
    for row in cards:
        card = dict(row)
        try:
            metadata = json.loads(card.pop("metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        current_path = str(card.get("current_path") or "")
        filename = current_path.replace("/", "\\").rsplit("\\", 1)[-1]
        card["filename"] = filename or f"Asset {card['asset_id'][:8]}"
        card["display_title"] = (
            metadata.get("display_title") or card["filename"]
        )
        card["atlas_uri"] = f"atlas://asset/{card['asset_id']}"
        card["available"] = bool(current_path and Path(current_path).exists())
        cards_by_message.setdefault(str(card["message_id"]), []).append(card)
    message_rows = []
    for row in messages:
        message = dict(row)
        message["result_cards"] = cards_by_message.get(message["id"], [])
        message_rows.append(message)
    return {**dict(thread), "messages": message_rows}


def desk_summary(db_path: Path) -> dict[str, int]:
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            """
            SELECT
                SUM(CASE WHEN state NOT IN ('resolved', 'closed') THEN 1 ELSE 0 END),
                SUM(CASE WHEN state = 'awaiting_human' THEN 1 ELSE 0 END),
                SUM(CASE WHEN state = 'queued_for_beacon' THEN 1 ELSE 0 END)
            FROM beacon_threads
            """
        ).fetchone()
    return {
        "open": int(row[0] or 0),
        "awaiting_human": int(row[1] or 0),
        "queued_for_beacon": int(row[2] or 0),
    }


def seed_threads(
    db_path: Path,
    seeds: Iterable[Mapping[str, object]],
) -> list[str]:
    inserted: list[str] = []
    with connect(db_path) as connection:
        migrate(connection)
        for seed in seeds:
            seed_key = _required_text(
                str(seed.get("seed_key") or ""),
                label="Seed key",
                limit=160,
            )
            if connection.execute(
                "SELECT 1 FROM beacon_threads WHERE seed_key = ?",
                (seed_key,),
            ).fetchone():
                continue
            subject = _required_text(
                str(seed.get("subject") or ""),
                label="Subject",
                limit=SUBJECT_LIMIT,
            )
            body = _required_text(
                str(seed.get("body") or ""),
                label="Message",
                limit=MESSAGE_LIMIT,
            )
            kind = _validate_kind(str(seed.get("kind") or "question"))
            priority = _validate_priority(
                str(seed.get("priority") or "normal")
            )
            thread_id = str(uuid.uuid5(THREAD_NAMESPACE, seed_key))
            _insert_thread(
                connection,
                thread_id=thread_id,
                subject=subject,
                body=body,
                kind=kind,
                priority=priority,
                state="awaiting_human",
                origin="beacon",
                author="beacon",
                requires_approval=bool(seed.get("requires_approval", False)),
                seed_key=seed_key,
                asset_id=(
                    str(seed["asset_id"]) if seed.get("asset_id") else None
                ),
            )
            inserted.append(thread_id)
    return inserted
