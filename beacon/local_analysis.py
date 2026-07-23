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

from .analysis import import_analysis_manifest
from .catalog import sha256_file
from .database import connect, migrate, record_event
from .metadata import apply_analysis_metadata

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
POLICY_VERSION = "beacon-local-multimodal-v2"
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
    pending: int
    analysis_run_id: str | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


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


def analysis_scope_preview(db_path: Path, *, include_analyzed: bool = False) -> dict[str, Any]:
    with connect(db_path) as connection:
        migrate(connection)
        where = "" if include_analyzed else """
            WHERE NOT EXISTS (
                SELECT 1 FROM analysis_results result
                WHERE result.asset_id = assets.id
                  AND result.analysis_kind = 'contextual_metadata'
                  AND result.review_state IN ('candidate', 'approved')
            )
        """
        rows = connection.execute(
            f"""
            SELECT assets.id, assets.sha256, assets.size_bytes,
                   MIN(locations.path) AS source_path,
                   assets.media_metadata_json
            FROM assets JOIN locations ON locations.asset_id = assets.id
            {where}
            GROUP BY assets.id
            ORDER BY source_path COLLATE NOCASE
            """
        ).fetchall()
    visual = audio = other = 0
    for row in rows:
        metadata = json.loads(row["media_metadata_json"] or "{}")
        kinds = {
            str(stream.get("codec_type") or "")
            for stream in metadata.get("streams", [])
            if isinstance(stream, dict)
        }
        if "video" in kinds or metadata.get("kind") == "image":
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
    requested_by: str = "human",
) -> str:
    model = model.strip()
    if not model:
        raise ValueError("choose a local model")
    preview = analysis_scope_preview(db_path, include_analyzed=include_analyzed)
    job_id = str(uuid.uuid4())
    now = _utc_now()
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT assets.id, assets.sha256, MIN(locations.path) AS source_path
            FROM assets JOIN locations ON locations.asset_id = assets.id
            WHERE ? OR NOT EXISTS (
                SELECT 1 FROM analysis_results result
                WHERE result.asset_id = assets.id
                  AND result.analysis_kind = 'contextual_metadata'
                  AND result.review_state IN ('candidate', 'approved')
            )
            GROUP BY assets.id ORDER BY source_path COLLATE NOCASE
            """,
            (int(include_analyzed),),
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
            },
        )
    return job_id


def _counts(connection: Any, job_id: str) -> dict[str, int]:
    values = {
        row["state"]: int(row["count"])
        for row in connection.execute(
            "SELECT state, COUNT(*) count FROM local_analysis_items WHERE job_id=? GROUP BY state",
            (job_id,),
        )
    }
    return {key: values.get(key, 0) for key in ("complete", "failed", "pending", "running")}


def list_local_analysis_jobs(db_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            """
            SELECT jobs.*,
              SUM(CASE WHEN items.state='complete' THEN 1 ELSE 0 END) completed_count,
              SUM(CASE WHEN items.state='failed' THEN 1 ELSE 0 END) failed_count,
              SUM(CASE WHEN items.state='pending' THEN 1 ELSE 0 END) pending_count,
              SUM(CASE WHEN items.state='running' THEN 1 ELSE 0 END) running_count
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
                "UPDATE local_analysis_jobs SET state='paused',current_asset_id=NULL,worker_pid=NULL,updated_at=? WHERE id=?",
                (_utc_now(), row["id"]),
            )
        return len(abandoned)


