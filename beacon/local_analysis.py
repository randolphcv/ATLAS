from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import import_analysis_manifest, validate_analysis_result
from .catalog import sha256_file
from .config import (
    LIKE_ESCAPE,
    archive_tier_when_sql,
    inbox_root,
    like_prefix_pattern,
    runtime_root,
)
from .database import connect, migrate, record_event
from .desk import seed_threads
from .managed_moves import (
    analysis_placement_for,
    commit_analyzed_file,
    destination_directory_blocked,
    placement_needs_clarification,
    recover_interrupted_managed_moves,
    settle_inbox_items,
)
from .media import IMAGE_EXTENSIONS, probe, should_probe
from .metadata import apply_analysis_metadata, apply_analysis_organization_path
from .music_analysis import analyze_asset_music
from .processes import hidden_creation_flags
from .repository import is_hidden_support_path, support_path_sql
from .text_preview import read_text_preview
from .thumbnails import RAW_EXTENSIONS, ensure_thumbnail
from .transcripts import get_asset_transcript, save_asset_transcript

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
POLICY_VERSION = "beacon-local-content-v4"
_WHISPER_MODEL: Any = None
NON_CONTENT_PROJECT_EXTENSIONS = frozenset({".aep", ".aepx", ".prproj"})
# Generated, non-media companions: a fixed-size camera media index written once
# per clip folder, and a gzipped editor index. Never probed, so a
# vision-language model has nothing to work from. Named constants so the owner
# can extend the list without a change to logic.
NON_CONTENT_COMPANION_EXTENSIONS = frozenset({".mif", ".prin"})
# Authored documents, not camera exhaust. Excluded under their own reason so a
# future text-extraction path can find every one of them with a single query.
DEFERRED_DOCUMENT_EXTENSIONS = frozenset({".key"})
EMPTY_FILE_SHA256 = hashlib.sha256(b"").hexdigest()
ANALYSIS_SCOPE_KINDS = frozenset(
    {"all", "visual", "audio", "other", "raw", "artifacts"}
)
# A job in one of these has finished one way or another and is not waiting on
# anything. Cancelling one is a no-op rather than an error.
TERMINAL_JOB_STATES = frozenset(
    {"complete", "partial", "failed", "cancelled"}
)
# A scope that enrols only regenerable cache may never move a file. Analysis
# normally authorizes placement, so the exception is named here and read from
# the job row at run time rather than inferred from the items, which is what
# makes "this job moves nothing" a property of the job instead of a
# coincidence of which items happened to be excluded first.
PLACEMENT_FREE_SCOPE_KINDS = frozenset({"artifacts"})
PLACEMENT_SKIPPED_FOR_SCOPE = (
    "Skipped managed placement and the Inbox settle step: this job's "
    "scope enrols only regenerable generated artifacts, which are never "
    "placed into the archive."
)


@dataclass(frozen=True)
class LocalRuntimeStatus:
    available: bool
    version: str
    models: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class LocalAnalysisRunResult:
    job_id: str
    state: str
    completed: int
    failed: int
    excluded: int
    pending: int
    analysis_run_id: str | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _is_still_image(source: Path, metadata: dict[str, Any]) -> bool:
    return (
        metadata.get("beacon_kind") == "image"
        or source.suffix.lower() in IMAGE_EXTENSIONS
        or source.suffix.lower() in RAW_EXTENSIONS
    )


def _analysis_media_bucket(
    source: Path, metadata: dict[str, Any]
) -> str:
    kinds = {
        str(stream.get("codec_type") or "")
        for stream in metadata.get("streams", [])
        if isinstance(stream, dict)
    }
    if "video" in kinds or _is_still_image(source, metadata):
        return "visual"
    if "audio" in kinds:
        return "audio"
    return "other"


def normalized_scope_path_prefix(path_prefix: str | Path | None) -> str | None:
    """Return a usable path prefix, or None when none was asked for."""
    if path_prefix is None:
        return None
    text = str(path_prefix).strip()
    return text or None


def _analysis_scope_rows(
    connection: Any,
    *,
    include_analyzed: bool,
    scope_kind: str,
    path_prefix: str | Path | None = None,
) -> list[Any]:
    if scope_kind not in ANALYSIS_SCOPE_KINDS:
        raise ValueError("unsupported analysis scope")
    visible_predicate, parameters = support_path_sql("locations.path")
    if scope_kind == "artifacts":
        # support_path_sql builds the predicate for a visible, content-bearing
        # path, which is the exact complement of what this scope wants, so it
        # is inverted rather than reimplemented.
        scope_predicate = f"NOT ({visible_predicate})"
    else:
        # Editable project files are enrolled rather than filtered out here.
        # Dropping them before enrolment gave them no item row, no reason and
        # no terminal state, so nothing could ever settle them and they sat in
        # the Inbox indefinitely. They are excluded from content inference the
        # moment the item is picked up, by _artifact_exclusion_reason, which
        # runs before any model call: enrolment costs no analysis time and buys
        # them a recorded reason and a destination.
        scope_predicate = visible_predicate
    prefix = normalized_scope_path_prefix(path_prefix)
    if prefix is None:
        prefix_predicate = "1"
    else:
        # The prefix is operator-supplied, so it is bound rather than
        # interpolated. like_prefix_pattern case-folds it, normalizes the
        # trailing separator and escapes the LIKE wildcards, which matters
        # because "_" is a wildcard and a commonplace character in folder
        # names.
        prefix_predicate = f"lower(locations.path) LIKE ? ESCAPE '{LIKE_ESCAPE}'"
        parameters.append(like_prefix_pattern(prefix))
    parameters.append(int(include_analyzed))
    rows = connection.execute(
        f"""
        SELECT assets.id, assets.sha256, assets.size_bytes,
               MIN(locations.path) AS source_path,
               assets.media_metadata_json
        FROM assets JOIN locations ON locations.asset_id = assets.id
        WHERE lower(locations.path) NOT LIKE '%.ds_store'
          AND lower(locations.path) NOT LIKE '%\\desktop.ini'
          AND lower(locations.path) NOT LIKE '%\\thumbs.db'
          AND ({scope_predicate})
          AND ({prefix_predicate})
          AND (? OR NOT EXISTS (
            SELECT 1 FROM analysis_results result
            WHERE result.asset_id = assets.id
              AND result.analysis_kind = 'contextual_metadata'
              AND result.review_state IN ('candidate', 'approved')
          ))
        GROUP BY assets.id
        ORDER BY source_path COLLATE NOCASE
        """,
        parameters,
    ).fetchall()
    if scope_kind == "all":
        return list(rows)
    selected = []
    for row in rows:
        source = Path(str(row["source_path"]))
        metadata = json.loads(row["media_metadata_json"] or "{}")
        if scope_kind == "artifacts":
            # The repository rule is the single authority on what counts as a
            # generated artifact. Asking it directly keeps enrolment identical
            # to the exclusion decision the run will make for each item.
            matches = is_hidden_support_path(source)
        elif scope_kind == "raw":
            matches = source.suffix.lower() in RAW_EXTENSIONS
        else:
            matches = _analysis_media_bucket(source, metadata) == scope_kind
        if matches:
            selected.append(row)
    return selected


def _analysis_scope_summary(rows: list[Any]) -> dict[str, Any]:
    visual = audio = other = 0
    digest = hashlib.sha256()
    for row in rows:
        source = Path(str(row["source_path"]))
        metadata = json.loads(row["media_metadata_json"] or "{}")
        bucket = _analysis_media_bucket(source, metadata)
        if bucket == "visual":
            visual += 1
        elif bucket == "audio":
            audio += 1
        else:
            other += 1
        digest.update(f"{row['id']}\0{row['sha256']}\n".encode())
    return {
        "assets": len(rows),
        "bytes": sum(int(row["size_bytes"]) for row in rows),
        "visual": visual,
        "audio": audio,
        "other": other,
        "scope_sha256": digest.hexdigest(),
    }


def _has_media_streams(metadata: dict[str, Any]) -> bool:
    if metadata.get("beacon_kind") == "image":
        return True
    return any(
        str(stream.get("codec_type") or "") in {"audio", "image", "video"}
        for stream in metadata.get("streams", [])
        if isinstance(stream, dict)
    )


def _refresh_media_metadata(
    db_path: Path,
    *,
    asset_id: str,
    source_sha256: str,
    source: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Reprobe incomplete metadata only after the source checksum is verified."""
    if _has_media_streams(metadata):
        return metadata
    refreshed = probe(source)
    if (
        not isinstance(refreshed, dict)
        or refreshed.get("error")
        or not _has_media_streams(refreshed)
    ):
        return metadata
    encoded = json.dumps(refreshed, ensure_ascii=False, sort_keys=True)
    with connect(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE assets
            SET media_metadata_json=?,last_seen_at=?
            WHERE id=? AND sha256=?
            """,
            (encoded, _utc_now(), asset_id, source_sha256),
        )
        if cursor.rowcount != 1:
            raise ValueError("catalog checksum changed during media reprobe")
        record_event(
            connection,
            kind="media_probe",
            state="complete",
            message="Refreshed incomplete media metadata before content analysis",
            asset_id=asset_id,
            location_path=str(source),
            details={
                "source_sha256": source_sha256,
                "stream_types": sorted(
                    {
                        str(stream.get("codec_type") or "")
                        for stream in refreshed.get("streams", [])
                        if isinstance(stream, dict)
                    }
                ),
            },
        )
    return refreshed


def _normalize_confidence(value: object) -> tuple[float, str | None]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("local model confidence must be numeric")
    confidence = float(value)
    if not math.isfinite(confidence):
        raise ValueError("local model confidence must be finite")
    if 0 <= confidence <= 1:
        return confidence, None
    if 1 < confidence <= 100:
        return confidence / 100, (
            f"Local model returned percentage-style confidence {confidence:g}; "
            "Beacon normalized it to the 0–1 candidate scale."
        )
    raise ValueError("local model confidence must be between 0 and 1 or 1 and 100")


LOGGER = logging.getLogger("beacon.local_analysis")

PAYLOAD_TEXT_LIMITS = {
    "title": 300,
    "description": 4_000,
    "media_category": 100,
    "organization_suggestion": 1_000,
}
PAYLOAD_TAG_LIMIT = 100
PAYLOAD_TAG_ENTRY_LIMIT = 300


