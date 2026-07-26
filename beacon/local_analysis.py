from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
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
from .database import connect, migrate, record_event
from .desk import seed_threads
from .managed_moves import (
    commit_analyzed_file,
    placement_needs_clarification,
    recover_interrupted_managed_moves,
)
from .media import IMAGE_EXTENSIONS
from .metadata import apply_analysis_metadata, apply_analysis_organization_path
from .music_analysis import analyze_asset_music
from .repository import is_hidden_support_path, support_path_sql
from .text_preview import read_text_preview
from .thumbnails import RAW_EXTENSIONS, ensure_thumbnail
from .transcripts import get_asset_transcript, save_asset_transcript

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
POLICY_VERSION = "beacon-local-content-v4"
_WHISPER_MODEL: Any = None


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


def _normalize_payload(payload: object) -> tuple[dict[str, Any], str | None]:
    if not isinstance(payload, dict):
        raise ValueError("local model payload must be an object")
    result = dict(payload)
    suggestion = result.get("organization_suggestion")
    if isinstance(suggestion, str) and not suggestion.strip():
        result["organization_suggestion"] = (
            "No organization suggestion was produced. Human review is "
            "required; do not move or rename the original."
        )
        return result, (
            "Local model returned an empty organization suggestion; Beacon "
            "inserted a non-operative review-required fallback."
        )
    return result, None


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
) -> dict[str, Any]:
    if scope_kind not in {"all", "raw"}:
        raise ValueError("unsupported analysis scope")
    with connect(db_path) as connection:
        migrate(connection)
        visible_predicate, parameters = support_path_sql("locations.path")
        where = """
            WHERE lower(locations.path) NOT LIKE '%.ds_store'
              AND lower(locations.path) NOT LIKE '%\\desktop.ini'
              AND lower(locations.path) NOT LIKE '%\\thumbs.db'
        """
        where += f" AND ({visible_predicate})"
        if not include_analyzed:
            where += """
              AND NOT EXISTS (
                SELECT 1 FROM analysis_results result
                WHERE result.asset_id = assets.id
                  AND result.analysis_kind = 'contextual_metadata'
                  AND result.review_state IN ('candidate', 'approved')
            )
            """
        if scope_kind == "raw":
            where += " AND (" + " OR ".join(
                "lower(locations.path) LIKE ?" for _ in RAW_EXTENSIONS
            ) + ")"
            parameters.extend(
                f"%{suffix}" for suffix in sorted(RAW_EXTENSIONS)
            )
        rows = connection.execute(
            f"""
            SELECT assets.id, assets.sha256, assets.size_bytes,
                   MIN(locations.path) AS source_path,
                   assets.media_metadata_json
            FROM assets JOIN locations ON locations.asset_id = assets.id
            {where}
            GROUP BY assets.id
            ORDER BY source_path COLLATE NOCASE
            """,
            parameters,
        ).fetchall()
    visual = audio = other = 0
    for row in rows:
        metadata = json.loads(row["media_metadata_json"] or "{}")
        kinds = {
            str(stream.get("codec_type") or "")
            for stream in metadata.get("streams", [])
            if isinstance(stream, dict)
        }
        if (
            "video" in kinds
            or _is_still_image(Path(row["source_path"]), metadata)
        ):
            visual += 1
        elif "audio" in kinds:
            audio += 1
        else:
            other += 1
    digest = hashlib.sha256()
    for row in rows:
        digest.update(f"{row['id']}\0{row['sha256']}\n".encode())
    return {
        "assets": len(rows),
        "bytes": sum(int(row["size_bytes"]) for row in rows),
        "visual": visual,
        "audio": audio,
        "other": other,
        "scope_sha256": digest.hexdigest(),
    }


