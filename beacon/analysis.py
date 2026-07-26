from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import connect, migrate, record_event

MAX_MANIFEST_BYTES = 5 * 1024 * 1024
MAX_RESULTS_PER_MANIFEST = 10_000


@dataclass(frozen=True)
class AnalysisImportResult:
    run_id: str
    result_ids: tuple[str, ...]
    reused: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _required_text(
    mapping: dict[str, Any],
    key: str,
    *,
    max_length: int = 500,
) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    value = value.strip()
    if len(value) > max_length:
        raise ValueError(f"{key} exceeds {max_length} characters")
    return value


def _validate_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    _required_text(value, "title", max_length=300)
    _required_text(value, "description", max_length=4_000)
    _required_text(value, "media_category", max_length=100)
    _required_text(value, "organization_suggestion", max_length=1_000)
    tags = value.get("tags")
    if not isinstance(tags, list) or any(
        not isinstance(tag, str) or not tag.strip() for tag in tags
    ):
        raise ValueError("payload.tags must be a list of non-empty strings")
    if len(tags) > 100:
        raise ValueError("payload.tags cannot contain more than 100 values")
    privacy_flags = value.get("privacy_flags")
    if not isinstance(privacy_flags, list) or any(
        not isinstance(flag, str) or not flag.strip() for flag in privacy_flags
    ):
        raise ValueError(
            "payload.privacy_flags must be a list of non-empty strings"
        )
    return value


def _validate_provenance(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("provenance must be an object")
    inputs = value.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("provenance.inputs must be a non-empty list")
    if any(not isinstance(item, dict) for item in inputs):
        raise ValueError("each provenance input must be an object")
    return value


def validate_analysis_result(result: object) -> dict[str, Any]:
    """Validate one candidate exactly as the durable importer will."""
    if not isinstance(result, dict):
        raise ValueError("each analysis result must be an object")
    asset_id = _required_text(result, "asset_id", max_length=100)
    source_sha256 = _required_text(
        result, "source_sha256", max_length=64
    ).lower()
    if len(source_sha256) != 64 or any(
        character not in "0123456789abcdef"
        for character in source_sha256
    ):
        raise ValueError("source_sha256 must be a lowercase SHA-256 value")
    analysis_kind = _required_text(
        result, "analysis_kind", max_length=100
    )
    confidence = result.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= float(confidence) <= 1
    ):
        raise ValueError("confidence must be a number from 0 through 1")
    return {
        "asset_id": asset_id,
        "source_sha256": source_sha256,
        "analysis_kind": analysis_kind,
        "confidence": float(confidence),
        "payload": _validate_payload(result.get("payload")),
        "provenance": _validate_provenance(result.get("provenance")),
    }