def _payload_limit_violations(payload: object) -> list[str]:
    """Limit breaches the durable importer would reject. Retryable, not fatal."""
    if not isinstance(payload, dict):
        return ["payload must be an object"]
    problems: list[str] = []
    for key, limit in PAYLOAD_TEXT_LIMITS.items():
        value = payload.get(key)
        if isinstance(value, str) and len(value.strip()) > limit:
            problems.append(
                f"{key} is {len(value.strip())} characters; the limit is {limit}"
            )
    tags = payload.get("tags")
    if isinstance(tags, list):
        long_tags = [
            tag for tag in tags
            if isinstance(tag, str) and len(tag.strip()) > PAYLOAD_TAG_ENTRY_LIMIT
        ]
        if long_tags:
            problems.append(
                f"{len(long_tags)} tag(s) exceed {PAYLOAD_TAG_ENTRY_LIMIT} "
                "characters; tags must be short labels, not sentences"
            )
        if len(tags) > PAYLOAD_TAG_LIMIT:
            problems.append(
                f"{len(tags)} tags returned; the limit is {PAYLOAD_TAG_LIMIT}"
            )
    return problems


def _degrade_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Correct an over-limit payload rather than discarding the analysis.

    Reached only after the retries are exhausted. Prose is truncated because a
    shortened title still describes the asset; an over-long tag is dropped
    whole because a truncated sentence is a worse tag than no tag.
    """
    result = dict(payload)
    notes: list[str] = []
    for key, limit in PAYLOAD_TEXT_LIMITS.items():
        value = result.get(key)
        if isinstance(value, str) and len(value.strip()) > limit:
            notes.append(
                f"Beacon truncated {key} from {len(value.strip())} to {limit} "
                "characters after the local model exceeded the limit on every "
                "attempt."
            )
            result[key] = value.strip()[:limit].rstrip()
    tags = result.get("tags")
    if isinstance(tags, list):
        kept = [
            tag for tag in tags
            if isinstance(tag, str)
            and tag.strip()
            and len(tag.strip()) <= PAYLOAD_TAG_ENTRY_LIMIT
        ]
        if len(kept) != len(tags):
            notes.append(
                f"Beacon dropped {len(tags) - len(kept)} tag(s) that exceeded "
                f"{PAYLOAD_TAG_ENTRY_LIMIT} characters or were empty, and kept "
                f"{len(kept)}."
            )
        if len(kept) > PAYLOAD_TAG_LIMIT:
            notes.append(
                f"Beacon reduced {len(kept)} tags to {PAYLOAD_TAG_LIMIT}."
            )
            kept = kept[:PAYLOAD_TAG_LIMIT]
        result["tags"] = kept
    return result, notes


def _normalize_payload(payload: object) -> tuple[dict[str, Any], str | None]:
    if not isinstance(payload, dict):
        raise ValueError("local model payload must be an object")
    result = dict(payload)
    notes: list[str] = []
    suggestion = result.get("organization_suggestion")
    if isinstance(suggestion, str) and not suggestion.strip():
        result["organization_suggestion"] = (
            "No organization suggestion was produced. Human review is "
            "required; do not move or rename the original."
        )
        notes.append(
            "Local model returned an empty organization suggestion; Beacon "
            "inserted a non-operative review-required fallback."
        )
    result, limit_notes = _degrade_payload(result)
    notes.extend(limit_notes)
    return result, ("; ".join(notes) if notes else None)


def _request_json(
    endpoint: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 5,
) -> dict[str, Any]:
    url = endpoint.rstrip("/") + path
    data = None if payload is None else _canonical_json(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8", errors="replace").strip()
        except OSError:
            detail = ""
        suffix = f": {detail[:1000]}" if detail else ""
        raise ConnectionError(
            f"local model endpoint returned HTTP {error.code}{suffix}"
        ) from error
    except (OSError, UnicodeError, json.JSONDecodeError, urllib.error.URLError) as error:
        raise ConnectionError(f"local model endpoint unavailable: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("local model endpoint returned an invalid response")
    return value


def local_runtime_status(endpoint: str = DEFAULT_ENDPOINT) -> LocalRuntimeStatus:
    try:
        version = str(_request_json(endpoint, "/api/version").get("version") or "unknown")
        tags = _request_json(endpoint, "/api/tags")
        models = tuple(
            str(item.get("name"))
            for item in tags.get("models", [])
            if isinstance(item, dict) and item.get("name")
        )
        return LocalRuntimeStatus(True, version, models)
    except (ConnectionError, ValueError) as error:
        return LocalRuntimeStatus(False, "", (), str(error))


def analysis_scope_preview(
    db_path: Path,
    *,
    include_analyzed: bool = False,
    scope_kind: str = "all",
    path_prefix: str | Path | None = None,
) -> dict[str, Any]:
    if scope_kind not in ANALYSIS_SCOPE_KINDS:
        raise ValueError("unsupported analysis scope")
    return analysis_scope_previews(
        db_path,
        include_analyzed=include_analyzed,
        path_prefix=path_prefix,
    )[scope_kind]


def analysis_scope_previews(
    db_path: Path,
    *,
    include_analyzed: bool = False,
    path_prefix: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    with connect(db_path) as connection:
        migrate(connection)
        rows = _analysis_scope_rows(
            connection,
            include_analyzed=include_analyzed,
            scope_kind="all",
            path_prefix=path_prefix,
        )
        # The artifacts scope cannot be grouped out of the rows above: the
        # base query filters generated artifacts away, so this kind needs its
        # own pass.
        artifact_rows = _analysis_scope_rows(
            connection,
            include_analyzed=include_analyzed,
            scope_kind="artifacts",
            path_prefix=path_prefix,
        )
    grouped: dict[str, list[Any]] = {
        "all": list(rows),
        "visual": [],
        "audio": [],
        "other": [],
        "raw": [],
        "artifacts": list(artifact_rows),
    }
    for row in rows:
        source = Path(str(row["source_path"]))
        metadata = json.loads(row["media_metadata_json"] or "{}")
        grouped[_analysis_media_bucket(source, metadata)].append(row)
        if source.suffix.lower() in RAW_EXTENSIONS:
            grouped["raw"].append(row)
    return {
        kind: _analysis_scope_summary(scoped_rows)
        for kind, scoped_rows in grouped.items()
    }


def create_local_analysis_job(
    db_path: Path,
    *,
    model: str,
    endpoint: str = DEFAULT_ENDPOINT,
    include_analyzed: bool = False,
    scope_kind: str = "all",
    path_prefix: str | Path | None = None,
    requested_by: str = "human",
) -> str:
    model = model.strip()
    if not model:
        raise ValueError("choose a local model")
    prefix = normalized_scope_path_prefix(path_prefix)
    job_id = str(uuid.uuid4())
    now = _utc_now()
    with connect(db_path) as connection:
        migrate(connection)
        rows = _analysis_scope_rows(
            connection,
            include_analyzed=include_analyzed,
            scope_kind=scope_kind,
            path_prefix=prefix,
        )
        preview = _analysis_scope_summary(rows)
        connection.execute(
            """
            INSERT INTO local_analysis_jobs(
                id,state,model,endpoint,policy_version,scope_sha256,total_items,
                requested_by,created_at,updated_at,scope_kind,scope_path_prefix
            ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id, model, endpoint.rstrip("/"), POLICY_VERSION,
                preview["scope_sha256"], len(rows), requested_by, now, now,
                scope_kind, prefix,
            ),
        )
        connection.executemany(
            """
            INSERT INTO local_analysis_items(
                id,job_id,asset_id,source_sha256,source_path,state
            ) VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (
                (
                    str(uuid.uuid5(uuid.UUID(job_id), str(row["id"]))),
                    job_id, row["id"], row["sha256"], row["source_path"],
                )
                for row in rows
            ),
        )
        record_event(
            connection,
            kind="local_analysis_job",
            state="queued",
            message=f"Prepared local-only analysis for {len(rows):,} assets",
            details={
                "job_id": job_id, "model": model, "endpoint": endpoint,
                "scope_sha256": preview["scope_sha256"],
                "scope_kind": scope_kind,
                "scope_path_prefix": prefix,
                "placement_allowed": scope_kind
                not in PLACEMENT_FREE_SCOPE_KINDS,
            },
        )
    return job_id


def create_selected_local_analysis_job(
    db_path: Path,
    *,
    asset_ids: list[str] | tuple[str, ...],
    model: str,
    endpoint: str = DEFAULT_ENDPOINT,
    requested_by: str = "human targeted content repair",
) -> str:
    """Create a durable reanalysis job containing only explicit catalog assets."""
    selected_ids = tuple(dict.fromkeys(
        str(asset_id).strip() for asset_id in asset_ids if str(asset_id).strip()
    ))
    if not selected_ids:
        raise ValueError("choose at least one asset for targeted analysis")
    if len(selected_ids) > 1000:
        raise ValueError("targeted analysis is limited to 1,000 assets")
    model = model.strip()
    if not model:
        raise ValueError("choose a local model")
    placeholders = ",".join("?" for _ in selected_ids)
    with connect(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT assets.id, assets.sha256,
                   (
                       SELECT preferred.path
                       FROM locations preferred
                       WHERE preferred.asset_id=assets.id
                       ORDER BY
                           CASE
                               WHEN EXISTS (
                                   SELECT 1 FROM managed_moves managed
                                   WHERE managed.asset_id=preferred.asset_id
                                     AND managed.destination_path=preferred.path
                                     -- '+' keeps SQLite off idx_managed_moves_state,
                                     -- which matches nearly every row; asset_id is
                                     -- the selective index here.
                                     AND +managed.state='complete'
                               )
                               THEN 0
                """
                + archive_tier_when_sql("preferred.path", 1)
                + f"""
                               ELSE 3
                           END,
                           preferred.observed_at DESC
                       LIMIT 1
                   ) source_path
            FROM assets
            WHERE assets.id IN ({placeholders})
            ORDER BY source_path COLLATE NOCASE
            """,
            selected_ids,
        ).fetchall()
        found_ids = {str(row["id"]) for row in rows}
        missing = [asset_id for asset_id in selected_ids if asset_id not in found_ids]
        if missing:
            raise LookupError(
                f"{len(missing)} selected assets are no longer in the catalog"
            )
        digest = hashlib.sha256()
        for row in rows:
            digest.update(f"{row['id']}\0{row['sha256']}\n".encode())
        scope_sha256 = digest.hexdigest()
        job_id = str(uuid.uuid4())
        now = _utc_now()
        connection.execute(
            """
            INSERT INTO local_analysis_jobs(
                id,state,model,endpoint,policy_version,scope_sha256,total_items,
                requested_by,created_at,updated_at,scope_kind
            ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                model,
                endpoint.rstrip("/"),
                POLICY_VERSION,
                scope_sha256,
                len(rows),
                requested_by,
                now,
                now,
                "selected_content_repair",
            ),
        )
        connection.executemany(
            """
            INSERT INTO local_analysis_items(
                id,job_id,asset_id,source_sha256,source_path,state
            ) VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (
                (
                    str(uuid.uuid5(uuid.UUID(job_id), str(row["id"]))),
                    job_id,
                    row["id"],
                    row["sha256"],
                    row["source_path"],
                )
                for row in rows
            ),
        )
        record_event(
            connection,
            kind="local_analysis_job",
            state="queued",
            message=(
                f"Prepared targeted content repair for {len(rows):,} assets"
            ),
            details={
                "job_id": job_id,
                "model": model,
                "endpoint": endpoint,
                "scope_sha256": scope_sha256,
                "scope_kind": "selected_content_repair",
            },
        )
    return job_id