def create_local_analysis_job(
    db_path: Path,
    *,
    model: str,
    endpoint: str = DEFAULT_ENDPOINT,
    include_analyzed: bool = False,
    scope_kind: str = "all",
    requested_by: str = "human",
) -> str:
    model = model.strip()
    if not model:
        raise ValueError("choose a local model")
    preview = analysis_scope_preview(
        db_path,
        include_analyzed=include_analyzed,
        scope_kind=scope_kind,
    )
    job_id = str(uuid.uuid4())
    now = _utc_now()
    with connect(db_path) as connection:
        scope_clause = ""
        visible_predicate, visible_parameters = support_path_sql(
            "locations.path"
        )
        support_clause = f" AND ({visible_predicate})"
        scope_parameters: list[object] = [
            *visible_parameters,
            int(include_analyzed),
        ]
        if scope_kind == "raw":
            scope_clause = " AND (" + " OR ".join(
                "lower(locations.path) LIKE ?" for _ in RAW_EXTENSIONS
            ) + ")"
            scope_parameters.extend(
                f"%{suffix}" for suffix in sorted(RAW_EXTENSIONS)
            )
        elif scope_kind != "all":
            raise ValueError("unsupported analysis scope")
        rows = connection.execute(
            f"""
            SELECT assets.id, assets.sha256, MIN(locations.path) AS source_path
            FROM assets JOIN locations ON locations.asset_id = assets.id
            WHERE lower(locations.path) NOT LIKE '%.ds_store'
              AND lower(locations.path) NOT LIKE '%\\desktop.ini'
              AND lower(locations.path) NOT LIKE '%\\thumbs.db'
              {support_clause}
              AND (? OR NOT EXISTS (
                SELECT 1 FROM analysis_results result
                WHERE result.asset_id = assets.id
                  AND result.analysis_kind = 'contextual_metadata'
                  AND result.review_state IN ('candidate', 'approved')
              ))
              {scope_clause}
            GROUP BY assets.id ORDER BY source_path COLLATE NOCASE
            """,
            scope_parameters,
        ).fetchall()
        connection.execute(
            """
            INSERT INTO local_analysis_jobs(
                id,state,model,endpoint,policy_version,scope_sha256,total_items,
                requested_by,created_at,updated_at
            ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id, model, endpoint.rstrip("/"), POLICY_VERSION,
                preview["scope_sha256"], len(rows), requested_by, now, now,
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
                                     AND managed.state='complete'
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
                requested_by,created_at,updated_at
            ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?)
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
            "SELECT state FROM local_analysis_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if job is None:
            raise LookupError("analysis job not found")
        if job["state"] == "running":
            raise ValueError("wait for analysis to stop before retrying failures")
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


def _artifact_exclusion_reason(source_path: str | Path) -> str | None:
    if not is_hidden_support_path(source_path):
        return None
    return (
        "Excluded confidently generated cache, autosave, or sidecar artifact; "
        "the original remains cataloged and can be shown as a hidden file."
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
        "visual evidence cannot be interpreted, set evidence_mode to "
        "'unreadable' instead of inventing or falling back to specifications. "
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
            "title": {"type": "string"},
            "description": {"type": "string"},
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
            "media_category": {"type": "string"},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 100,
            },
            "privacy_flags": {"type": "array", "items": {"type": "string"}},
            "organization_suggestion": {"type": "string"},
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
    media_context["visual_evidence_supplied"] = bool(image_paths)
    expected_mode = str(media_context.get("expected_evidence_mode") or "")
    if expected_mode not in CONTENT_EVIDENCE_MODES:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise ValueError(
            "no decodable visual, audio, or text content evidence was available"
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
    try:
        for attempt in range(1, 4):
            retry_note = ""
            if last_error is not None:
                retry_note = (
                    "\nA previous response was rejected: "
                    f"{str(last_error)[:500]}. Re-observe the supplied content "
                    "and return a complete schema-valid JSON object. Do not "
                    "substitute technical metadata."
                )
            try:
                response = _request_json(
                    endpoint,
                    "/api/chat",
                    {
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": prompt + retry_note,
                            },
                            message,
                        ],
                        "format": schema,
                        "stream": False,
                        "options": {
                            "temperature": 0 if attempt == 1 else 0.1,
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
                result = json.loads(response_message["content"])
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
                if (
                    result.get("evidence_mode") != expected_mode
                    or not isinstance(observations, list)
                    or not observations
                    or any(
                        not isinstance(item, str) or not item.strip()
                        for item in observations
                    )
                ):
                    raise ValueError(
                        "local model did not produce "
                        f"{expected_mode.replace('_', '-')} evidence"
                    )
                return result
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                last_error = error
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
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
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
            / "ATLAS" / "Beacon" / "models" / "whisper"
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
                capture_output=True, timeout=120, check=False,
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
                capture_output=True, timeout=120, check=False,
            )
            if completed.returncode == 0 and destination.is_file():
                images.append(destination)
                sampled.append(0.0)
        context["video_sample_seconds"] = sampled
        if images:
            context["expected_evidence_mode"] = "visual_content"
    elif executable and "audio" in kinds:
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
            capture_output=True, timeout=180, check=False,
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
            if asset is None:
                raise ValueError(f"catalog checksum changed for {item['asset_id']}")
            asset = dict(asset)
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
        exclusion_reason = _artifact_exclusion_reason(item["source_path"])
        if exclusion_reason:
            with connect(db_path) as connection:
                connection.execute(
                    """
                    UPDATE local_analysis_items
                    SET state='complete',result_json=NULL,error=NULL,
                        excluded_reason=?,completed_at=?
                    WHERE id=?
                    """,
                    (exclusion_reason, _utc_now(), item["id"]),
                )
            if progress_callback:
                progress_callback()
            continue
        try:
            source = Path(item["source_path"])
            if not source.exists():
                raise FileNotFoundError(str(source))
            if sha256_file(source) != item["source_sha256"]:
                raise ValueError("source bytes changed since cataloging")
            media_metadata = json.loads(
                asset.get("media_metadata_json") or "{}"
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
    if run_id:
        for candidate in candidates:
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
                        r"J:\Inbox\%",
                    ),
                ).fetchall()
            if not locations:
                raise RuntimeError("Analyzed source location could not be recovered.")
            last_move = None
            for location in locations:
                source_path = Path(location["source_path"])
                if not str(source_path).lower().startswith("j:\\inbox\\"):
                    continue
                _set_job_stage(db_path, job_id, "moving_to_archive")
                moved, placement_reason = commit_analyzed_file(
                    db_path,
                    asset_id=candidate["asset_id"],
                    source_path=source_path,
                    confidence=float(candidate["confidence"]),
                    analysis_run_id=run_id,
                )
                if moved is None and placement_needs_clarification(source_path):
                    seed_threads(
                        db_path,
                        [
                            {
                                "seed_key": (
                                    f"analysis-placement:{run_id}:"
                                    f"{candidate['asset_id']}:{source_path}"
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
    state = (
        "complete"
        if counts["failed"] == 0
        else ("partial" if counts["complete"] else "failed")
    )
    error = None
    if state != "complete":
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
            details={"job_id": job_id, "analysis_run_id": run_id, **counts},
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
