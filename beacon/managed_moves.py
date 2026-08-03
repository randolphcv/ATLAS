from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .catalog import sha256_file
from .database import connect, migrate, record_event
from .metadata import get_policy

APPROVED_DESTINATION_ROOTS = (
    Path(r"J:\Library"),
    Path(r"J:\Assets"),
    Path(r"J:\Projects"),
)
INBOX_ROOT = Path(r"J:\Inbox")
PROJECTS_ROOT = Path(r"J:\Projects")


@dataclass(frozen=True)
class MoveResult:
    move_id: str
    asset_id: str
    source_path: str
    destination_path: str
    sha256: str
    state: str


@dataclass(frozen=True)
class PlacementDecision:
    destination_directory: Path | None
    reason: str


def recover_interrupted_managed_moves(db_path: Path) -> int:
    """Reconcile durable move records after a process stops mid-rename."""
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            """
            SELECT * FROM managed_moves
            WHERE state IN ('planned', 'running')
            ORDER BY created_at
            """
        ).fetchall()
    recovered = 0
    for row in rows:
        source = Path(row["source_path"])
        destination = Path(row["destination_path"])
        expected_sha256 = str(row["source_sha256"])
        source_exists = source.is_file()
        destination_exists = destination.is_file()
        if not source_exists and destination_exists:
            if sha256_file(destination) != expected_sha256:
                _fail_move(
                    db_path,
                    row["id"],
                    "Interrupted move destination checksum did not match.",
                )
                recovered += 1
                continue
            destination_stat = destination.stat()
            completed = _utc_now()
            with connect(db_path) as connection:
                source_location = connection.execute(
                    """
                    SELECT 1 FROM locations
                    WHERE asset_id=? AND path=?
                    """,
                    (row["asset_id"], str(source)),
                ).fetchone()
                destination_location = connection.execute(
                    """
                    SELECT 1 FROM locations
                    WHERE asset_id=? AND path=?
                    """,
                    (row["asset_id"], str(destination)),
                ).fetchone()
                if source_location is not None:
                    connection.execute(
                        """
                        UPDATE locations
                        SET path=?,modified_ns=?,observed_at=?
                        WHERE asset_id=? AND path=?
                        """,
                        (
                            str(destination),
                            destination_stat.st_mtime_ns,
                            completed,
                            row["asset_id"],
                            str(source),
                        ),
                    )
                elif destination_location is None:
                    _fail_move(
                        db_path,
                        row["id"],
                        "Interrupted move destination is not catalog-bound.",
                    )
                    recovered += 1
                    continue
                connection.execute(
                    """
                    UPDATE managed_moves
                    SET state='complete',error=NULL,completed_at=?
                    WHERE id=?
                    """,
                    (completed, row["id"]),
                )
                record_event(
                    connection,
                    kind="managed_move",
                    state="complete",
                    message=(
                        "Recovered an interrupted managed move from its "
                        "verified destination"
                    ),
                    asset_id=row["asset_id"],
                    location_path=str(destination),
                    details={
                        "move_id": row["id"],
                        "source_path": str(source),
                        "destination_path": str(destination),
                        "sha256": expected_sha256,
                        "recovered": True,
                    },
                )
            recovered += 1
            continue
        if source_exists and not destination_exists:
            _fail_move(
                db_path,
                row["id"],
                "Interrupted before the atomic rename; source remains present "
                "and is safe to retry through normal checksum verification.",
            )
            recovered += 1
            continue
        _fail_move(
            db_path,
            row["id"],
            (
                "Interrupted move has both source and destination; Beacon "
                "left both untouched for human review."
                if source_exists and destination_exists
                else "Interrupted move has neither source nor destination."
            ),
        )
        recovered += 1
    return recovered


def analysis_placement_for(source_path: Path) -> PlacementDecision:
    """Choose a conservative final home from an established Inbox hierarchy."""
    source = Path(os.path.abspath(source_path))
    inbox = Path(os.path.abspath(INBOX_ROOT))
    if not _is_within(source, inbox):
        return PlacementDecision(None, "Source is outside the managed Inbox.")
    relative = source.relative_to(inbox)
    if source.name.startswith(".") or source.name.casefold() in {
        "desktop.ini", "thumbs.db",
    }:
        return PlacementDecision(
            None,
            "Ignored operating-system metadata is not committed to the archive.",
        )
    if len(relative.parts) < 3:
        return PlacementDecision(
            None,
            "The Inbox path does not contain enough reliable project context.",
        )
    return PlacementDecision(
        PROJECTS_ROOT / relative.parent,
        "Preserved the established client/project Inbox hierarchy under Projects.",
    )