def _counts(connection: Any, job_id: str) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT
          SUM(CASE WHEN state='complete' AND excluded_reason IS NULL
              THEN 1 ELSE 0 END) complete,
          SUM(CASE WHEN state='complete' AND excluded_reason IS NOT NULL
              THEN 1 ELSE 0 END) excluded,
          SUM(CASE WHEN state='failed' THEN 1 ELSE 0 END) failed,
          SUM(CASE WHEN state='pending' THEN 1 ELSE 0 END) pending,
          SUM(CASE WHEN state='running' THEN 1 ELSE 0 END) running
        FROM local_analysis_items WHERE job_id=?
        """,
        (job_id,),
    ).fetchone()
    return {
        key: int(row[key] or 0)
        for key in ("complete", "excluded", "failed", "pending", "running")
    }


def list_local_analysis_jobs(db_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            """
            SELECT jobs.*,
              SUM(CASE WHEN items.state='complete'
                        AND items.excluded_reason IS NULL
                  THEN 1 ELSE 0 END) completed_count,
              SUM(CASE WHEN items.state='complete'
                        AND items.excluded_reason IS NOT NULL
                  THEN 1 ELSE 0 END) excluded_count,
              SUM(CASE WHEN items.state='failed' THEN 1 ELSE 0 END) failed_count,
              SUM(CASE WHEN items.state='pending' THEN 1 ELSE 0 END) pending_count,
              SUM(CASE WHEN items.state='running' THEN 1 ELSE 0 END) running_count,
              MAX(CASE
                WHEN items.asset_id=jobs.current_asset_id THEN items.source_path
              END) current_source_path
            FROM local_analysis_jobs jobs
            LEFT JOIN local_analysis_items items ON items.job_id=jobs.id
            GROUP BY jobs.id ORDER BY jobs.updated_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def request_local_analysis_cancel(db_path: Path, job_id: str) -> None:
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT state FROM local_analysis_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise LookupError("analysis job not found")
        if row["state"] in {"complete", "failed"}:
            return
        connection.execute(
            "UPDATE local_analysis_jobs SET cancel_requested=1,updated_at=? WHERE id=?",
            (_utc_now(), job_id),
        )


def cancel_local_analysis_job(db_path: Path, job_id: str) -> str:
    """End a job whether or not a worker is still alive to notice.

    ``request_local_analysis_cancel`` sets a flag the run loop checks between
    items. That is the right mechanism for a running job and no mechanism at
    all for a paused one: nothing is looping, so the flag is read by nobody
    and the job sits in a non-terminal state forever. A paused job with no
    live worker is therefore terminalized here and now.

    Items left pending are released, not deleted. The rows are the record of
    what the job enrolled, and an item's history outlives the job that
    enrolled it. Nothing is moved and no managed move is touched.

    Returns "requested" when a live worker will stop cooperatively, or
    "cancelled" when the job was terminalized directly.
    """
    with connect(db_path) as connection:
        migrate(connection)
        job = connection.execute(
            "SELECT state, worker_pid FROM local_analysis_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if job is None:
            raise LookupError("analysis job not found")
        state = str(job["state"])
        if state in TERMINAL_JOB_STATES:
            return state
        worker_alive = state == "running" and _process_is_alive(
            job["worker_pid"]
        )
        if worker_alive:
            connection.execute(
                """
                UPDATE local_analysis_jobs
                SET cancel_requested=1,updated_at=? WHERE id=?
                """,
                (_utc_now(), job_id),
            )
            return "requested"
        released = connection.execute(
            """
            UPDATE local_analysis_items SET state='pending',started_at=NULL
            WHERE job_id=? AND state='running'
            """,
            (job_id,),
        ).rowcount
        pending = connection.execute(
            "SELECT COUNT(*) AS n FROM local_analysis_items "
            "WHERE job_id=? AND state='pending'",
            (job_id,),
        ).fetchone()["n"]
        now = _utc_now()
        connection.execute(
            """
            UPDATE local_analysis_jobs
            SET state='cancelled',cancel_requested=0,current_asset_id=NULL,
                current_stage=NULL,current_stage_updated_at=?,
                worker_pid=NULL,completed_at=?,updated_at=?
            WHERE id=?
            """,
            (now, now, now, job_id),
        )
        record_event(
            connection,
            kind="local_analysis_job",
            state="cancelled",
            message="Analysis job cancelled by the owner with no live worker",
            details={
                "job_id": job_id,
                "previous_state": state,
                "running_items_released": released,
                "pending_items_left": pending,
            },
        )
    return "cancelled"


def close_local_analysis_job(db_path: Path, job_id: str) -> dict[str, Any]:
    """Accept a job's outcome as final without retrying or re-enrolling it.

    A job that ends partial has done work worth keeping and work that failed.
    Leaving it partial means it reads as unfinished forever; retrying it means
    re-running what already succeeded. Closing records that the owner read the
    outcome and accepted it, with the counts as they stood.

    Moves nothing, re-enrols nothing, deletes nothing. The retry control skips
    a closed job, which is what stops a closed outcome being reopened by a
    later click.
    """
    with connect(db_path) as connection:
        migrate(connection)
        job = connection.execute(
            "SELECT state, closed_at FROM local_analysis_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if job is None:
            raise LookupError("analysis job not found")
        if job["closed_at"]:
            raise ValueError("this job is already closed")
        if str(job["state"]) == "running":
            raise ValueError("stop the analysis before closing the job")
        counts = _counts(connection, job_id)
        now = _utc_now()
        summary = (
            "Closed by owner: {complete} analysed, {excluded} excluded, "
            "{failed} failed, {pending} left pending.".format(**counts)
        )
        connection.execute(
            """
            UPDATE local_analysis_jobs
            SET state='cancelled',closed_at=?,cancel_requested=0,
                current_asset_id=NULL,current_stage=NULL,
                current_stage_updated_at=?,worker_pid=NULL,
                completed_at=COALESCE(completed_at, ?),updated_at=?,error=?
            WHERE id=?
            """,
            (now, now, now, now, summary, job_id),
        )
        record_event(
            connection,
            kind="local_analysis_job",
            state="closed",
            message=summary,
            details={"job_id": job_id, "previous_state": str(job["state"]),
                     **counts},
        )
    return {"job_id": job_id, "summary": summary, **counts}


def cancellable_local_analysis_jobs(db_path: Path) -> list[dict[str, Any]]:
    """Jobs the owner can end: anything not already in a terminal state."""
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            """
            SELECT id, state, total_items FROM local_analysis_jobs
            WHERE state NOT IN ('complete','partial','failed','cancelled')
            ORDER BY created_at
            """
        ).fetchall()
    return [dict(row) for row in rows]


def closeable_local_analysis_jobs(db_path: Path) -> list[dict[str, Any]]:
    """Jobs sitting in partial that the owner has not yet closed."""
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            """
            SELECT id, state, total_items FROM local_analysis_jobs
            WHERE state='partial' AND closed_at IS NULL
            ORDER BY created_at
            """
        ).fetchall()
    return [dict(row) for row in rows]


def cancel_open_local_analysis_jobs(db_path: Path) -> list[dict[str, str]]:
    """Cancel every job that is not terminal. One item never stops another."""
    results: list[dict[str, str]] = []
    for job in cancellable_local_analysis_jobs(db_path):
        job_id = str(job["id"])
        try:
            outcome = cancel_local_analysis_job(db_path, job_id)
        except Exception as error:  # noqa: BLE001
            LOGGER.exception("cancelling one job failed")
            outcome = f"error: {str(error)[:120]}"
        results.append({"job_id": job_id, "outcome": outcome})
    return results


def close_partial_local_analysis_jobs(db_path: Path) -> list[dict[str, Any]]:
    """Close every open partial job. One failure never stops the rest."""
    results: list[dict[str, Any]] = []
    for job in closeable_local_analysis_jobs(db_path):
        job_id = str(job["id"])
        try:
            results.append(close_local_analysis_job(db_path, job_id))
        except Exception as error:  # noqa: BLE001
            LOGGER.exception("closing one job failed")
            results.append(
                {"job_id": job_id, "error": str(error)[:120]}
            )
    return results


def recover_local_analysis_jobs(db_path: Path) -> int:
    with connect(db_path) as connection:
        migrate(connection)
        jobs = connection.execute(
            "SELECT id,worker_pid FROM local_analysis_jobs WHERE state='running'"
        ).fetchall()
        abandoned = [
            row for row in jobs
            if not _process_is_alive(row["worker_pid"])
        ]
        for row in abandoned:
            connection.execute(
                "UPDATE local_analysis_items SET state='pending' WHERE job_id=? AND state='running'",
                (row["id"],),
            )
            connection.execute(
                """
                UPDATE local_analysis_jobs
                SET state='paused',current_asset_id=NULL,current_stage=NULL,
                    current_stage_updated_at=?,worker_pid=NULL,updated_at=?
                WHERE id=?
                """,
                (_utc_now(), _utc_now(), row["id"]),
            )
        return len(abandoned)


