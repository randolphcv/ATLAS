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
from .repository import asset_detail, search_assets

MAX_AGENT_STEPS = 6
MAX_SEARCH_QUERIES = 6
MAX_RESULT_CARDS = 8
MAX_SEARCH_RESULTS = 16
MAX_INSPECT_ASSETS = 8
MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARACTERS = 20_000
MAX_AGENT_CONTEXT_CHARACTERS = 42_000
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
class AgentAction:
    action: str
    queries: tuple[str, ...] = ()
    match_strategy: str = "any"
    media_type: str = "all"
    result_limit: int = 8
    asset_ids: tuple[str, ...] = ()
    message: str = ""
    selected_asset_ids: tuple[str, ...] = ()
    decision_summary: str = ""


@dataclass(frozen=True)
class AgentGoal:
    request_summary: str
    requires_catalog_evidence: bool
    requested_result_count: int = 0
    media_type: str = "all"
    constraints: tuple[str, ...] = ()
    latest_human_corrects_beacon: bool = False


@dataclass(frozen=True)
class AgentResponse:
    message: str
    selected_asset_ids: tuple[str, ...] = ()
    request_fully_satisfied: bool = False


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
    def understand(self, messages: list[dict[str, str]]) -> AgentGoal: ...

    def decide(
        self,
        goal: AgentGoal,
        messages: list[dict[str, str]],
        observations: list[dict[str, Any]],
        available_assets: list[dict[str, Any]],
    ) -> AgentAction: ...

    def compose(
        self,
        goal: AgentGoal,
        messages: list[dict[str, str]],
        available_assets: list[dict[str, Any]],
        draft: AgentAction,
    ) -> AgentResponse: ...


