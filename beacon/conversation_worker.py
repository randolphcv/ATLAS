from __future__ import annotations

import json
import os
import socket
import sqlite3
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from .database import connect, migrate, record_event
from .desk import MESSAGE_LIMIT, _insert_result_cards, thread_detail
from .repository import search_assets

MAX_SEARCH_QUERIES = 4
MAX_RESULT_CARDS = 8
MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARACTERS = 24_000
DEFAULT_LEASE_SECONDS = 15 * 60
FAILURE_BACKOFF_SECONDS = 5 * 60


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _future(seconds: int) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(seconds=max(1, seconds))
    ).isoformat()


def _past(seconds: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(seconds=max(1, seconds))
    ).isoformat()


def validate_loopback_endpoint(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "http" or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError(
            "Beacon conversation inference must use a local loopback HTTP endpoint."
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("The local conversation endpoint is not valid.")
    return normalized


@dataclass(frozen=True)
class ConversationPlan:
    search_queries: tuple[str, ...]


@dataclass(frozen=True)
class WorkerClaim:
    run_id: str
    thread_id: str
    worker_id: str
    endpoint: str
    model: str


@dataclass(frozen=True)
class WorkerCycleResult:
    state: str
    thread_id: str | None = None
    message_id: str | None = None
    result_count: int = 0
    error: str | None = None


class ConversationAdapter(Protocol):
    def plan(self, messages: list[dict[str, str]]) -> ConversationPlan: ...

    def respond(
        self,
        messages: list[dict[str, str]],
        results: list[dict[str, Any]],
    ) -> str: ...


class OllamaConversationAdapter:
    """Loopback-only, two-pass adapter with no free-form filesystem tools."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        *,
        timeout_seconds: float = 120,
    ) -> None:
        self.endpoint = validate_loopback_endpoint(endpoint)
        self.model = model.strip()
        if not self.model:
            raise ValueError("A local conversation model is required.")
        self.timeout_seconds = timeout_seconds

    def _chat_json(
        self,
        *,
        system: str,
        content: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "format": schema,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 1200},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                outer = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Local Beacon conversation model is unavailable: {error}"
            ) from error
        message = outer.get("message")
        if not isinstance(message, dict):
            raise ValueError("Local conversation model returned no message.")
        content_value = message.get("content")
        if not isinstance(content_value, str):
            raise ValueError("Local conversation model returned invalid content.")
        result = json.loads(content_value)
        if not isinstance(result, dict):
            raise ValueError("Local conversation model result is not an object.")
        return result

    def plan(self, messages: list[dict[str, str]]) -> ConversationPlan:
        schema = {
            "type": "object",
            "properties": {
                "search_queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": MAX_SEARCH_QUERIES,
                }
            },
            "required": ["search_queries"],
        }
        result = self._chat_json(
            system=(
                "You are the planning boundary for Beacon's read-only local "
                "catalog. Return zero to four short literal catalog search "
                "queries. Use individual names, places, projects, filenames, "
                "or visual concepts rather than full sentences. Return no "
                "query when the conversation does not require catalog facts. "
                "Never propose a file operation."
            ),
            content=json.dumps({"conversation": messages}, ensure_ascii=False),
            schema=schema,
        )
        return ConversationPlan(
            search_queries=_normalize_queries(result.get("search_queries"))
        )

    def respond(
        self,
        messages: list[dict[str, str]],
        results: list[dict[str, Any]],
    ) -> str:
        schema = {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        }
        evidence = [
            {
                "reference": index,
                "atlas_uri": item["atlas_uri"],
                "filename": item["filename"],
                "path": item["primary_path"],
                "kind": item.get("kind"),
                "title": (
                    item.get("editable_metadata") or {}
                ).get("display_title"),
                "match_reason": item["match_reason"],
                "available": item["available"],
            }
            for index, item in enumerate(results, start=1)
        ]
        result = self._chat_json(
            system=(
                "You are Beacon, a calm local archive librarian. Answer only "
                "from the conversation and supplied catalog evidence. Cite "
                "catalog matches as [1], [2], and so on. If evidence is "
                "insufficient or the request is ambiguous, ask one focused "
                "question. Never claim to have copied, moved, shared, opened, "
                "or modified a file. Result cards let the human inspect assets."
            ),
            content=json.dumps(
                {"conversation": messages, "catalog_evidence": evidence},
                ensure_ascii=False,
            ),
            schema=schema,
        )
        message = str(result.get("message") or "").strip()
        if not message:
            raise ValueError("Local conversation model returned an empty message.")
        if len(message) > MESSAGE_LIMIT:
            raise ValueError("Local conversation response exceeds the Desk limit.")
        return message


def _normalize_queries(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    queries: list[str] = []
    seen: set[str] = set()
    for item in value:
        query = " ".join(str(item).split()).strip()
        key = query.casefold()
        if not query or len(query) > 120 or key in seen:
            continue
        seen.add(key)
        queries.append(query)
        if len(queries) >= MAX_SEARCH_QUERIES:
            break
    return tuple(queries)


def _bounded_history(detail: dict[str, Any]) -> list[dict[str, str]]:
    messages = detail.get("messages") or []
    prepared: list[dict[str, str]] = []
    remaining = MAX_HISTORY_CHARACTERS
    for message in reversed(messages[-MAX_HISTORY_MESSAGES:]):
        body = str(message.get("body") or "")
        if not body:
            continue
        if len(body) > remaining:
            body = body[-remaining:]
        prepared.append(
            {
                "author": str(message.get("author") or "system"),
                "body": body,
            }
        )
        remaining -= len(body)
        if remaining <= 0:
            break
    prepared.reverse()
    return prepared


def _analysis_running(connection: Any) -> bool:
    return connection.execute(
        "SELECT 1 FROM local_analysis_jobs WHERE state='running' LIMIT 1"
    ).fetchone() is not None


def _live_analysis_running_without_migration(db_path: Path) -> bool:
    """Protect a live older-schema catalog from worker-triggered migration."""
    if not db_path.exists():
        return False
    connection: sqlite3.Connection | None = None
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        return connection.execute(
            "SELECT 1 FROM local_analysis_jobs WHERE state='running' LIMIT 1"
        ).fetchone() is not None
    except sqlite3.OperationalError as error:
        if "no such table" in str(error).casefold():
            return False
        # If an existing catalog cannot be inspected safely, do not risk
        # migrating it while another process may be analyzing it.
        return True
    finally:
        if connection is not None:
            connection.close()


def claim_next_thread(
    db_path: Path,
    *,
    endpoint: str,
    model: str,
    worker_id: str | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> tuple[WorkerClaim | None, str]:
    endpoint = validate_loopback_endpoint(endpoint)
    model = model.strip()
    if not model:
        raise ValueError("A local conversation model is required.")
    worker_id = worker_id or (
        f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4()}"
    )
    if _live_analysis_running_without_migration(db_path):
        return None, "analysis_running"
    now = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE beacon_worker_runs
            SET state='expired',completed_at=?,error='Worker lease expired.'
            WHERE state='running' AND lease_expires_at < ?
            """,
            (now, now),
        )
        if _analysis_running(connection):
            return None, "analysis_running"
        row = connection.execute(
            """
            SELECT threads.id
            FROM beacon_threads threads
            WHERE threads.state='queued_for_beacon'
              AND NOT EXISTS (
                SELECT 1 FROM beacon_worker_runs active
                WHERE active.thread_id=threads.id AND active.state='running'
              )
              AND NOT EXISTS (
                SELECT 1 FROM beacon_worker_runs recent_failure
                WHERE recent_failure.thread_id=threads.id
                  AND recent_failure.state='failed'
                  AND recent_failure.completed_at > ?
              )
            ORDER BY
                CASE threads.priority
                    WHEN 'urgent' THEN 0
                    WHEN 'important' THEN 1
                    ELSE 2
                END,
                threads.updated_at
            LIMIT 1
            """,
            (_past(FAILURE_BACKOFF_SECONDS),),
        ).fetchone()
        if row is None:
            return None, "idle"
        run_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO beacon_worker_runs(
                id,thread_id,worker_id,endpoint,model,state,
                claimed_at,lease_expires_at
            ) VALUES (?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (
                run_id,
                row["id"],
                worker_id,
                endpoint,
                model,
                now,
                _future(lease_seconds),
            ),
        )
        record_event(
            connection,
            kind="beacon_conversation_worker",
            state="running",
            message="Beacon claimed a queued local conversation.",
            details={
                "run_id": run_id,
                "thread_id": row["id"],
                "worker_id": worker_id,
                "model": model,
                "endpoint": endpoint,
            },
        )
    return (
        WorkerClaim(run_id, str(row["id"]), worker_id, endpoint, model),
        "claimed",
    )


def _grounded_search(
    db_path: Path,
    queries: tuple[str, ...],
) -> list[dict[str, Any]]:
    matches: dict[str, dict[str, Any]] = {}
    reasons: dict[str, list[str]] = {}
    for query in queries:
        page = search_assets(db_path, query=query, limit=6)
        for item in page["items"]:
            asset_id = str(item["id"])
            matches.setdefault(asset_id, item)
            reasons.setdefault(asset_id, []).append(
                _catalog_match_reason(db_path, item, query)
            )
            if len(matches) >= MAX_RESULT_CARDS:
                break
        if len(matches) >= MAX_RESULT_CARDS:
            break
    grounded: list[dict[str, Any]] = []
    for asset_id, item in matches.items():
        path = str(item.get("primary_path") or "")
        grounded.append(
            {
                **item,
                "match_reason": "; ".join(reasons[asset_id]),
                "available": bool(path and Path(path).exists()),
            }
        )
    return grounded


def _catalog_match_reason(
    db_path: Path,
    item: dict[str, Any],
    query: str,
) -> str:
    folded = query.casefold()
    path = str(item.get("primary_path") or "")
    if folded in path.casefold():
        return f'Filename/path match for “{query}”'
    metadata = item.get("editable_metadata") or {}
    metadata_text = json.dumps(metadata, ensure_ascii=False)
    if folded in metadata_text.casefold():
        return f'Editable metadata match for “{query}”'
    with connect(db_path) as connection:
        transcript = connection.execute(
            """
            SELECT text FROM asset_transcripts
            WHERE asset_id=? AND instr(lower(text),lower(?)) > 0
            ORDER BY verified_at DESC LIMIT 1
            """,
            (item["id"], query),
        ).fetchone()
    if transcript is not None:
        text = " ".join(str(transcript["text"]).split())
        position = text.casefold().find(folded)
        start = max(0, position - 90)
        end = min(len(text), position + len(query) + 130)
        excerpt = text[start:end]
        if start:
            excerpt = f"…{excerpt}"
        if end < len(text):
            excerpt = f"{excerpt}…"
        return f'Transcript match for “{query}”: “{excerpt}”'
    return f'Analyzed catalog context match for “{query}”'


def _complete_claim(
    db_path: Path,
    claim: WorkerClaim,
    body: str,
    results: list[dict[str, Any]],
) -> str:
    timestamp = _utc_now()
    message_id = str(uuid.uuid4())
    cards = [
        {
            "asset_id": item["id"],
            "match_reason": item["match_reason"],
            "matched_path": item.get("primary_path"),
        }
        for item in results[:MAX_RESULT_CARDS]
    ]
    with connect(db_path) as connection:
        migrate(connection)
        connection.execute("BEGIN IMMEDIATE")
        run = connection.execute(
            """
            SELECT state,worker_id,thread_id FROM beacon_worker_runs
            WHERE id=?
            """,
            (claim.run_id,),
        ).fetchone()
        if (
            run is None
            or run["state"] != "running"
            or run["worker_id"] != claim.worker_id
            or run["thread_id"] != claim.thread_id
        ):
            raise RuntimeError("Beacon conversation worker lease was lost.")
        connection.execute(
            """
            INSERT INTO beacon_messages(id,thread_id,author,body,created_at)
            VALUES (?, ?, 'beacon', ?, ?)
            """,
            (message_id, claim.thread_id, body, timestamp),
        )
        _insert_result_cards(connection, message_id, cards)
        connection.execute(
            """
            UPDATE beacon_threads
            SET state='awaiting_human',updated_at=?,resolved_at=NULL
            WHERE id=?
            """,
            (timestamp, claim.thread_id),
        )
        connection.execute(
            """
            UPDATE beacon_worker_runs
            SET state='complete',completed_at=?,error=NULL WHERE id=?
            """,
            (timestamp, claim.run_id),
        )
        record_event(
            connection,
            kind="beacon_conversation_worker",
            state="complete",
            message="Beacon answered a queued local conversation.",
            details={
                "run_id": claim.run_id,
                "thread_id": claim.thread_id,
                "message_id": message_id,
                "result_count": len(cards),
                "file_action_authorized": False,
            },
        )
    return message_id


def _fail_claim(db_path: Path, claim: WorkerClaim, error: Exception) -> None:
    timestamp = _utc_now()
    message = str(error)[:2000]
    with connect(db_path) as connection:
        migrate(connection)
        connection.execute(
            """
            UPDATE beacon_worker_runs
            SET state='failed',completed_at=?,error=?
            WHERE id=? AND state='running' AND worker_id=?
            """,
            (timestamp, message, claim.run_id, claim.worker_id),
        )
        record_event(
            connection,
            kind="beacon_conversation_worker",
            state="failed",
            message="Beacon could not answer a queued local conversation.",
            details={
                "run_id": claim.run_id,
                "thread_id": claim.thread_id,
                "error": message,
                "file_action_authorized": False,
            },
        )


def run_worker_once(
    db_path: Path,
    *,
    endpoint: str = "http://127.0.0.1:11434",
    model: str = "qwen2.5vl:7b",
    adapter: ConversationAdapter | None = None,
    worker_id: str | None = None,
) -> WorkerCycleResult:
    claim, state = claim_next_thread(
        db_path,
        endpoint=endpoint,
        model=model,
        worker_id=worker_id,
    )
    if claim is None:
        return WorkerCycleResult(state=state)
    selected_adapter = adapter or OllamaConversationAdapter(endpoint, model)
    try:
        detail = thread_detail(db_path, claim.thread_id)
        if detail is None:
            raise LookupError("Claimed Beacon conversation was not found.")
        history = _bounded_history(detail)
        plan = selected_adapter.plan(history)
        results = _grounded_search(db_path, plan.search_queries)
        response = selected_adapter.respond(history, results)
        message_id = _complete_claim(
            db_path,
            claim,
            response,
            results,
        )
        return WorkerCycleResult(
            state="complete",
            thread_id=claim.thread_id,
            message_id=message_id,
            result_count=len(results),
        )
    except Exception as error:
        _fail_claim(db_path, claim, error)
        return WorkerCycleResult(
            state="failed",
            thread_id=claim.thread_id,
            error=str(error),
        )