def placement_needs_clarification(source_path: Path) -> bool:
    decision = analysis_placement_for(source_path)
    return (
        decision.destination_directory is None
        and not decision.reason.startswith("Ignored ")
        and _is_within(
            Path(os.path.abspath(source_path)),
            Path(os.path.abspath(INBOX_ROOT)),
        )
    )


def commit_analyzed_file(
    db_path: Path,
    *,
    asset_id: str,
    source_path: Path,
    confidence: float,
    analysis_run_id: str,
) -> tuple[MoveResult | None, str]:
    """Commit a confidently analyzed Inbox file or explain why it needs review."""
    decision = analysis_placement_for(source_path)
    if decision.destination_directory is None:
        return None, decision.reason
    result = move_cataloged_file(
        db_path,
        asset_id=asset_id,
        source_path=source_path,
        destination_directory=decision.destination_directory,
        requested_by="Beacon local analyzer",
        authorization=(
            "Successful local analysis authorizes confident final placement; "
            f"analysis_run={analysis_run_id}; descriptive_confidence={confidence:.3f}. "
            f"{decision.reason}"
        ),
    )
    return result, decision.reason


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validated_destination(
    value: Path,
    approved_roots: tuple[Path, ...],
) -> Path:
    destination = Path(os.path.abspath(value))
    if not any(
        _is_within(destination, Path(os.path.abspath(root)))
        for root in approved_roots
    ):
        labels = ", ".join(str(root) for root in approved_roots)
        raise ValueError(
            f"Managed destination must be inside an approved root: {labels}"
        )
    if destination.name in {"", ".", ".."}:
        raise ValueError("Managed destination must include a filename.")
    for candidate in (destination.parent, *destination.parents):
        if not candidate.exists():
            continue
        is_junction = bool(
            getattr(os.path, "isjunction", lambda _: False)(candidate)
        )
        if candidate.is_symlink() or is_junction:
            raise ValueError(
                f"Managed destination traverses a reparse point: {candidate}"
            )
    return destination


def _unique_destination(destination: Path, source_sha256: str) -> Path:
    if not destination.exists():
        return destination
    if destination.is_file() and sha256_file(destination) == source_sha256:
        raise FileExistsError(
            "An identical file already exists at the managed destination; "
            "Beacon will not silently delete or merge either location."
        )
    for suffix in range(2, 10_000):
        candidate = destination.with_name(
            f"{destination.stem} ({suffix}){destination.suffix}"
        )
        if not candidate.exists():
            return candidate
    raise FileExistsError("No unused managed destination filename was available.")