class OllamaConversationAdapter:
    """Loopback-only agent adapter with bounded, read-only catalog tools."""

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
        last_error: Exception | None = None
        for attempt in range(2):
            retry_instruction = (
                "\n\nYour prior structured output was invalid or incomplete. "
                "Retry concisely and return one complete JSON object matching "
                "the schema."
                if attempt
                else ""
            )
            payload = json.dumps(
                {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": f"{system}{retry_instruction}",
                        },
                        {"role": "user", "content": content},
                    ],
                    "format": schema,
                    "stream": False,
                    "options": {
                        "temperature": 0,
                        "num_predict": 1800,
                        "num_ctx": 16384,
                    },
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
                message = outer.get("message")
                if not isinstance(message, dict):
                    raise ValueError(
                        "Local conversation model returned no message."
                    )
                content_value = message.get("content")
                if not isinstance(content_value, str):
                    raise ValueError(
                        "Local conversation model returned invalid content."
                    )
                result = json.loads(content_value)
                if not isinstance(result, dict):
                    raise ValueError(
                        "Local conversation model result is not an object."
                    )
                return result
            except (
                OSError,
                urllib.error.URLError,
                json.JSONDecodeError,
                ValueError,
            ) as error:
                last_error = error
        raise RuntimeError(
            f"Local Beacon conversation model returned invalid structured "
            f"output after retry: {last_error}"
        ) from last_error

    def understand(self, messages: list[dict[str, str]]) -> AgentGoal:
        schema = {
            "type": "object",
            "properties": {
                "request_summary": {"type": "string"},
                "requires_catalog_evidence": {"type": "boolean"},
                "requested_result_count": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": MAX_RESULT_CARDS,
                },
                "media_type": {
                    "type": "string",
                    "enum": ["all", "photo", "video", "audio", "other"],
                },
                "constraints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 8,
                },
                "latest_human_corrects_beacon": {"type": "boolean"},
            },
            "required": [
                "request_summary",
                "requires_catalog_evidence",
                "requested_result_count",
                "media_type",
                "constraints",
                "latest_human_corrects_beacon",
            ],
        }
        result = self._chat_json(
            system=(
                "You are Beacon's reasoning model. Formalize only the active "
                "latest_human_request supplied to you. prior_conversation is "
                "context for resolving follow-ups and references; do not repeat "
                "or combine a prior request that Beacon already answered unless "
                "the latest human explicitly asks for it again. Preserve explicit count, "
                "media kind, names, exact filenames, scope, exclusions, and "
                "quality requirements. Map images/photos/pictures to photo; map "
                "videos/clips/footage to video; use all only when no media kind "
                "is requested. requested_result_count is the explicit count, or "
                "0 when no count was stated. Put requirements such as unique, "
                "different, exact, oldest, or excluding something into "
                "constraints in operational language. A request to find, show, "
                "retrieve, compare, or answer about local assets requires catalog "
                "evidence. requires_catalog_evidence is false only for ordinary "
                "conversation or when the latest human explicitly says not to "
                "search. A follow-up can be a new request. Mark "
                "latest_human_corrects_beacon true only when that latest turn "
                "actually says or clearly implies Beacon's prior answer was "
                "mistaken—not merely because a Beacon turn precedes it. Summarize "
                "the goal without proposing an answer or inventing catalog facts."
            ),
            content=json.dumps(
                _active_request_context(messages),
                ensure_ascii=False,
            ),
            schema=schema,
        )
        media_type = str(result.get("media_type") or "all").casefold()
        if media_type not in {"all", "photo", "video", "audio", "other"}:
            media_type = "all"
        try:
            count = int(result.get("requested_result_count") or 0)
        except (TypeError, ValueError):
            count = 0
        summary = " ".join(
            str(result.get("request_summary") or "").split()
        )[:1000]
        if not summary:
            raise ValueError("Local conversation model returned no request goal.")
        return AgentGoal(
            request_summary=summary,
            requires_catalog_evidence=bool(
                result.get("requires_catalog_evidence")
            ),
            requested_result_count=max(0, min(count, MAX_RESULT_CARDS)),
            media_type=media_type,
            constraints=_normalize_strings(
                result.get("constraints"),
                maximum=8,
                item_limit=240,
            ),
            latest_human_corrects_beacon=bool(
                result.get("latest_human_corrects_beacon")
            ),
        )

    def decide(
        self,
        goal: AgentGoal,
        messages: list[dict[str, str]],
        observations: list[dict[str, Any]],
        available_assets: list[dict[str, Any]],
    ) -> AgentAction:
        schema = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search_catalog", "inspect_assets", "respond"],
                },
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": MAX_SEARCH_QUERIES,
                },
                "match_strategy": {
                    "type": "string",
                    "enum": ["any", "all"],
                },
                "media_type": {
                    "type": "string",
                    "enum": ["all", "photo", "video", "audio", "other"],
                },
                "result_limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_SEARCH_RESULTS,
                },
                "asset_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": MAX_INSPECT_ASSETS,
                },
            },
            "required": ["action"],
        }
        result = self._chat_json(
            system=(
                "You are Beacon, an agentic local archive partner with a warm, "
                "capable personality. Another reasoning pass by you has already "
                "formalized the human's current goal. Treat that goal as stable "
                "throughout this tool loop: do not change its requested media "
                "type, count, or constraints. You can iteratively use "
                "search_catalog and inspect_assets before responding.\n\n"
                "Available actions:\n"
                "- search_catalog: choose one or more useful literal search "
                "queries, a media_type, an any/all match strategy, and a result "
                "limit. With any matching, result_limit is the candidate depth "
                "per query and the tool interleaves those query buckets (up to "
                f"{MAX_SEARCH_RESULTS} total); with all matching, it is the total "
                "limit. If the first wording is sparse, reason about synonyms, "
                "related visual concepts, places, people, projects, filenames, "
                "or likely metadata and search again. Search queries should be "
                "concepts likely to exist in catalog metadata; do not search for "
                "instruction words such as unique, different, best, exactly, or "
                "a requested count. Use all when every query must describe the "
                "same asset; use any to explore alternatives. For this action, "
                "return queries, match_strategy, media_type, and result_limit; "
                "omit message, selected_asset_ids, and asset_ids.\n"
                "- inspect_assets: choose IDs already returned by search when "
                "you need richer contextual analysis, descriptions, people, "
                "transcripts, or other metadata to judge relevance or diversity. "
                "For this action, return asset_ids and omit search/response fields.\n"
                "- respond: answer naturally. selected_asset_ids must contain "
                "indicates that you have enough evidence to compose the answer "
                "or need to ask the human a focused question. A separate focused "
                "Qwen composition pass will write and ground the final answer. "
                "For this action, omit search and inspection fields.\n\n"
                "If requires_catalog_evidence is false, respond without a catalog "
                "tool. Otherwise, use catalog evidence before making catalog "
                "claims. Honor explicit instructions, including no-search. "
                "Treat exact filenames as exact retrieval goals unless context "
                "says otherwise. For 'unique', 'distinct', or 'different' "
                "results, retrieve a larger candidate pool than the requested "
                "count, inspect candidates when their summaries could belong to "
                "one burst/series, and choose meaningfully different scenes or "
                "subjects. Similar filenames, near-identical titles, or adjacent "
                "variations of one setup are not meaningfully unique. If the "
                "first candidates are too similar, broaden the concepts and "
                "search again. For example, a request for three distinct food "
                "images should search useful catalog concepts such as food, "
                "meal, cooking, dessert, or dining with an exploratory pool "
                "larger than three; it should not search for the word unique "
                "or accept three adjacent variations of the same dish. "
                "Conversation context matters: pronouns and follow-ups "
                "refer to prior turns when logic supports that reading.\n\n"
                "Catalog tools are read-only. Never claim you copied, moved, "
                "shared, opened, deleted, or modified anything. Never invent "
                "catalog facts or asset IDs."
            ),
            content=_bounded_agent_payload(
                {
                    "stable_goal": {
                        "request_summary": goal.request_summary,
                        "requires_catalog_evidence": (
                            goal.requires_catalog_evidence
                        ),
                        "requested_result_count": goal.requested_result_count,
                        "media_type": goal.media_type,
                        "constraints": list(goal.constraints),
                    },
                    "conversation": messages,
                    "tool_observations": observations,
                    "available_assets": available_assets,
                }
            ),
            schema=schema,
        )
        action = str(result.get("action") or "").strip().casefold()
        if action not in {"search_catalog", "inspect_assets", "respond"}:
            raise ValueError("Local conversation model returned an invalid action.")
        queries = _normalize_strings(
            result.get("queries"),
            maximum=MAX_SEARCH_QUERIES,
            item_limit=120,
        )
        asset_ids = _normalize_strings(
            result.get("asset_ids"),
            maximum=MAX_INSPECT_ASSETS,
            item_limit=80,
        )
        selected_asset_ids = _normalize_strings(
            result.get("selected_asset_ids"),
            maximum=MAX_RESULT_CARDS,
            item_limit=80,
        )
        message = str(result.get("message") or "").strip()
        # Repair a structurally inconsistent tool envelope using only the
        # model-supplied action arguments. This does not reinterpret the human
        # request: Qwen's own populated argument set identifies the intended tool.
        if action == "search_catalog" and not queries and asset_ids:
            action = "inspect_assets"
        elif (
            action in {"search_catalog", "inspect_assets"}
            and message
            and selected_asset_ids
        ):
            action = "respond"
        try:
            result_limit = int(result.get("result_limit") or 8)
        except (TypeError, ValueError):
            result_limit = 8
        return AgentAction(
            action=action,
            queries=queries,
            match_strategy=(
                "all"
                if str(result.get("match_strategy")).casefold() == "all"
                else "any"
            ),
            media_type=(
                str(result.get("media_type")).casefold()
                if str(result.get("media_type")).casefold()
                in {"all", "photo", "video", "audio", "other"}
                else "all"
            ),
            result_limit=max(1, min(result_limit, MAX_SEARCH_RESULTS)),
            asset_ids=asset_ids,
            message=message,
            selected_asset_ids=selected_asset_ids,
            decision_summary=" ".join(
                str(result.get("decision_summary") or "").split()
            )[:500],
        )

    def compose(
        self,
        goal: AgentGoal,
        messages: list[dict[str, str]],
        available_assets: list[dict[str, Any]],
        draft: AgentAction,
    ) -> AgentResponse:
        schema = {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "selected_asset_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": MAX_RESULT_CARDS,
                },
                "request_fully_satisfied": {"type": "boolean"},
            },
            "required": [
                "message",
                "selected_asset_ids",
                "request_fully_satisfied",
            ],
        }
        result = self._chat_json(
            system=(
                "You are Beacon, a capable local archive partner. Compose the "
                "final natural answer for the stable model-authored goal using "
                "only the available_assets. Return a non-empty message and the "
                "exact asset IDs that materially support it. When an explicit "
                "result count is requested and enough qualifying assets exist, "
                "select exactly that many—never extras. Honor all constraints. "
                "For unique/distinct results, select meaningfully different "
                "scenes or subjects; avoid adjacent filenames, near-identical "
                "titles, and variations of one setup. potential_series_hint is "
                "a filename/path-based caution that nearby captures may belong "
                "to one series; choose at most one asset with the same hint for "
                "a uniqueness request unless the metadata clearly proves the "
                "scenes are meaningfully different. If evidence is genuinely "
                "insufficient, say what is missing and ask one focused question "
                "or offer a useful broadened option and set "
                "request_fully_satisfied false. Set it true only when the "
                "response meets the full count and every constraint. Do not invent assets or "
                "claim any file operation. Do not print raw asset IDs or ATLAS "
                "URIs in the prose; the attached result cards provide those."
            ),
            content=_bounded_agent_payload(
                {
                    "stable_goal": {
                        "request_summary": goal.request_summary,
                        "requested_result_count": goal.requested_result_count,
                        "media_type": goal.media_type,
                        "constraints": list(goal.constraints),
                    },
                    "conversation": messages,
                    "available_assets": available_assets,
                    "agent_readiness_summary": draft.decision_summary,
                }
            ),
            schema=schema,
        )
        message = str(result.get("message") or "").strip()
        if not message:
            raise ValueError(
                "Local conversation model returned an empty final response."
            )
        return AgentResponse(
            message=message,
            selected_asset_ids=_normalize_strings(
                result.get("selected_asset_ids"),
                maximum=MAX_RESULT_CARDS,
                item_limit=80,
            ),
            request_fully_satisfied=bool(
                result.get("request_fully_satisfied")
            ),
        )