def _process_is_alive(value: object) -> bool:
    try:
        pid = int(value or 0)
        if pid <= 0:
            return False
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
            SET state='pending',error=NULL,started_at=NULL,completed_at=NULL
            WHERE job_id=? AND state='failed'
            """,
            (job_id,),
        )
        connection.execute(
            """
            UPDATE local_analysis_jobs
            SET state='paused',cancel_requested=0,current_asset_id=NULL,
                completed_at=NULL,updated_at=?,error=NULL
            WHERE id=?
            """,
            (_utc_now(), job_id),
        )
        return int(cursor.rowcount)


def _default_analyzer(
    endpoint: str, model: str, asset: dict[str, Any]
) -> dict[str, Any]:
    prompt = (
        "You are Beacon, a local archive and stock-footage metadata specialist. "
        "Use all supplied sampled frames, transcript, spectrogram, filename, and "
        "verified technical context. Be highly descriptive and produce as many "
        "specific, relevant search tags as useful (up to 100): subjects, actions, "
        "apparent age group, apparent gender presentation (never gender identity), "
        "facial expression, wardrobe, setting, weather, lighting, dominant colors, "
        "shot size, angle, composition, camera movement, copy space, mood, concepts, "
        "speech topics, sound sources, music character, and likely B-roll uses. "
        "Do not identify an unnamed person, invent dialogue, rights, relationships, "
        "or events. Distinguish observation from uncertainty. A managed archive move "
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
            "title", "description", "media_category", "tags", "privacy_flags",
            "organization_suggestion", "confidence",
            "stock_metadata",
        ],
    }
    media_context, image_paths, temporary_root = _prepare_media_context(asset)
    content = _canonical_json(
        {
            "source_filename": Path(asset["source_path"]).name,
            "source_path_context": str(Path(asset["source_path"]).parent),
            "size_bytes": asset["size_bytes"],
            "verified_media_metadata": asset["media_metadata"],
            "local_media_context": media_context,
        }
    )
    message: dict[str, Any] = {"role": "user", "content": content}
    encoded_images = []
    for image_path in image_paths:
        if image_path.is_file() and image_path.stat().st_size <= 8 * 1024 * 1024:
            encoded_images.append(base64.b64encode(image_path.read_bytes()).decode("ascii"))
    if encoded_images:
        message["images"] = encoded_images
    try:
        response = _request_json(
            endpoint,
            "/api/chat",
            {
                "model": model,
                "messages": [{"role": "system", "content": prompt}, message],
                "format": schema,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 4096},
            },
            timeout=600,
        )
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
    message = response.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValueError("local model returned no structured message")
    result = json.loads(message["content"])
    if not isinstance(result, dict):
        raise ValueError("local model result is not an object")
    return result


def _duration_seconds(metadata: dict[str, Any]) -> float:
    try:
        return max(0.0, float((metadata.get("format") or {}).get("duration") or 0))
    except (TypeError, ValueError):
        return 0.0


def _transcribe_audio(source: Path) -> dict[str, Any]:
    global _WHISPER_MODEL
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
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    if len(text) > 8000:
        third = 2600
        middle = max(0, (len(text) - third) // 2)
        text = (
            text[:third]
            + "\n[...middle excerpt...]\n"
            + text[middle:middle + third]
            + "\n[...ending excerpt...]\n"
            + text[-third:]
        )
    return {
        "status": "complete",
        "language": getattr(info, "language", ""),
        "language_probability": getattr(info, "language_probability", None),
        "transcript": text,
        "excerpted": "[...middle excerpt...]" in text,
    }


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
    context: dict[str, Any] = {"sampling": "verified local derivatives only"}
    executable = os.environ.get("BEACON_FFMPEG") or shutil.which("ffmpeg")
    temp_root = Path(tempfile.mkdtemp(prefix="beacon-analysis-"))
    if executable and "video" in kinds:
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
        context["video_sample_seconds"] = sampled
    elif executable and "audio" in kinds:
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
        context["speech_analysis"] = _transcribe_audio(source)
    return context, images, temp_root


def run_local_analysis_job(
    db_path: Path,
    job_id: str,
    *,
    analyzer: Callable[[str, str, dict[str, Any]], dict[str, Any]] = _default_analyzer,
    progress_callback: Callable[[], None] | None = None,
) -> LocalAnalysisRunResult:
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
            return LocalAnalysisRunResult(job_id, "complete", counts["complete"], counts["failed"], counts["pending"], job["analysis_run_id"])
        connection.execute(
            """
            UPDATE local_analysis_jobs SET state='running',cancel_requested=0,
              started_at=COALESCE(started_at,?),updated_at=?,error=NULL,
              worker_pid=? WHERE id=?
            """,
            (_utc_now(), _utc_now(), os.getpid(), job_id),
        )

    while True:
        with connect(db_path) as connection:
            job = dict(connection.execute(
                "SELECT * FROM local_analysis_jobs WHERE id=?", (job_id,)
            ).fetchone())
            if job["cancel_requested"]:
                connection.execute(
                    "UPDATE local_analysis_jobs SET state='cancelled',current_asset_id=NULL,worker_pid=NULL,updated_at=? WHERE id=?",
                    (_utc_now(), job_id),
                )
                counts = _counts(connection, job_id)
                return LocalAnalysisRunResult(job_id, "cancelled", counts["complete"], counts["failed"], counts["pending"], None)
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
            connection.execute(
                "UPDATE local_analysis_items SET state='running',attempts=attempts+1,started_at=?,error=NULL WHERE id=?",
                (_utc_now(), item["id"]),
            )
            connection.execute(
                "UPDATE local_analysis_jobs SET current_asset_id=?,updated_at=? WHERE id=?",
                (item["asset_id"], _utc_now(), job_id),
            )
        try:
            source = Path(item["source_path"])
            if not source.exists():
                raise FileNotFoundError(str(source))
            if sha256_file(source) != item["source_sha256"]:
                raise ValueError("source bytes changed since cataloging")
            result = analyzer(
                job["endpoint"],
                job["model"],
                {
                    **item,
                    "size_bytes": int(asset["size_bytes"]),
                    "media_metadata": json.loads(asset["media_metadata_json"] or "{}"),
                    "thumbnail_path": asset["thumbnail_path"],
                },
            )
            provenance_inputs = [
                {"kind": "catalog_identity", "sha256": item["source_sha256"]},
                {"kind": "verified_technical_metadata"},
                {"kind": "source_path_context"},
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
            with connect(db_path) as connection:
                connection.execute(
                    "UPDATE local_analysis_items SET state='complete',result_json=?,completed_at=? WHERE id=?",
                    (_canonical_json(candidate), _utc_now(), item["id"]),
                )
        except Exception as error:
            with connect(db_path) as connection:
                connection.execute(
                    "UPDATE local_analysis_items SET state='failed',error=?,completed_at=? WHERE id=?",
                    (str(error)[:2000], _utc_now(), item["id"]),
                )
        if progress_callback:
            progress_callback()

    with connect(db_path) as connection:
        job = dict(connection.execute(
            "SELECT * FROM local_analysis_jobs WHERE id=?", (job_id,)
        ).fetchone())
        completed_rows = connection.execute(
            """
            SELECT id,asset_id,result_json FROM local_analysis_items
            WHERE job_id=? AND state='complete' ORDER BY asset_id
            """,
            (job_id,),
        ).fetchall()
        already_imported = {
            row["asset_id"]
            for row in connection.execute(
                """
                SELECT results.asset_id,runs.scope_json
                FROM analysis_results results
                JOIN analysis_runs runs ON runs.id=results.run_id
                """
            )
            if json.loads(row["scope_json"] or "{}").get("job_id") == job_id
        }
        results = []
        for row in completed_rows:
            if row["asset_id"] in already_imported:
                continue
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
            if normalization_note or payload_note:
                connection.execute(
                    """
                    UPDATE local_analysis_items SET result_json=?
                    WHERE id=?
                    """,
                    (_canonical_json(candidate), row["id"]),
                )
            results.append(candidate)
        counts = _counts(connection, job_id)
    run_id = None
    if results:
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
        for candidate in results:
            apply_analysis_metadata(
                db_path,
                candidate["asset_id"],
                candidate["payload"],
                run_id=run_id,
            )
    state = "complete" if counts["failed"] == 0 else ("partial" if counts["complete"] else "failed")
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE local_analysis_jobs SET state=?,current_asset_id=NULL,
              completed_at=?,updated_at=?,analysis_run_id=?,error=?,
              worker_pid=NULL WHERE id=?
            """,
            (
                state, _utc_now(), _utc_now(), run_id,
                None if state == "complete" else f"{counts['failed']} item(s) failed",
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
    return LocalAnalysisRunResult(job_id, state, counts["complete"], counts["failed"], counts["pending"], run_id)
