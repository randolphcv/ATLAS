from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Protocol
from urllib.parse import urlparse

from .database import connect, migrate, record_event
from .desk import MESSAGE_LIMIT, _insert_result_cards, thread_detail
from .repository import search_assets

MAX_SEARCH_QUERIES = 4
MAX_RESULT_CARDS = 8
DEFAULT_RESULT_CARDS = 3
MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARACTERS = 24_000
DEFAULT_LEASE_SECONDS = 15 * 60
FAILURE_BACKOFF_SECONDS = 5 * 60
GENERIC_SEARCH_TERMS = frozenset(
    {
        "atlas",
        "beacon",
        "catalog",
        "library",
        "asset",
        "assets",
        "file",
        "files",
    }
)
MEDIA_EXTENSION_TERMS = frozenset(
    {
        "cr2", "cr3", "dng", "jpg", "jpeg", "png", "gif", "heic",
        "mov", "mp4", "m4v", "avi", "mkv", "wav", "mp3", "m4a", "flac",
    }
)
NO_SEARCH_PATTERNS = (
    r"\bdo not search\b",
    r"\bdon.t search\b",
    r"\bwithout (?:searching|a search)\b",
    r"\bno (?:catalog|library) search\b",
)
CORRECTION_PATTERNS = (
    *NO_SEARCH_PATTERNS,
    r"\bthat(?:'s| is) (?:not right|wrong|incorrect)\b",
    r"\bnot what i meant\b",
    r"\byou misunderstood\b",
    r"\bi meant\b",
    r"\bplease correct\b",
    r"\bonly (?:show|return|include|use)\b",
)


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
    search_mode: str = "catalog"
    max_results: int = DEFAULT_RESULT_CARDS


@dataclass(frozen=True)
class ConversationResponse:
    message: str
    used_references: tuple[int, ...] = ()


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
    ) -> ConversationResponse: ...


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
                "search_mode": {
                    "type": "string",
                    "enum": ["none", "catalog"],
                },
                "search_queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": MAX_SEARCH_QUERIES,
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": MAX_RESULT_CARDS,
                },
            },
            "required": ["search_mode", "search_queries", "max_results"],
        }
        result = self._chat_json(
            system=(
                "You are the planning boundary for Beacon's read-only local "
                "catalog. Search only when the latest human request requires "
                "catalog facts. An explicit request not to search means mode "
                "none. Return zero to four specific literal queries using "
                "names, places, projects, exact filenames, or visual concepts. "
                "Never use generic system words such as ATLAS, Beacon, catalog, "
                "library, file, or asset as queries. Default to at most three "
                "results unless the human asks for a collection or alternatives. "
                "Never propose a file operation."
            ),
            content=json.dumps({"conversation": messages}, ensure_ascii=False),
            schema=schema,
        )
        mode = str(result.get("search_mode") or "none").strip().casefold()
        queries = _normalize_queries(result.get("search_queries"))
        if mode != "catalog" or not queries:
            return ConversationPlan((), search_mode="none", max_results=0)
        try:
            max_results = int(result.get("max_results") or DEFAULT_RESULT_CARDS)
        except (TypeError, ValueError):
            max_results = DEFAULT_RESULT_CARDS
        return ConversationPlan(
            search_queries=queries,
            search_mode="catalog",
            max_results=max(1, min(max_results, MAX_RESULT_CARDS)),
        )

    def respond(
        self,
        messages: list[dict[str, str]],
        results: list[dict[str, Any]],
    ) -> ConversationResponse:
        schema = {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "used_references": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "maxItems": MAX_RESULT_CARDS,
                },
            },
            "required": ["message", "used_references"],
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
                "or modified a file. Return used_references containing only "
                "evidence actually used in the answer. Return an empty list "
                "when the answer uses no catalog evidence. Result cards let "
                "the human inspect those cited assets."
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
        references = _normalize_references(
            result.get("used_references"),
            result_count=len(results),
            message=message,
        )
        return ConversationResponse(message, references)


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


def _normalize_references(
    value: object,
    *,
    result_count: int,
    message: str,
) -> tuple[int, ...]:
    candidates: list[object] = list(value) if isinstance(value, list) else []
    candidates.extend(re.findall(r"\[(\d+)\]", message))
    references: list[int] = []
    for candidate in candidates:
        try:
            reference = int(candidate)
        except (TypeError, ValueError):
            continue
        if 1 <= reference <= result_count and reference not in references:
            references.append(reference)
    return tuple(references[:MAX_RESULT_CARDS])