def _bounded_agent_payload(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False)
    if len(payload) <= MAX_AGENT_CONTEXT_CHARACTERS:
        return payload
    trimmed = {
        **value,
        "tool_observations": list(value.get("tool_observations") or []),
        "available_assets": [
            dict(item) for item in value.get("available_assets") or []
        ],
    }
    observations = list(trimmed.get("tool_observations") or [])
    while observations and len(
        json.dumps({**trimmed, "tool_observations": observations}, ensure_ascii=False)
    ) > MAX_AGENT_CONTEXT_CHARACTERS:
        observations.pop(0)
    trimmed["tool_observations"] = observations
    payload = json.dumps(trimmed, ensure_ascii=False)
    if len(payload) <= MAX_AGENT_CONTEXT_CHARACTERS:
        return payload
    for item in trimmed["available_assets"]:
        if not item.get("inspection"):
            item.pop("editable_metadata", None)
    payload = json.dumps(trimmed, ensure_ascii=False)
    if len(payload) <= MAX_AGENT_CONTEXT_CHARACTERS:
        return payload
    for item in trimmed["available_assets"]:
        item.pop("editable_metadata", None)
        inspection = item.get("inspection")
        if isinstance(inspection, dict):
            item["inspection"] = _compact_json(inspection, limit=1800)
    # Always return valid JSON. The compact fallback keeps every observed asset
    # ID available for grounding even when rich evidence exceeds the soft cap.
    return json.dumps(trimmed, ensure_ascii=False)