def _process_is_alive(value: object) -> bool:
    try:
        pid = int(value or 0)
        if pid <= 0:
            return False
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            process = ctypes.windll.kernel32.OpenProcess(
                0x1000,  # PROCESS_QUERY_LIMITED_INFORMATION
                False,
                pid,
            )
            if not process:
                return False
            try:
                exit_code = wintypes.DWORD()
                if not ctypes.windll.kernel32.GetExitCodeProcess(
                    process, ctypes.byref(exit_code)
                ):
                    return False
                return exit_code.value == 259  # STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(process)
        os.kill(pid, 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def retry_local_analysis_failures(db_path: Path, job_id: str) -> int:
    """Return failed items to pending without replacing the durable job."""
    with connect(db_path) as connection:
        migrate(connection)
        job = connection.execute(
            "SELECT state, closed_at FROM local_analysis_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if job is None:
            raise LookupError("analysis job not found")
        if job["state"] == "running":
            raise ValueError("wait for analysis to stop before retrying failures")
        if job["closed_at"]:
            # The owner read this job's outcome and accepted it. Reopening it
            # on a later click would undo a deliberate decision.
            raise ValueError("this job was closed by the owner; it is final")
        cursor = connection.execute(
            """
            UPDATE local_analysis_items
            SET state='pending',error=NULL,excluded_reason=NULL,
                started_at=NULL,completed_at=NULL
            WHERE job_id=? AND state='failed'
            """,
            (job_id,),
        )
        connection.execute(
            """
            UPDATE local_analysis_jobs
            SET state='paused',cancel_requested=0,current_asset_id=NULL,
                current_stage=NULL,current_stage_updated_at=?,
                completed_at=NULL,updated_at=?,error=NULL,
                policy_version=?
            WHERE id=?
            """,
            (_utc_now(), _utc_now(), POLICY_VERSION, job_id),
        )
        return int(cursor.rowcount)


def _set_job_stage(db_path: Path, job_id: str, stage: str) -> None:
    """Persist a meaningful pipeline boundary for the active durable job."""
    now = _utc_now()
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE local_analysis_jobs
            SET current_stage=?,current_stage_updated_at=?,updated_at=?
            WHERE id=?
            """,
            (stage, now, now, job_id),
        )


def _undecodable_reason(source: Path, metadata: dict[str, Any] | None) -> str:
    """Name the actual cause, not the symptom.

    "no decodable content evidence" is what Beacon observed; it says nothing
    about why, which forced a catalog query to diagnose a whole class of
    failures. Each branch below is separately actionable.
    """
    suffix = source.suffix.lower() or "(no extension)"
    if not should_probe(source):
        return (
            f"{suffix} is not a supported media type, so no probe was "
            "attempted and there is no content to analyse; this file should "
            "not have entered analysis scope"
        )
    try:
        size = source.stat().st_size
    except OSError:
        size = None
    if size == 0:
        return f"the file is zero bytes, so {suffix} content cannot be decoded"
    if not metadata:
        return (
            f"{suffix} is a supported media type but the probe returned no "
            "metadata; the media tool may be unavailable or the file "
            "unreadable"
        )
    if metadata.get("error"):
        return (
            f"the probe of this {suffix} file failed: "
            f"{str(metadata.get('error'))[:300]}"
        )
    streams = metadata.get("streams") or []
    kinds = sorted({str(s.get("codec_type")) for s in streams if isinstance(s, dict)})
    if not streams:
        return (
            f"the probe of this {suffix} file reported no streams, so it "
            "holds no decodable video, audio, or image content"
        )
    return (
        f"the probe of this {suffix} file reported only {', '.join(kinds)} "
        "stream(s), none of which yields visual, audio, or text evidence"
    )


CONTENT_EVIDENCE_MODES = {
    "visual_content",
    "audio_content",
    "text_content",
}


def _validate_content_candidate(
    candidate: dict[str, Any],
    *,
    expected_mode: str | None = None,
) -> None:
    """Reject speculative or incomplete local results before publication."""
    validated = validate_analysis_result(candidate)
    payload = validated["payload"]
    mode = str(payload.get("evidence_mode") or "")
    observations = payload.get("content_observations")
    if mode not in CONTENT_EVIDENCE_MODES:
        raise ValueError(
            "local analysis did not produce content-derived evidence"
        )
    if expected_mode and mode != expected_mode:
        raise ValueError(
            f"local analysis returned {mode or 'no evidence'}; "
            f"{expected_mode} was required"
        )
    if (
        not isinstance(observations, list)
        or not observations
        or any(not isinstance(item, str) or not item.strip()
               for item in observations)
    ):
        raise ValueError(
            "local analysis must include concrete content observations"
        )


def job_may_place(job: Any) -> bool:
    """Whether this job is allowed to move originals at all.

    The single authority for both movement call sites in a run: the managed
    placement of each analyzed candidate, and the settle step that follows
    it. A job whose scope enrols only regenerable generated
    artifacts answers False, so neither site runs.

    The answer comes from the job row, which means it survives a restart and a
    run started from another process, and it does not depend on which items
    happened to be excluded first.
    """
    try:
        scope_kind = job["scope_kind"]
    except (KeyError, IndexError, TypeError):
        # A job row written before schema 17 carries no scope kind. It cannot
        # be a placement-free scope, because that scope did not exist, so it
        # behaves exactly as it did before this guard.
        return True
    return str(scope_kind or "") not in PLACEMENT_FREE_SCOPE_KINDS


def _record_placement_guard(
    db_path: Path,
    *,
    job_id: str,
    scope_kind: str,
    item_count: int,
) -> None:
    """Write the skipped-placement decision to the audit trail.

    AGENTS.md section 10: a correction is never silent. A job that declines to
    place is a user-facing fact, not a debug detail.
    """
    with connect(db_path) as connection:
        record_event(
            connection,
            kind="local_analysis_placement_guard",
            state="skipped",
            message=PLACEMENT_SKIPPED_FOR_SCOPE,
            details={
                "job_id": job_id,
                "scope_kind": scope_kind,
                "candidates_not_placed": item_count,
                "settle_skipped": True,
            },
        )


def _artifact_exclusion_reason(
    source_path: str | Path,
    *,
    size_bytes: int | None = None,
    source_sha256: str | None = None,
) -> str | None:
    source = Path(source_path)
    if size_bytes == 0 and source_sha256 == EMPTY_FILE_SHA256:
        return (
            "Excluded empty file from contextual content inference; the "
            "zero-byte catalog identity remains searchable."
        )
    if source.suffix.lower() in NON_CONTENT_PROJECT_EXTENSIONS:
        return (
            "Excluded editable production project file from contextual content "
            "inference; the project remains cataloged and searchable."
        )
    if source.suffix.lower() in NON_CONTENT_COMPANION_EXTENSIONS:
        return (
            "Excluded camera metadata or generated editor index from "
            "contextual content inference; the file remains cataloged and "
            "searchable."
        )
    if source.suffix.lower() in DEFERRED_DOCUMENT_EXTENSIONS:
        return (
            "Deferred presentation document pending text extraction; it holds "
            "no decodable media evidence today and remains cataloged and "
            "searchable."
        )
    if not is_hidden_support_path(source_path):
        return None
    return (
        "Excluded confidently generated cache, autosave, or sidecar artifact; "
        "the original remains cataloged and can be shown as a hidden file."
    )


def _resolve_item_source(
    db_path: Path,
    *,
    asset_id: str,
    stored_path: str,
) -> Path:
    """Where this item's bytes are now, not where they were when enrolled.

    An item's ``source_path`` records the location it was enrolled from. Once
    settle moves a failed item to the review holding zone, that path no longer
    exists, and a retry that trusted it would fail on a file that is sitting
    safely one directory away. The catalog's ``locations`` table is the record
    of where a file is, so a retry resolves the item by catalog location and
    falls back to the enrolled path only when nothing else is on disk.
    """
    stored = Path(stored_path)
    if stored.exists():
        return stored
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT path FROM locations WHERE asset_id=? ORDER BY observed_at DESC",
            (asset_id,),
        ).fetchall()
    for row in rows:
        candidate = Path(str(row["path"]))
        if candidate.exists():
            return candidate
    return stored


def _complete_analysis_exclusion(
    db_path: Path,
    item_id: str,
    reason: str,
) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE local_analysis_items
            SET state='complete',result_json=NULL,error=NULL,
                excluded_reason=?,completed_at=?
            WHERE id=?
            """,
            (reason, _utc_now(), item_id),
        )


def _analysis_metadata_applied(
    db_path: Path,
    asset_id: str,
    run_id: str,
) -> bool:
    with connect(db_path) as connection:
        return connection.execute(
            """
            SELECT 1 FROM asset_metadata_revisions
            WHERE asset_id=? AND source=?
            LIMIT 1
            """,
            (asset_id, f"analysis_run:{run_id}"),
        ).fetchone() is not None


def _analysis_placement_seed_key(
    kind: str,
    run_id: str,
    asset_id: str,
    source_path: Path,
) -> str:
    path_fingerprint = hashlib.sha256(
        str(source_path).encode("utf-8")
    ).hexdigest()[:16]
    return f"analysis-placement-{kind}:{run_id}:{asset_id}:{path_fingerprint}"


def _record_finalization_failure(
    db_path: Path,
    *,
    run_id: str,
    job_id: str,
    asset_id: str,
    error: BaseException,
) -> None:
    """Record one item's finalization failure without disturbing the others."""
    try:
        with connect(db_path) as connection:
            connection.execute(
                """
                UPDATE local_analysis_items
                SET state='failed',error=?
                WHERE job_id=? AND asset_id=?
                """,
                (
                    "Result published but finalization failed: "
                    f"{str(error)[:1900]}",
                    job_id,
                    asset_id,
                ),
            )
            record_event(
                connection,
                kind="local_analysis_finalization",
                state="failed",
                message=(
                    "Finalization failed for one analyzed asset; the rest of "
                    "the run was unaffected"
                ),
                asset_id=asset_id,
                details={
                    "analysis_run_id": run_id,
                    "job_id": job_id,
                    "error_class": type(error).__name__,
                    "error": str(error)[:1000],
                },
            )
    except Exception:
        # Recording a failure must never itself abort the batch.
        LOGGER.exception("could not record finalization failure")


def _record_analysis_placement_failure(
    db_path: Path,
    *,
    run_id: str,
    asset_id: str,
    source_path: Path,
    error: Exception,
) -> None:
    error_text = str(error)[:1900]
    source_present = source_path.is_file()
    with connect(db_path) as connection:
        record_event(
            connection,
            kind="local_analysis_placement",
            state="failed",
            message="Analyzed file placement requires attention",
            asset_id=asset_id,
            location_path=str(source_path),
            details={
                "analysis_run_id": run_id,
                "error": error_text,
                "source_present": source_present,
            },
        )
    source_state = (
        "Beacon confirmed that the source is still present at its cataloged "
        "path."
        if source_present
        else (
            "Beacon could not confirm the source at its cataloged path; "
            "inspect the managed-move record before retrying."
        )
    )
    seed_threads(
        db_path,
        [
            {
                "seed_key": _analysis_placement_seed_key(
                    "error", run_id, asset_id, source_path
                ),
                "subject": "Beacon could not place an analyzed file",
                "body": (
                    "Contextual analysis completed, but the managed archive "
                    f"placement failed for {source_path}. {source_state} "
                    f"Error: {error_text}"
                ),
                "kind": "blocker",
                "priority": "important",
                "requires_approval": False,
                "asset_id": asset_id,
            }
        ],
    )


def _default_analyzer(
    endpoint: str, model: str, asset: dict[str, Any]
) -> dict[str, Any]:
    prompt = (
        "You are Beacon, a local archive and stock-footage metadata specialist. "
        "Use all supplied sampled frames, transcript, spectrogram, music features, "
        "or extracted text. The title, description, tags, and stock metadata must "
        "describe only content actually observed in that evidence. For visual "
        "media, describe subjects, actions, setting, light, color, composition, "
        "mood, and visible text concretely. Never use a filename, extension, codec, "
        "resolution, duration, file size, path, frame rate, or analysis mechanism "
        "as a substitute for observed content. Never call an "
        "ordinary still photograph a video frame or image sequence because of "
        "technical decoder metadata. Be highly descriptive and produce as many "
        "specific, relevant search tags as useful (up to 100): subjects, actions, "
        "apparent age group, apparent gender presentation (never gender identity), "
        "facial expression, wardrobe, setting, weather, lighting, dominant colors, "
        "shot size, angle, composition, camera movement, copy space, mood, concepts, "
        "speech topics, sound sources, music character, and likely B-roll uses. "
        "Do not identify an unnamed person, invent dialogue, rights, relationships, "
        "or events. Make visual claims only from supplied images. If supplied "
        "images are decodable but abstract, blurred, dark, defocused, dominated "
        "by light or texture, or lack a recognizable subject, that is still "
        "visual content: describe only the visible forms, colors, light, texture, "
        "composition, and movement cues and use evidence_mode 'visual_content'. "
        "Use 'unreadable' only when supplied image bytes cannot be interpreted at "
        "all. The required_evidence_mode field is binding and describes the "
        "content evidence that must ground the response. A supplied spectrogram "
        "is audio-derived evidence, not a photographed scene; when "
        "required_evidence_mode is 'audio_content', use that mode and ground "
        "claims in the transcript, sound, music features, or spectrogram. "
        "If no image is supplied, limit claims to supplied audio-derived or "
        "text-derived content. Never manufacture a content result from technical "
        "context alone. "
        "Distinguish observation from uncertainty. A managed archive move "
        "policy already exists, so provide a useful organization suggestion without "
        "asking for approval; analysis itself must never move or alter an original."
    )
    stock_properties = {
        key: {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        }
        for key in (
            "people", "apparent_age_groups", "apparent_gender_presentations",
            "facial_expressions", "actions", "wardrobe", "setting",
            "lighting", "dominant_colors", "camera", "composition",
            "camera_movement", "copy_space", "mood", "concepts",
            "visible_text", "logos", "audio_subjects", "sound_sources",
            "music_character", "stock_uses", "release_concerns",
        )
    }
    schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "maxLength": PAYLOAD_TEXT_LIMITS["title"],
            },
            "description": {
                "type": "string",
                "maxLength": PAYLOAD_TEXT_LIMITS["description"],
            },
            "content_observations": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 20,
            },
            "evidence_mode": {
                "type": "string",
                "enum": [
                    "visual_content",
                    "audio_content",
                    "text_content",
                    "technical_only",
                    "unreadable",
                ],
            },
            "media_category": {
                "type": "string",
                "maxLength": PAYLOAD_TEXT_LIMITS["media_category"],
            },
            "tags": {
                "type": "array",
                "items": {
                    "type": "string",
                    "maxLength": PAYLOAD_TAG_ENTRY_LIMIT,
                },
                "maxItems": PAYLOAD_TAG_LIMIT,
            },
            "privacy_flags": {"type": "array", "items": {"type": "string"}},
            "organization_suggestion": {
                "type": "string",
                "maxLength": PAYLOAD_TEXT_LIMITS["organization_suggestion"],
            },
            "stock_metadata": {
                "type": "object",
                "properties": stock_properties,
                "required": list(stock_properties),
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "title", "description", "content_observations", "evidence_mode",
            "media_category", "tags", "privacy_flags",
            "organization_suggestion", "confidence",
            "stock_metadata",
        ],
    }
    media_context, image_paths, temporary_root = _prepare_media_context(asset)
    source = Path(str(asset["source_path"]))
    is_still_image = _is_still_image(
        source, asset.get("media_metadata") or {}
    )
    stage_callback = asset.get("stage_callback")
    if callable(stage_callback):
        stage_callback(
            "visually_observing" if image_paths else "analyzing_context"
        )
    expected_mode = str(media_context.get("expected_evidence_mode") or "")
    media_context["visual_evidence_supplied"] = bool(
        image_paths and expected_mode == "visual_content"
    )
    media_context["supplemental_image_evidence_supplied"] = bool(
        image_paths and expected_mode != "visual_content"
    )
    if expected_mode not in CONTENT_EVIDENCE_MODES:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise ValueError(
            "no decodable visual, audio, or text content evidence was "
            "available: "
            + _undecodable_reason(source, asset.get("media_metadata") or {})
        )
    request_context: dict[str, Any] = {
        "asset_mode": (
            "still_image"
            if is_still_image
            else expected_mode.replace("_content", "")
        ),
        "required_evidence_mode": expected_mode,
        "local_media_context": media_context,
    }
    content = _canonical_json(request_context)
    message: dict[str, Any] = {"role": "user", "content": content}
    encoded_images = []
    for image_path in image_paths:
        if image_path.is_file() and image_path.stat().st_size <= 8 * 1024 * 1024:
            encoded_images.append(base64.b64encode(image_path.read_bytes()).decode("ascii"))
    if encoded_images:
        message["images"] = encoded_images
    last_error: Exception | None = None
    last_rejected_output: str | None = None
    limited_result: dict[str, Any] | None = None
    try:
        for attempt in range(1, 4):
            retry_note = ""
            if last_error is not None:
                retry_note = (
                    "\nA previous response was rejected: "
                    f"{str(last_error)[:500]}. Re-observe the supplied content "
                    "and return a complete schema-valid JSON object using the "
                    "required_evidence_mode. Abstract, dark, blurred, defocused, "
                    "or textural imagery is still visual content when decodable. "
                    "A spectrogram is audio-derived evidence. Do not substitute "
                    "technical metadata."
                )
            messages: list[dict[str, Any]] = [
                {
                    "role": "system",
                    "content": prompt + retry_note,
                },
                message,
            ]
            if last_rejected_output is not None:
                messages.extend(
                    [
                        {
                            "role": "assistant",
                            "content": last_rejected_output[-8_000:],
                        },
                        {
                            "role": "user",
                            "content": (
                                "That response was rejected. Correct your own "
                                "output using the supplied content evidence and "
                                "return one complete schema-valid JSON object."
                            ),
                        },
                    ]
                )
            try:
                response = _request_json(
                    endpoint,
                    "/api/chat",
                    {
                        "model": model,
                        "messages": messages,
                        "format": schema,
                        "stream": False,
                        "options": {
                            "temperature": 0 if attempt == 1 else 0.1,
                            "num_ctx": 32768,
                            "num_predict": 4096,
                        },
                    },
                    timeout=600,
                )
            except (ConnectionError, ValueError) as error:
                last_error = error
                continue
            try:
                response_message = response.get("message")
                if (
                    not isinstance(response_message, dict)
                    or not isinstance(response_message.get("content"), str)
                ):
                    raise ValueError(
                        "local model returned no structured message"
                    )
                response_content = response_message["content"]
                result = json.loads(response_content)
                if not isinstance(result, dict):
                    raise ValueError("local model result is not an object")
                for key in (
                    "title",
                    "description",
                    "media_category",
                    "organization_suggestion",
                ):
                    if (
                        not isinstance(result.get(key), str)
                        or not str(result[key]).strip()
                    ):
                        raise ValueError(
                            f"local model returned an empty {key}"
                        )
                observations = result.get("content_observations")
                actual_mode = str(result.get("evidence_mode") or "")
                if actual_mode != expected_mode:
                    raise ValueError(
                        "local model returned evidence mode "
                        f"{actual_mode or 'missing'}; {expected_mode} was required"
                    )
                if (
                    not isinstance(observations, list)
                    or not observations
                    or any(
                        not isinstance(item, str) or not item.strip()
                        for item in observations
                    )
                ):
                    raise ValueError(
                        "local model did not produce concrete "
                        f"{expected_mode.replace('_', '-')} observations"
                    )
                violations = _payload_limit_violations(result)
                if violations:
                    if limited_result is None:
                        # One corrective attempt. The rejected output is fed
                        # back, so the model is told exactly which field it
                        # overran.
                        limited_result = result
                        raise ValueError(
                            "local model exceeded field limits: "
                            + "; ".join(violations)
                        )
                    # It overran twice. It will not self-correct, and a third
                    # full generation buys nothing: keep the analysis and let
                    # the shared degrade policy correct and record the field.
                    limited_result = result
                    break
                return result
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                last_error = error
                if (
                    isinstance(response_message, dict)
                    and isinstance(response_message.get("content"), str)
                ):
                    last_rejected_output = response_message["content"]
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
    if limited_result is not None:
        # Structurally sound, only over-length. Model output is an untrusted
        # input source (AGENTS.md section 10): an over-long field is corrected
        # and recorded by _normalize_payload, not thrown away.
        LOGGER.warning(
            "local model exceeded field limits on every attempt; "
            "keeping the analysis and degrading the over-long fields"
        )
        return limited_result
    raise ValueError(
        "local model failed content validation after three attempts: "
        f"{last_error}"
    )