def _latest_human_body(messages: list[dict[str, str]]) -> str:
    for message in reversed(messages):
        if str(message.get("author") or "").casefold() == "human":
            return str(message.get("body") or "")
    return ""


def _explicit_no_search(body: str) -> bool:
    folded = body.casefold()
    return any(re.search(pattern, folded) for pattern in NO_SEARCH_PATTERNS)


def _wants_collection(body: str) -> bool:
    return bool(
        re.search(
            r"\b(all|every|collection|alternatives?|similar|related|"
            r"other|several|multiple)\b",
            body.casefold(),
        )
    )


def _exact_filename(body: str) -> str | None:
    matches = re.findall(
        r"(?i)\b([a-z0-9][a-z0-9_.()-]*\.[a-z0-9]{1,10})\b",
        body,
    )
    return matches[-1] if matches else None


def _explicit_retrieval_plan(body: str) -> ConversationPlan | None:
    match = re.search(
        r"(?i)\b(?:find|show|locate|pull up|retrieve|get)\s+"
        r"(?:me\s+)?(?:all\s+|some\s+|an?\s+|the\s+)?"
        r"(?:images?|photos?|pictures?|videos?|clips?|audio|files?|assets?)"
        r"(?:\s+of|\s+for)?\s+(.+?)(?:[.?!]|$)",
        body,
    )
    if match is None:
        return None
    target = " ".join(match.group(1).strip(" \"'").split())
    if not target:
        return None
    terms = tuple(
        part.strip()
        for part in re.split(r"\s+(?:and|&)\s+", target, flags=re.IGNORECASE)
        if part.strip()
    )
    max_results = (
        MAX_RESULT_CARDS if _wants_collection(body) else DEFAULT_RESULT_CARDS
    )
    if 2 <= len(terms) <= MAX_SEARCH_QUERIES:
        return ConversationPlan(
            terms,
            search_mode="all_terms",
            max_results=max_results,
        )
    return ConversationPlan(
        (target,),
        search_mode="catalog",
        max_results=max_results,
    )


def _apply_search_policy(
    plan: ConversationPlan,
    messages: list[dict[str, str]],
) -> ConversationPlan:
    latest = _latest_human_body(messages)
    if _explicit_no_search(latest):
        return ConversationPlan((), search_mode="none", max_results=0)
    filename = _exact_filename(latest)
    if filename and not _wants_collection(latest):
        return ConversationPlan(
            (filename,),
            search_mode="exact_filename",
            max_results=1,
        )
    wants_collection = _wants_collection(latest)
    accepted: list[str] = []
    for query in plan.search_queries:
        key = query.casefold().strip().lstrip(".")
        if key in GENERIC_SEARCH_TERMS:
            continue
        if key in MEDIA_EXTENSION_TERMS and not (
            wants_collection and key in latest.casefold()
        ):
            continue
        accepted.append(query)
    if plan.search_mode == "none" or not accepted:
        return ConversationPlan((), search_mode="none", max_results=0)
    ceiling = MAX_RESULT_CARDS if wants_collection else DEFAULT_RESULT_CARDS
    return ConversationPlan(
        tuple(accepted[:MAX_SEARCH_QUERIES]),
        search_mode="catalog",
        max_results=max(1, min(plan.max_results, ceiling)),
    )


def _forced_search_plan(
    messages: list[dict[str, str]],
) -> ConversationPlan | None:
    latest = _latest_human_body(messages)
    if _explicit_no_search(latest):
        return ConversationPlan((), search_mode="none", max_results=0)
    filename = _exact_filename(latest)
    if filename and not _wants_collection(latest):
        return ConversationPlan(
            (filename,),
            search_mode="exact_filename",
            max_results=1,
        )
    retrieval = _explicit_retrieval_plan(latest)
    if retrieval is not None:
        return retrieval
    return None


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


def _is_explicit_correction(body: str) -> bool:
    folded = body.casefold()
    return any(re.search(pattern, folded) for pattern in CORRECTION_PATTERNS)