def _normalize_strings(
    value: object,
    *,
    maximum: int,
    item_limit: int,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    values: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = " ".join(str(item).split()).strip()
        key = normalized.casefold()
        if not normalized or len(normalized) > item_limit or key in seen:
            continue
        seen.add(key)
        values.append(normalized)
        if len(values) >= maximum:
            break
    return tuple(values)


def _active_request_context(
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    latest_index = -1
    for index in range(len(messages) - 1, -1, -1):
        if str(messages[index].get("author") or "").casefold() == "human":
            latest_index = index
            break
    if latest_index < 0:
        return {
            "prior_conversation": messages,
            "latest_human_request": "",
        }
    return {
        "prior_conversation": messages[:latest_index],
        "latest_human_request": str(
            messages[latest_index].get("body") or ""
        ),
    }


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


def _load_corrections(
    db_path: Path,
    detail: dict[str, Any],
) -> list[str]:
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


def _record_latest_correction(
    db_path: Path,
    detail: dict[str, Any],
) -> None:
    messages = detail.get("messages") or []
    if len(messages) < 2:
        return
    latest = messages[-1]
    prior = messages[-2]
    note = " ".join(str(latest.get("body") or "").split())[:2000]
    if (
        latest.get("author") != "human"
        or prior.get("author") != "beacon"
        or not note
    ):
        return
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
                message="Beacon retained a model-identified human correction.",
                details={
                    "thread_id": detail["id"],
                    "human_message_id": latest["id"],
                    "scope": "thread",
                    "identified_by": "conversation_model",
                },
            )


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


def _search_catalog_tool(
    db_path: Path,
    action: AgentAction,
) -> list[dict[str, Any]]:
    matches: dict[str, dict[str, Any]] = {}
    reasons: dict[str, list[str]] = {}
    matched_queries: dict[str, set[str]] = {}
    query_result_ids: dict[str, list[str]] = {}
    for query in action.queries:
        query_key = query.casefold()
        query_result_ids[query_key] = []
        page = search_assets(
            db_path,
            query=query,
            file_type=action.media_type,
            limit=max(20, action.result_limit * 4),
        )
        for item in page["items"]:
            path = str(item.get("primary_path") or "")
            if _is_nonproduction_path(path):
                continue
            asset_id = str(item["id"])
            matches.setdefault(asset_id, item)
            query_result_ids[query_key].append(asset_id)
            reasons.setdefault(asset_id, []).append(
                _catalog_match_reason(db_path, item, query)
            )
            matched_queries.setdefault(asset_id, set()).add(query_key)
    grounded: list[dict[str, Any]] = []
    required = {query.casefold() for query in action.queries}
    if action.match_strategy == "all":
        ordered_ids = [
            asset_id
            for asset_id in matches
            if matched_queries.get(asset_id, set()) >= required
        ]
        ordered_ids.sort(
            key=lambda asset_id: _search_rank(
                matches[asset_id],
                action.queries,
                matched_queries.get(asset_id, set()),
            ),
            reverse=True,
        )
    else:
        ordered_ids = []
        largest = max(
            (len(asset_ids) for asset_ids in query_result_ids.values()),
            default=0,
        )
        for position in range(largest):
            for query in action.queries:
                asset_ids = query_result_ids.get(query.casefold(), [])
                if position >= len(asset_ids):
                    continue
                asset_id = asset_ids[position]
                if asset_id not in ordered_ids:
                    ordered_ids.append(asset_id)
        ordered_ids = _interleave_candidate_series(ordered_ids, matches)
    tool_limit = (
        action.result_limit
        if action.match_strategy == "all"
        else min(
            MAX_SEARCH_RESULTS,
            action.result_limit * max(1, len(action.queries)),
        )
    )
    for asset_id in ordered_ids[:tool_limit]:
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


def _search_rank(
    item: dict[str, Any],
    queries: tuple[str, ...],
    matched_queries: set[str],
) -> tuple[int, int, int]:
    filename = str(item.get("filename") or "").casefold()
    metadata = item.get("editable_metadata") or {}
    title = str(metadata.get("display_title") or "").casefold()
    exact = sum(
        1 for query in queries if query.casefold() in {filename, title}
    )
    phrase = sum(
        1
        for query in queries
        if query.casefold() in filename or query.casefold() in title
    )
    return len(matched_queries), exact, phrase


def _candidate_series_hint(item: dict[str, Any]) -> str:
    path = str(item.get("primary_path") or "")
    filename = Path(path).stem
    digit_start = len(filename)
    while digit_start > 0 and filename[digit_start - 1].isdigit():
        digit_start -= 1
    digits = filename[digit_start:]
    if len(digits) < 2:
        return f"single:{item['id']}"
    prefix = filename[:digit_start]
    numeric_family = f"{digits[:-1]}x"
    parent = str(Path(path).parent).casefold()
    return f"{parent}|{prefix.casefold()}{numeric_family}"


def _interleave_candidate_series(
    ordered_ids: list[str],
    matches: dict[str, dict[str, Any]],
) -> list[str]:
    buckets: dict[str, list[str]] = {}
    for asset_id in ordered_ids:
        hint = _candidate_series_hint(matches[asset_id])
        buckets.setdefault(hint, []).append(asset_id)
    diversified: list[str] = []
    largest = max((len(bucket) for bucket in buckets.values()), default=0)
    for position in range(largest):
        for bucket in buckets.values():
            if position < len(bucket):
                diversified.append(bucket[position])
    return diversified


def _compact_json(value: object, *, limit: int) -> object:
    if value in (None, "", [], {}):
        return value
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded) <= limit:
        return value
    return f"{encoded[:limit]}…"