def load_analysis_manifest(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"not a regular manifest file: {path}")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError(
            f"analysis manifest exceeds {MAX_MANIFEST_BYTES} bytes"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid analysis manifest: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("analysis manifest must be an object")
    return value


def import_analysis_manifest(
    db_path: Path,
    manifest: dict[str, Any],
) -> AnalysisImportResult:
    analyzer = _required_text(manifest, "analyzer", max_length=200)
    analyzer_version = _required_text(
        manifest, "analyzer_version", max_length=200
    )
    policy_version = _required_text(
        manifest, "policy_version", max_length=200
    )
    execution_location = _required_text(
        manifest, "execution_location", max_length=300
    )
    external_inference = manifest.get("external_inference")
    if not isinstance(external_inference, bool):
        raise ValueError("external_inference must be true or false")
    authorization = manifest.get("authorization")
    if external_inference:
        if not isinstance(authorization, str) or not authorization.strip():
            raise ValueError(
                "external inference requires an explicit authorization note"
            )
        authorization = authorization.strip()
    elif authorization is not None and not isinstance(authorization, str):
        raise ValueError("authorization must be a string when supplied")

    scope = manifest.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("scope must be an object")
    results = manifest.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("results must be a non-empty list")
    if len(results) > MAX_RESULTS_PER_MANIFEST:
        raise ValueError(
            f"results cannot exceed {MAX_RESULTS_PER_MANIFEST} entries"
        )

    validated: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for result in results:
        candidate = validate_analysis_result(result)
        identity = (
            candidate["asset_id"],
            candidate["analysis_kind"],
        )
        if identity in seen:
            raise ValueError(
                "duplicate result for asset/kind: "
                f"{candidate['asset_id']}/{candidate['analysis_kind']}"
            )
        seen.add(identity)
        validated.append(candidate)

    manifest_sha256 = _sha256_json(manifest)
    run_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"atlas://analysis-run/{manifest_sha256}",
        )
    )
    now = _utc_now()

    with connect(db_path) as connection:
        migrate(connection)
        existing = connection.execute(
            """
            SELECT id FROM analysis_runs WHERE manifest_sha256 = ?
            """,
            (manifest_sha256,),
        ).fetchone()
        if existing is not None:
            result_ids = tuple(
                row["id"]
                for row in connection.execute(
                    """
                    SELECT id FROM analysis_results
                    WHERE run_id = ? ORDER BY asset_id, analysis_kind
                    """,
                    (existing["id"],),
                ).fetchall()
            )
            return AnalysisImportResult(
                run_id=str(existing["id"]),
                result_ids=result_ids,
                reused=True,
            )

        for result in validated:
            asset = connection.execute(
                "SELECT sha256 FROM assets WHERE id = ?",
                (result["asset_id"],),
            ).fetchone()
            if asset is None:
                raise ValueError(f"asset not found: {result['asset_id']}")
            if str(asset["sha256"]).lower() != result["source_sha256"]:
                raise ValueError(
                    f"source checksum mismatch for asset {result['asset_id']}"
                )

        connection.execute(
            """
            INSERT INTO analysis_runs(
                id, manifest_sha256, analyzer, analyzer_version,
                policy_version, execution_location, external_inference,
                authorization, state, scope_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (
                run_id,
                manifest_sha256,
                analyzer,
                analyzer_version,
                policy_version,
                execution_location,
                int(external_inference),
                authorization,
                _canonical_json(scope),
                now,
            ),
        )

        result_ids: list[str] = []
        for result in validated:
            fingerprint_input = {
                "analyzer": analyzer,
                "analyzer_version": analyzer_version,
                "policy_version": policy_version,
                **result,
            }
            fingerprint = _sha256_json(fingerprint_input)
            result_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"atlas://analysis-result/{fingerprint}",
                )
            )
            connection.execute(
                """
                INSERT INTO analysis_results(
                    id, run_id, asset_id, source_sha256, analysis_kind,
                    fingerprint, payload_json, provenance_json, confidence,
                    review_state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?)
                """,
                (
                    result_id,
                    run_id,
                    result["asset_id"],
                    result["source_sha256"],
                    result["analysis_kind"],
                    fingerprint,
                    _canonical_json(result["payload"]),
                    _canonical_json(result["provenance"]),
                    result["confidence"],
                    now,
                ),
            )
            result_ids.append(result_id)
            record_event(
                connection,
                kind="analysis",
                state="complete",
                message=(
                    "Beacon analysis candidate recorded "
                    f"({result['analysis_kind']})"
                ),
                asset_id=result["asset_id"],
                details={
                    "analysis_result_id": result_id,
                    "analysis_run_id": run_id,
                    "analyzer": analyzer,
                    "analyzer_version": analyzer_version,
                    "policy_version": policy_version,
                    "review_state": "candidate",
                    "source_sha256": result["source_sha256"],
                },
            )

        connection.execute(
            """
            UPDATE analysis_runs
            SET state = 'complete', completed_at = ?
            WHERE id = ?
            """,
            (_utc_now(), run_id),
        )
        record_event(
            connection,
            kind="analysis_run",
            state="complete",
            message=(
                f"Beacon analysis run recorded {len(result_ids)} candidate(s)"
            ),
            details={
                "analysis_run_id": run_id,
                "analyzer": analyzer,
                "analyzer_version": analyzer_version,
                "policy_version": policy_version,
                "execution_location": execution_location,
                "external_inference": external_inference,
                "result_count": len(result_ids),
            },
        )

    return AnalysisImportResult(
        run_id=run_id,
        result_ids=tuple(result_ids),
        reused=False,
    )