def move_cataloged_file(
    db_path: Path,
    *,
    asset_id: str,
    source_path: Path,
    destination_directory: Path,
    requested_by: str,
    authorization: str,
    approved_roots: tuple[Path, ...] = APPROVED_DESTINATION_ROOTS,
) -> MoveResult:
    if get_policy(db_path, "files.managed_moves.enabled") is not True:
        raise PermissionError("Managed moves are not enabled by recorded policy.")
    if not requested_by.strip() or not authorization.strip():
        raise ValueError("Managed moves require a requester and authorization record.")
    if source_path.is_symlink():
        raise ValueError("Managed move source must not be a symlink.")
    source = source_path.resolve(strict=True)
    if not source.is_file():
        raise ValueError("Managed move source must be a regular non-symlink file.")
    for candidate in (source.parent, *source.parents):
        if candidate.is_symlink() or bool(
            getattr(os.path, "isjunction", lambda _: False)(candidate)
        ):
            raise ValueError(
                f"Managed move source traverses a reparse point: {candidate}"
            )
    destination_directory = _validated_destination(
        destination_directory / source.name,
        approved_roots,
    ).parent
    if source.drive.upper() != destination_directory.drive.upper():
        raise ValueError(
            "Managed moves must remain on one volume so the rename is atomic."
        )
    move_id = str(uuid.uuid4())
    timestamp = _utc_now()

    with connect(db_path) as connection:
        migrate(connection)
        row = connection.execute(
            """
            SELECT a.sha256
            FROM assets a
            JOIN locations l ON l.asset_id = a.id
            WHERE a.id = ? AND l.path = ?
            """,
            (asset_id, str(source)),
        ).fetchone()
        if row is None:
            raise ValueError(
                "Source is not an observed location for the selected catalog asset."
            )
        expected_sha256 = row["sha256"]
        destination = _unique_destination(
            _validated_destination(
                destination_directory / source.name,
                approved_roots,
            ),
            expected_sha256,
        )
        connection.execute(
            """
            INSERT INTO managed_moves(
                id, asset_id, source_path, destination_path, source_sha256,
                state, requested_by, authorization, created_at
            ) VALUES (?, ?, ?, ?, ?, 'planned', ?, ?, ?)
            """,
            (
                move_id,
                asset_id,
                str(source),
                str(destination),
                expected_sha256,
                requested_by,
                authorization,
                timestamp,
            ),
        )

    moved = False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        actual_sha256 = sha256_file(source)
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                "Source checksum no longer matches the catalog: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        with connect(db_path) as connection:
            connection.execute(
                "UPDATE managed_moves SET state = 'running' WHERE id = ?",
                (move_id,),
            )
        os.replace(source, destination)
        moved = True
        destination_sha256 = sha256_file(destination)
        if destination_sha256 != expected_sha256:
            raise RuntimeError("Destination checksum did not match after move.")
        destination_stat = destination.stat()
        completed = _utc_now()
        with connect(db_path) as connection:
            migrate(connection)
            cursor = connection.execute(
                """
                UPDATE locations
                SET path = ?, modified_ns = ?, observed_at = ?
                WHERE asset_id = ? AND path = ?
                """,
                (
                    str(destination),
                    destination_stat.st_mtime_ns,
                    completed,
                    asset_id,
                    str(source),
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Catalog location changed before the move could be committed."
                )
            connection.execute(
                """
                UPDATE managed_moves
                SET state = 'complete', completed_at = ?
                WHERE id = ?
                """,
                (completed, move_id),
            )
            record_event(
                connection,
                kind="managed_move",
                state="complete",
                message=f"Moved cataloged file to {destination}",
                asset_id=asset_id,
                location_path=str(destination),
                details={
                    "move_id": move_id,
                    "source_path": str(source),
                    "destination_path": str(destination),
                    "sha256": expected_sha256,
                    "authorization": authorization,
                },
            )
    except Exception as error:
        if moved and destination.exists() and not source.exists():
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, source)
                _fail_move(db_path, move_id, str(error), rolled_back=True)
            except Exception as rollback_error:
                _fail_move(
                    db_path,
                    move_id,
                    f"{error}; rollback also failed: {rollback_error}",
                )
        else:
            _fail_move(db_path, move_id, str(error))
        raise

    return MoveResult(
        move_id=move_id,
        asset_id=asset_id,
        source_path=str(source),
        destination_path=str(destination),
        sha256=expected_sha256,
        state="complete",
    )


def _fail_move(
    db_path: Path,
    move_id: str,
    error: str,
    *,
    rolled_back: bool = False,
) -> None:
    with connect(db_path) as connection:
        migrate(connection)
        move = connection.execute(
            "SELECT asset_id, source_path, destination_path FROM managed_moves WHERE id = ?",
            (move_id,),
        ).fetchone()
        connection.execute(
            """
            UPDATE managed_moves
            SET state = ?, error = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                "rolled_back" if rolled_back else "failed",
                error,
                _utc_now(),
                move_id,
            ),
        )
        if move is not None:
            record_event(
                connection,
                kind="managed_move",
                state="failed",
                message=(
                    "Managed move failed and source was restored"
                    if rolled_back
                    else "Managed move failed"
                ),
                asset_id=move["asset_id"],
                location_path=move["source_path"],
                details={
                    "move_id": move_id,
                    "destination_path": move["destination_path"],
                    "rolled_back": rolled_back,
                    "error": error,
                },
            )


def move_history(db_path: Path, asset_id: str) -> list[dict[str, object]]:
    with connect(db_path) as connection:
        migrate(connection)
        rows = connection.execute(
            """
            SELECT * FROM managed_moves
            WHERE asset_id = ?
            ORDER BY created_at DESC
            """,
            (asset_id,),
        ).fetchall()
    return [dict(row) for row in rows]