def _agent_asset_summary(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("editable_metadata") or {}
    result: dict[str, Any] = {
        "asset_id": item["id"],
        "atlas_uri": item["atlas_uri"],
        "title": metadata.get("display_title") or item.get("filename"),
        "filename": item.get("filename"),
        "path": item.get("primary_path"),
        "kind": item.get("kind"),
        "dimensions": item.get("dimensions"),
        "duration_seconds": item.get("duration_seconds"),
        "available": bool(item.get("available")),
        "match_reason": item.get("match_reason"),
        "potential_series_hint": _candidate_series_hint(item),
        "editable_metadata": _compact_json(metadata, limit=1000),
    }
    if item.get("inspection"):
        result["inspection"] = item["inspection"]
    return result


def _inspect_asset_tool(db_path: Path, item: dict[str, Any]) -> dict[str, Any]:
    detail = asset_detail(db_path, str(item["id"]))
    if detail is None:
        return {"asset_id": item["id"], "error": "Asset no longer exists."}
    analyses = []
    for analysis in detail.get("analysis") or []:
        if analysis.get("review_state") not in {"candidate", "approved"}:
            continue
        analyses.append(
            {
                "kind": analysis.get("analysis_kind"),
                "confidence": analysis.get("confidence"),
                "review_state": analysis.get("review_state"),
                "payload": _compact_json(analysis.get("payload"), limit=1800),
            }
        )
        if len(analyses) >= 2:
            break
    transcript = detail.get("transcript") or {}
    text = " ".join(str(transcript.get("text") or "").split())
    return {
        "asset_id": detail["id"],
        "editable_metadata": _compact_json(
            detail.get("editable_metadata") or {},
            limit=1400,
        ),
        "contextual_analysis": analyses,
        "transcript_excerpt": (
            f"{text[:1000]}…" if len(text) > 1000 else text
        ),
        "music_analysis": _compact_json(
            detail.get("music_analysis") or {},
            limit=800,
        ),
    }


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


def _record_agent_step(
    db_path: Path,
    claim: WorkerClaim,
    *,
    step: int,
    action: AgentAction,
    state: str,
    result_ids: list[str] | None = None,
    error: str | None = None,
) -> None:
    with connect(db_path) as connection:
        migrate(connection)
        record_event(
            connection,
            kind="beacon_conversation_agent",
            state=state,
            message=(
                f"Beacon agent step {step}: {action.action}."
                if not error
                else f"Beacon agent step {step} could not use {action.action}."
            ),
            details={
                "run_id": claim.run_id,
                "thread_id": claim.thread_id,
                "step": step,
                "action": action.action,
                "queries": list(action.queries),
                "match_strategy": action.match_strategy,
                "media_type": action.media_type,
                "requested_asset_ids": list(action.asset_ids),
                "selected_asset_ids": list(action.selected_asset_ids),
                "result_asset_ids": result_ids or [],
                "decision_summary": action.decision_summary,
                "error": error,
                "file_action_authorized": False,
            },
        )


def _run_agent_session(
    db_path: Path,
    claim: WorkerClaim,
    detail: dict[str, Any],
    adapter: ConversationAdapter,
) -> tuple[str, list[dict[str, Any]]]:
    history = _bounded_history(detail)
    corrections = _load_corrections(db_path, detail)
    grounded_history = _history_with_corrections(history, corrections)
    goal = adapter.understand(grounded_history)
    if goal.latest_human_corrects_beacon:
        _record_latest_correction(db_path, detail)
    observations: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}

    for step in range(1, MAX_AGENT_STEPS + 1):
        available = [_agent_asset_summary(item) for item in seen.values()]
        action = adapter.decide(
            goal,
            grounded_history,
            observations,
            available,
        )

        if action.action == "search_catalog":
            if not goal.requires_catalog_evidence:
                error = (
                    "search_catalog conflicts with the model-authored goal, "
                    "which says catalog evidence is not required."
                )
            elif (
                goal.media_type != "all"
                and action.media_type != goal.media_type
            ):
                error = (
                    f"search_catalog media_type {action.media_type!r} conflicts "
                    f"with the stable goal media_type {goal.media_type!r}."
                )
            elif not action.queries:
                error = "search_catalog requires at least one query."
            else:
                error = ""
            if error:
                observations.append(
                    {"step": step, "tool": action.action, "error": error}
                )
                _record_agent_step(
                    db_path,
                    claim,
                    step=step,
                    action=action,
                    state="failed",
                    error=error,
                )
                continue
            results = _search_catalog_tool(db_path, action)
            for item in results:
                asset_id = str(item["id"])
                previous = seen.get(asset_id)
                if previous and previous.get("inspection"):
                    item["inspection"] = previous["inspection"]
                seen[asset_id] = item
            summaries = [_agent_asset_summary(item) for item in results]
            observations.append(
                {
                    "step": step,
                    "tool": action.action,
                    "input": {
                        "queries": list(action.queries),
                        "match_strategy": action.match_strategy,
                        "media_type": action.media_type,
                        "result_limit": action.result_limit,
                    },
                    "returned_count": len(summaries),
                    "result_asset_ids": [
                        item["asset_id"] for item in summaries
                    ],
                }
            )
            _record_agent_step(
                db_path,
                claim,
                step=step,
                action=action,
                state="complete",
                result_ids=[str(item["id"]) for item in results],
            )
            continue

        if action.action == "inspect_assets":
            requested = [
                asset_id for asset_id in action.asset_ids if asset_id in seen
            ]
            unknown = [
                asset_id for asset_id in action.asset_ids if asset_id not in seen
            ]
            if not requested:
                error = (
                    "inspect_assets requires asset IDs previously returned by "
                    "search_catalog."
                )
                observations.append(
                    {
                        "step": step,
                        "tool": action.action,
                        "error": error,
                        "unknown_asset_ids": unknown,
                    }
                )
                _record_agent_step(
                    db_path,
                    claim,
                    step=step,
                    action=action,
                    state="failed",
                    error=error,
                )
                continue
            inspected = []
            for asset_id in requested:
                inspection = _inspect_asset_tool(db_path, seen[asset_id])
                seen[asset_id]["inspection"] = inspection
                inspected.append(inspection)
            observations.append(
                {
                    "step": step,
                    "tool": action.action,
                    "inspected_asset_ids": [
                        item["asset_id"] for item in inspected
                    ],
                    "unknown_asset_ids": unknown,
                }
            )
            _record_agent_step(
                db_path,
                claim,
                step=step,
                action=action,
                state="complete",
                result_ids=requested,
            )
            continue

        if action.action == "respond":
            response = adapter.compose(
                goal,
                grounded_history,
                available,
                action,
            )
            if len(response.message) > MESSAGE_LIMIT:
                error = "Response exceeds the Beacon Desk message limit."
            else:
                unknown = [
                    asset_id
                    for asset_id in response.selected_asset_ids
                    if asset_id not in seen
                ]
                error = (
                    "respond selected assets that were not observed through "
                    f"catalog tools: {', '.join(unknown)}"
                    if unknown
                    else ""
                )
                if (
                    not error
                    and goal.requested_result_count
                    and response.request_fully_satisfied
                    and len(response.selected_asset_ids)
                    != goal.requested_result_count
                ):
                    error = (
                        "The model marked the request fully satisfied without "
                        "selecting the model-authored result count "
                        f"({goal.requested_result_count})."
                    )
                elif (
                    not error
                    and goal.requested_result_count
                    and len(response.selected_asset_ids)
                    > goal.requested_result_count
                ):
                    error = (
                        "respond selected more assets than the model-authored "
                        f"goal permits ({goal.requested_result_count})."
                    )
            if error:
                observations.append(
                    {"step": step, "tool": action.action, "error": error}
                )
                _record_agent_step(
                    db_path,
                    claim,
                    step=step,
                    action=action,
                    state="failed",
                    error=error,
                )
                continue
            selected = [
                seen[asset_id] for asset_id in response.selected_asset_ids
            ]
            _record_agent_step(
                db_path,
                claim,
                step=step,
                action=action,
                state="complete",
                result_ids=[str(item["id"]) for item in selected],
            )
            return response.message, selected

    raise RuntimeError(
        f"Beacon did not reach a grounded response within {MAX_AGENT_STEPS} steps."
    )


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
        response, selected_results = _run_agent_session(
            db_path,
            claim,
            detail,
            selected_adapter,
        )
        message_id = _complete_claim(
            db_path,
            claim,
            response,
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