def _record_and_load_corrections(
    db_path: Path,
    detail: dict[str, Any],
) -> list[str]:
    messages = detail.get("messages") or []
    if len(messages) >= 2:
        latest = messages[-1]
        prior = messages[-2]
        note = " ".join(str(latest.get("body") or "").split())[:2000]
        if (
            latest.get("author") == "human"
            and prior.get("author") == "beacon"
            and note
            and _is_explicit_correction(note)
        ):
            with connect(db_path) as connection:
                migrate(connection)
                inserted = connection.execute(
                    """
                    INSERT OR IGNORE INTO beacon_conversation_feedback(
                        id,thread_id,human_message_id,prior_beacon_message_id,
                        kind,note,created_at
                    ) VALUES (?, ?, ?, ?, 'correction', ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        detail["id"],
                        latest["id"],
                        prior["id"],
                        note,
                        _utc_now(),
                    ),
                )
                if inserted.rowcount:
                    record_event(
                        connection,
                        kind="beacon_conversation_feedback",
                        state="complete",
                        message="Beacon retained an explicit human correction.",
                        details={
                            "thread_id": detail["id"],
                            "human_message_id": latest["id"],
                            "scope": "thread",
                        },
                    )
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            """
            SELECT note FROM beacon_conversation_feedback
            WHERE thread_id=? ORDER BY created_at DESC LIMIT 8
            """,
            (detail["id"],),
        ).fetchall()
    return [str(row["note"]) for row in reversed(rows)]


def _history_with_corrections(
    history: list[dict[str, str]],
    corrections: list[str],
) -> list[dict[str, str]]:
    if not corrections:
        return history
    durable = "\n".join(f"- {note}" for note in corrections)
    return [
        {
            "author": "system",
            "body": (
                "Thread-scoped human corrections retained from earlier "
                f"misunderstandings:\n{durable}"
            ),
        },
        *history,
    ]


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
    plan: ConversationPlan,
) -> list[dict[str, Any]]:
    matches: dict[str, dict[str, Any]] = {}
    reasons: dict[str, list[str]] = {}
    matched_queries: dict[str, set[str]] = {}
    if plan.search_mode == "none" or not plan.search_queries:
        return []
    for query in plan.search_queries:
        page = search_assets(
            db_path,
            query=query,
            limit=max(12, plan.max_results * 4),
        )
        for item in page["items"]:
            path = str(item.get("primary_path") or "")
            if _is_nonproduction_path(path):
                continue
            if (
                plan.search_mode == "exact_filename"
                and PureWindowsPath(path).name.casefold() != query.casefold()
            ):
                continue
            asset_id = str(item["id"])
            matches.setdefault(asset_id, item)
            reasons.setdefault(asset_id, []).append(
                _catalog_match_reason(db_path, item, query)
            )
            matched_queries.setdefault(asset_id, set()).add(query.casefold())
            if (
                plan.search_mode == "exact_filename"
                and len(matches) >= plan.max_results
            ):
                break
        if (
            plan.search_mode == "exact_filename"
            and len(matches) >= plan.max_results
        ):
            break
    grounded: list[dict[str, Any]] = []
    ordered_ids = sorted(
        matches,
        key=lambda asset_id: -len(matched_queries.get(asset_id, set())),
    )
    if plan.search_mode == "all_terms":
        required = {query.casefold() for query in plan.search_queries}
        ordered_ids = [
            asset_id
            for asset_id in ordered_ids
            if matched_queries.get(asset_id, set()) >= required
        ]
    for asset_id in ordered_ids[:plan.max_results]:
        item = matches[asset_id]
        path = str(item.get("primary_path") or "")
        grounded.append(
            {
                **item,
                "match_reason": "; ".join(reasons[asset_id]),
                "available": bool(path and Path(path).exists()),
            }
        )
    return grounded


def _is_nonproduction_path(path: str) -> bool:
    normalized = path.replace("/", "\\").casefold()
    return (
        "\\programdata\\atlas\\beacon\\use-tests\\" in normalized
        or "\\programdata\\atlas\\beacon\\sandbox\\" in normalized
    )


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
        corrections = _record_and_load_corrections(db_path, detail)
        grounded_history = _history_with_corrections(history, corrections)
        plan = _forced_search_plan(grounded_history)
        if plan is None:
            plan = _apply_search_policy(
                selected_adapter.plan(grounded_history),
                grounded_history,
            )
        results = _grounded_search(db_path, plan)
        response = selected_adapter.respond(grounded_history, results)
        selected_results = [
            results[reference - 1]
            for reference in response.used_references
            if 1 <= reference <= len(results)
        ]
        message_id = _complete_claim(
            db_path,
            claim,
            response.message,
            selected_results,
        )
        return WorkerCycleResult(
            state="complete",
            thread_id=claim.thread_id,
            message_id=message_id,
            result_count=len(selected_results),
        )
    except Exception as error:
        _fail_claim(db_path, claim, error)
        return WorkerCycleResult(
            state="failed",
            thread_id=claim.thread_id,
            error=str(error),
        )