def _duration_seconds(metadata: dict[str, Any]) -> float:
    try:
        return max(0.0, float((metadata.get("format") or {}).get("duration") or 0))
    except (TypeError, ValueError):
        return 0.0


def _analysis_excerpt(text: str, limit: int = 8000) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    third = (limit - 80) // 3
    middle = max(0, (len(text) - third) // 2)
    return (
        text[:third]
        + "\n[...middle excerpt...]\n"
        + text[middle:middle + third]
        + "\n[...ending excerpt...]\n"
        + text[-third:],
        True,
    )


def _transcribe_audio(
    source: Path,
    *,
    db_path: Path | None = None,
    asset_id: str = "",
    source_sha256: str = "",
) -> dict[str, Any]:
    global _WHISPER_MODEL
    if db_path and asset_id and source_sha256:
        cached = get_asset_transcript(
            db_path, asset_id, source_sha256=source_sha256
        )
        if cached:
            excerpt, excerpted = _analysis_excerpt(str(cached["text"]))
            return {
                "status": "cached",
                "language": cached.get("language") or "",
                "language_probability": cached.get("language_probability"),
                "transcript": str(cached["text"]),
                "analysis_excerpt": excerpt,
                "excerpted": excerpted,
            }
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {"status": "unavailable", "transcript": ""}
    if _WHISPER_MODEL is None:
        model_name = os.environ.get("BEACON_WHISPER_MODEL", "small")
        model_root = (
            runtime_root() / "models" / "whisper"
        )
        model_root.mkdir(parents=True, exist_ok=True)
        _WHISPER_MODEL = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            download_root=str(model_root),
        )
    segments, info = _WHISPER_MODEL.transcribe(
        str(source), beam_size=5, vad_filter=True, word_timestamps=False
    )
    text = " ".join(
        segment.text.strip() for segment in segments if segment.text.strip()
    ).strip()
    language = str(getattr(info, "language", "") or "")
    probability = getattr(info, "language_probability", None)
    if not text:
        return {
            "status": "complete",
            "language": language,
            "language_probability": probability,
            "transcript": "",
            "analysis_excerpt": "",
            "excerpted": False,
        }
    if db_path and asset_id and source_sha256:
        if sha256_file(source) != source_sha256:
            raise ValueError("source bytes changed during transcription")
        save_asset_transcript(
            db_path,
            asset_id=asset_id,
            source_sha256=source_sha256,
            text=text,
            language=language,
            language_probability=probability,
        )
    excerpt, excerpted = _analysis_excerpt(text)
    return {
        "status": "complete",
        "language": language,
        "language_probability": probability,
        "transcript": text,
        "analysis_excerpt": excerpt,
        "excerpted": excerpted,
    }


