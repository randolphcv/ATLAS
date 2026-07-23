from __future__ import annotations

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
) -> None:
    timestamp = _utc_now()
    connection.execute(
        """
        INSERT INTO beacon_threads(
            id, subject, kind, priority, state, origin,
            requires_approval, seed_key, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            thread_id,
            subject,
            kind,
            priority,
            state,
            origin,
            int(requires_approval),
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
    return message_id


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
    return {**dict(thread), "messages": [dict(row) for row in messages]}


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
            )
            inserted.append(thread_id)
    return inserted
