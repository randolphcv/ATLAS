from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import connect, migrate, record_event

GENERATOR = "faster-whisper-small-int8-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_asset_transcript(
    db_path: Path,
    asset_id: str,
    *,
    source_sha256: str | None = None,
) -> dict[str, Any] | None:
    where = "AND source_sha256=?" if source_sha256 else ""
    values: tuple[object, ...] = (
        (asset_id, source_sha256) if source_sha256 else (asset_id,)
    )
    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            f"""
            SELECT * FROM asset_transcripts
            WHERE asset_id=? {where}
            ORDER BY verified_at DESC LIMIT 1
            """,
            values,
        ).fetchone()
    return dict(row) if row else None


def save_asset_transcript(
    db_path: Path,
    *,
    asset_id: str,
    source_sha256: str,
    text: str,
    language: str,
    language_probability: float | None,
) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("transcript text is empty")
    text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    now = _utc_now()
    transcript_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"atlas://transcript/{asset_id}/{source_sha256}/{GENERATOR}",
        )
    )
    with connect(db_path) as connection:
        migrate(connection)
        asset = connection.execute(
            "SELECT sha256 FROM assets WHERE id=?", (asset_id,)
        ).fetchone()
        if asset is None or asset["sha256"] != source_sha256:
            raise ValueError("transcript source checksum does not match catalog")
        connection.execute(
            """
            INSERT INTO asset_transcripts(
                id,asset_id,source_sha256,text,text_sha256,language,
                language_probability,generator,created_at,verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id,source_sha256,generator) DO UPDATE SET
                text=excluded.text,
                text_sha256=excluded.text_sha256,
                language=excluded.language,
                language_probability=excluded.language_probability,
                verified_at=excluded.verified_at
            """,
            (
                transcript_id, asset_id, source_sha256, text, text_sha256,
                language or None, language_probability, GENERATOR, now, now,
            ),
        )
        record_event(
            connection,
            kind="transcript",
            state="complete",
            message="Verified local transcript stored",
            asset_id=asset_id,
            details={
                "generator": GENERATOR,
                "source_sha256": source_sha256,
                "text_sha256": text_sha256,
                "characters": len(text),
                "language": language,
            },
        )
    result = get_asset_transcript(
        db_path, asset_id, source_sha256=source_sha256
    )
    assert result is not None
    return result