def ensure_asset_transcript(db_path: Path, asset_id: str) -> dict[str, Any]:
    """Create or reuse the full checksum-bound transcript for one audio asset."""
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            """
            SELECT a.sha256,a.media_metadata_json,MIN(l.path) AS source_path
            FROM assets a JOIN locations l ON l.asset_id=a.id
            WHERE a.id=? GROUP BY a.id
            """,
            (asset_id,),
        ).fetchone()
    if row is None:
        raise LookupError("Catalog asset was not found.")
    metadata = json.loads(row["media_metadata_json"] or "{}")
    kinds = {
        str(stream.get("codec_type") or "")
        for stream in metadata.get("streams", [])
        if isinstance(stream, dict)
    }
    if "audio" not in kinds or "video" in kinds:
        raise ValueError("Full speech transcripts are generated for audio-only assets.")
    source = Path(row["source_path"])
    if sha256_file(source) != row["sha256"]:
        raise ValueError("source bytes changed since cataloging")
    return _transcribe_audio(
        source,
        db_path=db_path,
        asset_id=asset_id,
        source_sha256=row["sha256"],
    )


def _image_is_uniformly_near_black(path: Path) -> bool:
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as image:
            grayscale = image.convert("L")
            grayscale.thumbnail((320, 320))
            statistics = ImageStat.Stat(grayscale)
            mean = float(statistics.mean[0])
            deviation = float(statistics.stddev[0])
            histogram = grayscale.histogram()
    except (OSError, ValueError):
        return False
    pixels = sum(histogram)
    threshold_count = max(1, math.ceil(pixels * 0.99))
    cumulative = 0
    percentile_99 = 255
    for level, count in enumerate(histogram):
        cumulative += count
        if cumulative >= threshold_count:
            percentile_99 = level
            break
    # Broadcast/video black is commonly encoded around luma 16-32 rather than
    # digital zero. Require both low luminance and extremely low detail so a
    # genuinely dark scene with visible structure remains visual evidence.
    return mean <= 48 and deviation <= 3 and percentile_99 <= 56


def _all_images_uniformly_near_black(images: list[Path]) -> bool:
    return bool(images) and all(_image_is_uniformly_near_black(path) for path in images)


def _append_audio_context(
    *,
    context: dict[str, Any],
    images: list[Path],
    temp_root: Path,
    executable: str,
    source: Path,
    asset: dict[str, Any],
    stage_callback: object,
) -> None:
    if callable(stage_callback):
        stage_callback("preparing_audio_context")
    spectrum = temp_root / "audio-spectrum.png"
    completed = subprocess.run(
        [
            executable, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-lavfi",
            "showspectrumpic=s=1200x600:legend=1:color=channel",
            "-frames:v", "1", str(spectrum),
        ],
        capture_output=True,
        timeout=180,
        check=False,
        creationflags=hidden_creation_flags(),
    )
    if completed.returncode == 0 and spectrum.is_file():
        images.append(spectrum)
        context["spectrogram"] = "full-file local frequency/time visualization"
    if callable(stage_callback):
        stage_callback("transcribing_audio")
    speech = _transcribe_audio(
        source,
        db_path=Path(str(asset["db_path"])) if asset.get("db_path") else None,
        asset_id=str(asset.get("asset_id") or ""),
        source_sha256=str(asset.get("source_sha256") or ""),
    )
    context["speech_analysis"] = {
        key: value
        for key, value in speech.items()
        if key not in {"transcript", "analysis_excerpt"}
    }
    context["speech_analysis"]["transcript"] = speech.get(
        "analysis_excerpt", ""
    )
    has_audio_evidence = bool(
        images or str(speech.get("analysis_excerpt") or "").strip()
    )
    if asset.get("db_path") and asset.get("asset_id"):
        try:
            if callable(stage_callback):
                stage_callback("analyzing_music")
            music = analyze_asset_music(
                Path(str(asset["db_path"])),
                asset_id=str(asset["asset_id"]),
                source_path=source,
                source_sha256=str(asset.get("source_sha256") or ""),
                full=True,
            )
            context["music_analysis"] = {
                key: value
                for key, value in music.items()
                if key not in {"derivatives", "stems"}
            }
            context["music_analysis"]["stem_kinds"] = [
                item.get("kind")
                for item in music.get("stems") or []
                if item.get("kind")
            ]
            has_audio_evidence = True
        except ValueError:
            raise
        except Exception as error:
            context["music_analysis"] = {
                "status": "failed",
                "error": str(error)[:1000],
            }
    if has_audio_evidence:
        context["expected_evidence_mode"] = "audio_content"


def _prepare_media_context(
    asset: dict[str, Any],
) -> tuple[dict[str, Any], list[Path], Path]:
    source = Path(str(asset["source_path"]))
    metadata = asset.get("media_metadata") or {}
    kinds = {
        str(stream.get("codec_type") or "")
        for stream in metadata.get("streams", [])
        if isinstance(stream, dict)
    }
    images: list[Path] = []
    thumbnail = Path(str(asset.get("thumbnail_path") or ""))
    if thumbnail.is_file():
        images.append(thumbnail)
    is_still_image = _is_still_image(source, metadata)
    context: dict[str, Any] = {
        "sampling": "verified local derivatives only",
        "media_mode": "still_image" if is_still_image else "time_based",
    }
    executable = os.environ.get("BEACON_FFMPEG") or shutil.which("ffmpeg")
    stage_callback = asset.get("stage_callback")
    temp_root = Path(tempfile.mkdtemp(prefix="beacon-analysis-"))
    if is_still_image:
        context["still_image_derivatives"] = len(images)
        if images:
            context["expected_evidence_mode"] = "visual_content"
    elif executable and "video" in kinds:
        if callable(stage_callback):
            stage_callback("preparing_visual_context")
        images.clear()
        duration = _duration_seconds(metadata)
        times = (
            [duration * fraction for fraction in (0.08, 0.25, 0.42, 0.59, 0.76, 0.92)]
            if duration > 1 else [0]
        )
        sampled = []
        for index, second in enumerate(times):
            destination = temp_root / f"frame-{index}.jpg"
            completed = subprocess.run(
                [
                    executable, "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{second:.3f}", "-i", str(source), "-frames:v", "1",
                    "-vf", "scale=960:-2:force_original_aspect_ratio=decrease",
                    str(destination),
                ],
                capture_output=True,
                timeout=120,
                check=False,
                creationflags=hidden_creation_flags(),
            )
            if completed.returncode == 0 and destination.is_file():
                images.append(destination)
                sampled.append(round(second, 3))
        if not images:
            destination = temp_root / "frame-fallback.jpg"
            completed = subprocess.run(
                [
                    executable, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(source), "-frames:v", "1",
                    "-vf", "scale=960:-2:force_original_aspect_ratio=decrease",
                    str(destination),
                ],
                capture_output=True,
                timeout=120,
                check=False,
                creationflags=hidden_creation_flags(),
            )
            if completed.returncode == 0 and destination.is_file():
                images.append(destination)
                sampled.append(0.0)
        context["video_sample_seconds"] = sampled
        if _all_images_uniformly_near_black(images):
            images.clear()
            context["visual_sampling_outcome"] = "uniformly_near_black"
        elif images:
            context["expected_evidence_mode"] = "visual_content"
    if (
        executable
        and "audio" in kinds
        and context.get("expected_evidence_mode") != "visual_content"
    ):
        _append_audio_context(
            context=context,
            images=images,
            temp_root=temp_root,
            executable=executable,
            source=source,
            asset=asset,
            stage_callback=stage_callback,
        )
    if "expected_evidence_mode" not in context:
        preview = read_text_preview(source, max_bytes=64 * 1024)
        if preview is not None and preview.text.strip():
            excerpt, excerpted = _analysis_excerpt(
                preview.text,
                limit=16_000,
            )
            context["text_content"] = {
                "encoding": preview.encoding,
                "excerpt": excerpt,
                "excerpted": excerpted or preview.truncated,
            }
            context["expected_evidence_mode"] = "text_content"
    return context, images, temp_root


def _run_local_analysis_job(
    db_path: Path,
    job_id: str,
    *,
    analyzer: Callable[[str, str, dict[str, Any]], dict[str, Any]] = _default_analyzer,
    progress_callback: Callable[[], None] | None = None,
    stop_on_item_error: bool = False,
) -> LocalAnalysisRunResult:
    recover_interrupted_managed_moves(db_path)
    recover_local_analysis_jobs(db_path)
    with connect(db_path) as connection:
        job_row = connection.execute(
            "SELECT * FROM local_analysis_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if job_row is None:
            raise LookupError("analysis job not found")
        job = dict(job_row)
        if job["state"] == "complete":
            counts = _counts(connection, job_id)
            return LocalAnalysisRunResult(
                job_id,
                "complete",
                counts["complete"],
                counts["failed"],
                counts["excluded"],
                counts["pending"],
                job["analysis_run_id"],
            )
        connection.execute(
            """
            UPDATE local_analysis_jobs SET state='running',cancel_requested=0,
              started_at=COALESCE(started_at,?),updated_at=?,error=NULL,
              worker_pid=?,current_stage=NULL,current_stage_updated_at=?
              WHERE id=?
            """,
            (_utc_now(), _utc_now(), os.getpid(), _utc_now(), job_id),
        )

    while True:
        with connect(db_path) as connection:
            job = dict(connection.execute(
                "SELECT * FROM local_analysis_jobs WHERE id=?", (job_id,)
            ).fetchone())
            if job["cancel_requested"]:
                connection.execute(
                    """
                    UPDATE local_analysis_jobs
                    SET state='cancelled',current_asset_id=NULL,
                        current_stage=NULL,current_stage_updated_at=?,
                        worker_pid=NULL,updated_at=?
                    WHERE id=?
                    """,
                    (_utc_now(), _utc_now(), job_id),
                )
                counts = _counts(connection, job_id)
                return LocalAnalysisRunResult(
                    job_id,
                    "cancelled",
                    counts["complete"],
                    counts["failed"],
                    counts["excluded"],
                    counts["pending"],
                    None,
                )
            item_row = connection.execute(
                "SELECT * FROM local_analysis_items WHERE job_id=? AND state='pending' ORDER BY source_path COLLATE NOCASE LIMIT 1",
                (job_id,),
            ).fetchone()
            if item_row is None:
                break
            item = dict(item_row)
            asset = connection.execute(
                """
                SELECT assets.size_bytes,assets.media_metadata_json,
                       derivatives.path thumbnail_path,
                       derivatives.sha256 thumbnail_sha256
                FROM assets
                LEFT JOIN derivatives
                  ON derivatives.asset_id=assets.id
                 AND derivatives.kind='thumbnail'
                 AND derivatives.state='complete'
                WHERE assets.id=? AND assets.sha256=?
                """,
                (item["asset_id"], item["source_sha256"]),
            ).fetchone()
            asset = dict(asset) if asset is not None else None
            connection.execute(
                """
                UPDATE local_analysis_items
                SET state='running',attempts=attempts+1,started_at=?,
                    error=NULL,excluded_reason=NULL
                WHERE id=?
                """,
                (_utc_now(), item["id"]),
            )
            connection.execute(
                """
                UPDATE local_analysis_jobs
                SET current_asset_id=?,current_stage='verifying_source',
                    current_stage_updated_at=?,updated_at=?
                WHERE id=?
                """,
                (item["asset_id"], _utc_now(), _utc_now(), job_id),
            )
        item_source = _resolve_item_source(
            db_path,
            asset_id=str(item["asset_id"]),
            stored_path=str(item["source_path"]),
        )
        exclusion_reason = _artifact_exclusion_reason(item_source)
        if exclusion_reason:
            _complete_analysis_exclusion(
                db_path,
                str(item["id"]),
                exclusion_reason,
            )
            if progress_callback:
                progress_callback()
            continue
        try:
            # AGENTS.md section 10: no per-item failure may abort a batch.
            # Catalog drift is one item's problem, so it is raised inside
            # this try and recorded like any other per-item failure.
            if asset is None:
                raise ValueError(f"catalog checksum changed for {item['asset_id']}")
            source = item_source
            if not source.exists():
                raise FileNotFoundError(str(source))
            if sha256_file(source) != item["source_sha256"]:
                raise ValueError("source bytes changed since cataloging")
            exclusion_reason = _artifact_exclusion_reason(
                source,
                size_bytes=int(asset["size_bytes"]),
                source_sha256=str(item["source_sha256"]),
            )
            if exclusion_reason:
                _complete_analysis_exclusion(
                    db_path,
                    str(item["id"]),
                    exclusion_reason,
                )
                if progress_callback:
                    progress_callback()
                continue
            media_metadata = json.loads(
                asset.get("media_metadata_json") or "{}"
            )
            media_metadata = _refresh_media_metadata(
                db_path,
                asset_id=str(item["asset_id"]),
                source_sha256=str(item["source_sha256"]),
                source=source,
                metadata=media_metadata,
            )
            if (
                _is_still_image(source, media_metadata)
                and not asset.get("thumbnail_path")
            ):
                _set_job_stage(
                    db_path,
                    job_id,
                    (
                        "preparing_raw_preview"
                        if source.suffix.lower() in RAW_EXTENSIONS
                        else "preparing_image_preview"
                    ),
                )
                generated = ensure_thumbnail(
                    source,
                    db_path,
                    asset_id=str(item["asset_id"]),
                    source_sha256=str(item["source_sha256"]),
                    media_metadata=media_metadata,
                )
                if generated is None:
                    raise RuntimeError(
                        "Still-image visual derivative could not be generated; "
                        "contextual analysis was stopped to prevent guessing"
                    )
                asset["thumbnail_path"] = generated.path
                asset["thumbnail_sha256"] = generated.sha256
            result = analyzer(
                job["endpoint"],
                job["model"],
                {
                    **item,
                    "db_path": str(db_path),
                    "size_bytes": int(asset["size_bytes"]),
                    "media_metadata": media_metadata,
                    "thumbnail_path": asset["thumbnail_path"],
                    "stage_callback": (
                        lambda stage: _set_job_stage(db_path, job_id, stage)
                    ),
                },
            )
            provenance_inputs = [
                {"kind": "catalog_identity", "sha256": item["source_sha256"]},
                {"kind": "verified_local_content_extraction"},
            ]
            if asset["thumbnail_path"]:
                provenance_inputs.append(
                    {
                        "kind": "verified_local_thumbnail",
                        "sha256": asset["thumbnail_sha256"],
                    }
                )
            confidence, normalization_note = _normalize_confidence(
                result.pop("confidence")
            )
            payload, payload_note = _normalize_payload(result)
            candidate = {
                "asset_id": item["asset_id"],
                "source_sha256": item["source_sha256"],
                "analysis_kind": "contextual_metadata",
                "confidence": confidence,
                "payload": payload,
                "provenance": {
                    "inputs": provenance_inputs,
                    "limitations": ["No source media bytes were sent outside ATLAS."],
                },
            }
            notes = [
                note for note in (normalization_note, payload_note) if note
            ]
            if notes:
                candidate["provenance"]["normalizations"] = notes
            _validate_content_candidate(candidate)
            with connect(db_path) as connection:
                connection.execute(
                    """
                    UPDATE local_analysis_items
                    SET state='complete',result_json=?,error=NULL,
                        excluded_reason=NULL,completed_at=?
                    WHERE id=?
                    """,
                    (_canonical_json(candidate), _utc_now(), item["id"]),
                )
        except Exception as error:
            with connect(db_path) as connection:
                connection.execute(
                    """
                    UPDATE local_analysis_items
                    SET state='failed',error=?,excluded_reason=NULL,
                        completed_at=?
                    WHERE id=?
                    """,
                    (str(error)[:2000], _utc_now(), item["id"]),
                )
                if stop_on_item_error:
                    connection.execute(
                        """
                        UPDATE local_analysis_jobs
                        SET state='failed',error=?,current_asset_id=NULL,
                            current_stage=NULL,current_stage_updated_at=?,
                            worker_pid=NULL,updated_at=?
                        WHERE id=?
                        """,
                        (
                            str(error)[:2000],
                            _utc_now(),
                            _utc_now(),
                            job_id,
                        ),
                    )
            if stop_on_item_error:
                raise
        if progress_callback:
            progress_callback()

    _set_job_stage(db_path, job_id, "validating_results")
    with connect(db_path) as connection:
        job = dict(connection.execute(
            "SELECT * FROM local_analysis_jobs WHERE id=?", (job_id,)
        ).fetchone())
        completed_rows = connection.execute(
            """
            SELECT id,asset_id,source_path,result_json,excluded_reason
            FROM local_analysis_items
            WHERE job_id=? AND state='complete' ORDER BY asset_id
            """,
            (job_id,),
        ).fetchall()
        imported_rows = connection.execute(
                """
                SELECT results.asset_id,runs.id AS run_id,runs.scope_json
                FROM analysis_results results
                JOIN analysis_runs runs ON runs.id=results.run_id
                """
            ).fetchall()
        matching_imports = [
            row for row in imported_rows
            if json.loads(row["scope_json"] or "{}").get("job_id") == job_id
        ]
        already_imported = {row["asset_id"] for row in matching_imports}
        existing_run_id = (
            matching_imports[0]["run_id"] if matching_imports else None
        )
        results = []
        candidates = []
        for row in completed_rows:
            exclusion_reason = (
                row["excluded_reason"]
                or _artifact_exclusion_reason(row["source_path"])
            )
            if exclusion_reason:
                connection.execute(
                    """
                    UPDATE local_analysis_items SET excluded_reason=?,error=NULL
                    WHERE id=?
                    """,
                    (exclusion_reason, row["id"]),
                )
                continue
            try:
                if not row["result_json"]:
                    raise ValueError("completed item has no result")
                candidate = json.loads(row["result_json"])
                confidence, normalization_note = _normalize_confidence(
                    candidate.get("confidence")
                )
                candidate["confidence"] = confidence
                payload, payload_note = _normalize_payload(
                    candidate.get("payload")
                )
                candidate["payload"] = payload
                if normalization_note:
                    candidate.setdefault("provenance", {}).setdefault(
                        "normalizations", []
                    ).append(normalization_note)
                if payload_note:
                    candidate.setdefault("provenance", {}).setdefault(
                        "normalizations", []
                    ).append(payload_note)
                _validate_content_candidate(candidate)
            except Exception as error:
                connection.execute(
                    """
                    UPDATE local_analysis_items
                    SET state='failed',error=?,excluded_reason=NULL
                    WHERE id=?
                    """,
                    (
                        "Completed result rejected before publication: "
                        f"{str(error)[:1900]}",
                        row["id"],
                    ),
                )
                continue
            connection.execute(
                """
                UPDATE local_analysis_items
                SET result_json=?,error=NULL,excluded_reason=NULL
                WHERE id=?
                """,
                (_canonical_json(candidate), row["id"]),
            )
            candidates.append(candidate)
            if row["asset_id"] not in already_imported:
                results.append(candidate)
        counts = _counts(connection, job_id)
    run_id = existing_run_id
    if results:
        _set_job_stage(db_path, job_id, "publishing_results")
        imported = import_analysis_manifest(
            db_path,
            {
                "analyzer": f"Beacon local adapter ({job['model']})",
                "analyzer_version": "1",
                "policy_version": job["policy_version"],
                "execution_location": job["endpoint"],
                "external_inference": False,
                "authorization": "Local-only analysis requested in the native Beacon app.",
                "scope": {"job_id": job_id, "scope_sha256": job["scope_sha256"]},
                "results": results,
            },
        )
        run_id = imported.run_id
        with connect(db_path) as connection:
            connection.execute(
                """
                UPDATE local_analysis_jobs
                SET analysis_run_id=?,updated_at=?
                WHERE id=?
                """,
                (run_id, _utc_now(), job_id),
            )
    placement_failures: list[dict[str, str]] = []
    finalization_failures: list[dict[str, str]] = []
    blocked_placement_directories: set[str] = set()
    deferred_placements = 0
    skipped_artifact_placements = 0
    # The structural placement guard. Both of this run's movement sites are
    # gated on this one answer, read from the job row: the managed placement
    # loop immediately below, and the settle step further down. Neither is
    # left merely unreachable.
    may_place = job_may_place(job)
    scope_path_prefix = normalized_scope_path_prefix(job["scope_path_prefix"])
    if not may_place:
        _record_placement_guard(
            db_path,
            job_id=job_id,
            scope_kind=str(job["scope_kind"] or ""),
            item_count=len(candidates),
        )
        _set_job_stage(db_path, job_id, "placement_skipped_for_scope")
    if run_id and may_place:
        for candidate in candidates:
            # AGENTS.md section 10: no per-item failure in a batch may
            # abort the batch. One asset's metadata or placement problem
            # must not stop publication for every item that succeeded.
            try:
                with connect(db_path) as connection:
                    now = _utc_now()
                    connection.execute(
                        """
                        UPDATE local_analysis_jobs
                        SET current_asset_id=?,current_stage='writing_metadata',
                            current_stage_updated_at=?,updated_at=?
                        WHERE id=?
                        """,
                        (candidate["asset_id"], now, now, job_id),
                    )
                if not _analysis_metadata_applied(
                    db_path,
                    candidate["asset_id"],
                    run_id,
                ):
                    apply_analysis_metadata(
                        db_path,
                        candidate["asset_id"],
                        candidate["payload"],
                        run_id=run_id,
                    )
                with connect(db_path) as connection:
                    locations = connection.execute(
                        """
                        SELECT path AS source_path FROM locations
                        WHERE asset_id=?
                        ORDER BY
                          CASE WHEN path LIKE ? THEN 0 ELSE 1 END,
                          path COLLATE NOCASE
                        """,
                        (
                            candidate["asset_id"],
                            f"{inbox_root()}{os.sep}%",
                        ),
                    ).fetchall()
                if not locations:
                    raise RuntimeError("Analyzed source location could not be recovered.")
                last_move = None
                for location in locations:
                    source_path = Path(location["source_path"])
                    # Second layer, independent of the job's scope. A
                    # generated artifact is regenerable cache and is never
                    # placed into the archive, whichever scope enrolled it.
                    # Unreachable while exclusion runs first, which is the
                    # point: it holds if that ever changes.
                    if is_hidden_support_path(source_path):
                        skipped_artifact_placements += 1
                        continue
                    placement = analysis_placement_for(source_path)
                    destination_key = (
                        str(placement.destination_directory).casefold()
                        if placement.destination_directory is not None
                        else None
                    )
                    if (
                        destination_key is not None
                        and destination_key in blocked_placement_directories
                    ):
                        deferred_placements += 1
                        continue
                    _set_job_stage(db_path, job_id, "moving_to_archive")
                    try:
                        moved, placement_reason = commit_analyzed_file(
                            db_path,
                            asset_id=candidate["asset_id"],
                            source_path=source_path,
                            confidence=float(candidate["confidence"]),
                            analysis_run_id=run_id,
                        )
                    except Exception as placement_error:
                        if (
                            destination_directory_blocked(placement_error)
                            and destination_key is not None
                        ):
                            blocked_placement_directories.add(destination_key)
                        placement_failures.append(
                            {
                                "asset_id": str(candidate["asset_id"]),
                                "source_path": str(source_path),
                                "error": str(placement_error)[:1900],
                            }
                        )
                        try:
                            _record_analysis_placement_failure(
                                db_path,
                                run_id=run_id,
                                asset_id=str(candidate["asset_id"]),
                                source_path=source_path,
                                error=placement_error,
                            )
                        except Exception:
                            pass
                        continue
                    if moved is None and placement_needs_clarification(source_path):
                        seed_threads(
                            db_path,
                            [
                                {
                                    "seed_key": _analysis_placement_seed_key(
                                        "clarification",
                                        run_id,
                                        str(candidate["asset_id"]),
                                        source_path,
                                    ),
                                    "subject": "Where should this analyzed file live?",
                                    "body": (
                                        "Beacon completed analysis but could not infer "
                                        f"a reliable final home for {source_path}. "
                                        f"{placement_reason}"
                                    ),
                                    "kind": "clarification",
                                    "priority": "normal",
                                    "requires_approval": False,
                                    "asset_id": candidate["asset_id"],
                                }
                            ],
                        )
                    elif moved is not None:
                        last_move = moved
                if last_move is not None:
                    apply_analysis_organization_path(
                        db_path,
                        candidate["asset_id"],
                        Path(last_move.destination_path).parent,
                        run_id=run_id,
                    )
            except Exception as finalize_error:
                finalization_failures.append(
                    {
                        "asset_id": str(candidate["asset_id"]),
                        "error": str(finalize_error)[:1900],
                    }
                )
                _record_finalization_failure(
                    db_path,
                    run_id=run_id,
                    job_id=job_id,
                    asset_id=str(candidate["asset_id"]),
                    error=finalize_error,
                )
                continue
    if finalization_failures:
        counts["failed"] += len(finalization_failures)
        counts["complete"] = max(0, counts["complete"] - len(finalization_failures))
    settled = None
    # The guard's second site. Settle is scoped to this job's path prefix, so
    # a folder-scoped job drains its own folder and nothing else, and it is
    # gated on the same one answer as placement: a cache-only job moves
    # nothing at all.
    #
    # It is deliberately NOT gated on the job's failure or pending counts.
    # That gate is what left the Inbox full: one failed item out of a thousand
    # skipped placement for every other item in the job, which is the
    # per-item-failure-aborts-the-batch defect AGENTS.md forbids. A failed item
    # is settled to the review zone; it no longer strands its neighbours.
    if may_place:
        _set_job_stage(db_path, job_id, "settling_inbox")
        # The stage line is the only progress an operator sees, and a settle
        # over a large folder runs for hours. Writing it per item would be
        # thousands of needless catalog writes, so it is throttled to a few
        # seconds: often enough that the window never looks hung, rarely
        # enough that it costs nothing against the work itself.
        last_reported = [0.0]

        def report_settle(done: int, total: int, outcome: str) -> None:
            now = time.monotonic()
            if done != 1 and done != total and now - last_reported[0] < 3.0:
                return
            last_reported[0] = now
            _set_job_stage(
                db_path,
                job_id,
                f"settling_inbox {done}/{total} -> {outcome}",
            )

        settled = settle_inbox_items(
            db_path,
            path_prefix=scope_path_prefix,
            requested_by="Beacon local analyzer",
            authorization_note=f"analysis_run={run_id}; job={job_id}.",
            progress_callback=report_settle,
        )
    # An excluded item is work that succeeded: the rule decided it, no model
    # was needed, and the settle step moved it. Reading only "complete" here
    # meant a job whose every item was excluded by rule reported as wholly
    # failed the moment one item failed, which is now the ordinary shape of a
    # job that drains an Inbox rather than an unusual one.
    productive = counts["complete"] + counts["excluded"]
    state = (
        "complete"
        if counts["failed"] == 0
        else ("partial" if productive else "failed")
    )
    # A settle that could not move something does not fail the analysis: the
    # analysis is done. It makes the job partial so the count is visible and
    # the operator knows the Inbox did not fully clear.
    if settled is not None and settled.skipped_reasons:
        state = "partial"
    error = None
    if settled is not None and settled.skipped_reasons:
        left = sum(settled.skipped_reasons.values())
        error = f"{left} item(s) could not leave the Inbox"
    elif state != "complete":
        error = f"{counts['failed']} item(s) failed"
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE local_analysis_jobs SET state=?,current_asset_id=NULL,
              current_stage=NULL,current_stage_updated_at=?,
              completed_at=?,updated_at=?,analysis_run_id=?,error=?,
              worker_pid=NULL WHERE id=?
            """,
            (
                state, _utc_now(), _utc_now(), _utc_now(), run_id,
                error,
                job_id,
            ),
        )
        record_event(
            connection,
            kind="local_analysis_job",
            state=state,
            message=f"Local-only analysis finished: {counts['complete']} candidates",
            details={
                "job_id": job_id,
                "analysis_run_id": run_id,
                "placement_failures": len(placement_failures),
                "finalization_failures": len(finalization_failures),
                "deferred_placements": deferred_placements,
                "placement_allowed": may_place,
                "placement_skipped_reason": (
                    None if may_place else PLACEMENT_SKIPPED_FOR_SCOPE
                ),
                "skipped_artifact_placements": skipped_artifact_placements,
                "settle_attempted": settled.attempted if settled else 0,
                "settle_moved": settled.moved if settled else 0,
                "settle_outcomes": settled.outcomes if settled else {},
                "settle_left_behind": (
                    settled.skipped_reasons if settled else {}
                ),
                "settle_not_terminal": (
                    settled.not_terminal if settled else 0
                ),
                "removed_directories": (
                    settled.removed_directories if settled else 0
                ),
                **counts,
            },
        )
    return LocalAnalysisRunResult(
        job_id,
        state,
        counts["complete"],
        counts["failed"],
        counts["excluded"],
        counts["pending"],
        run_id,
    )


def _terminalize_analysis_failure(
    db_path: Path,
    job_id: str,
    error: Exception,
) -> None:
    """Never leave a failed worker impersonating a live analysis job."""
    message = f"Analysis finalization failed: {str(error)[:1900]}"
    with connect(db_path) as connection:
        migrate(connection)
        job = connection.execute(
            "SELECT state,analysis_run_id FROM local_analysis_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if job is None or job["state"] in {
            "complete",
            "partial",
            "failed",
            "cancelled",
        }:
            return
        run_id = job["analysis_run_id"]
        if not run_id:
            for row in connection.execute(
                "SELECT id,scope_json FROM analysis_runs"
            ):
                try:
                    scope = json.loads(row["scope_json"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    continue
                if scope.get("job_id") == job_id:
                    run_id = row["id"]
                    break
        state = "partial" if run_id else "failed"
        now = _utc_now()
        connection.execute(
            """
            UPDATE local_analysis_jobs
            SET state=?,current_asset_id=NULL,current_stage=NULL,
                current_stage_updated_at=?,completed_at=?,updated_at=?,
                analysis_run_id=COALESCE(analysis_run_id,?),
                error=?,worker_pid=NULL
            WHERE id=?
            """,
            (state, now, now, now, run_id, message, job_id),
        )
        record_event(
            connection,
            kind="local_analysis_job",
            state=state,
            message=message,
            details={"job_id": job_id, "analysis_run_id": run_id},
        )


def run_local_analysis_job(
    db_path: Path,
    job_id: str,
    *,
    analyzer: Callable[[str, str, dict[str, Any]], dict[str, Any]] = _default_analyzer,
    progress_callback: Callable[[], None] | None = None,
    stop_on_item_error: bool = False,
) -> LocalAnalysisRunResult:
    try:
        return _run_local_analysis_job(
            db_path,
            job_id,
            analyzer=analyzer,
            progress_callback=progress_callback,
            stop_on_item_error=stop_on_item_error,
        )
    except Exception as error:
        try:
            _terminalize_analysis_failure(db_path, job_id, error)
        except Exception:
            pass
        raise
