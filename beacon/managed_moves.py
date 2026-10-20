from __future__ import annotations

import errno
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import sha256_file
from .config import (
    LIKE_ESCAPE,
    approved_destination_roots,
    cache_root,
    inbox_root,
    like_prefix_pattern,
    projects_root,
    review_root,
    unidentified_root,
)
from .database import connect, migrate, record_event
from .metadata import get_policy
from .repository import is_hidden_support_path

LOGGER = logging.getLogger("beacon.managed_moves")

APPROVED_DESTINATION_ROOTS = approved_destination_roots()
INBOX_ROOT = inbox_root()
PROJECTS_ROOT = projects_root()
CACHE_ROOT = cache_root()
REVIEW_ROOT = review_root()
UNIDENTIFIED_ROOT = unidentified_root()

# Terminal outcomes a settled item can carry out of the Inbox. The Inbox means
# "not yet looked at", so every item a job reached a terminal state on leaves
# it by exactly one of these routes.
SETTLE_PLACED = "placed"
SETTLE_CACHE = "cache"
SETTLE_REVIEW = "review"
SETTLE_UNIDENTIFIED = "unidentified"
SETTLE_DESTINATION_EXISTS = "destination_exists"
SETTLE_CHECKSUM_MISMATCH = "checksum_mismatch"
SETTLE_MISSING = "missing"
SETTLE_FAILED = "failed"


def destination_directory_blocked(error: BaseException) -> bool:
    """Return true only when a destination is actually permission-blocked."""
    if not isinstance(error, PermissionError):
        return False
    winerror = getattr(error, "winerror", None)
    if winerror is not None:
        return winerror == 5
    return getattr(error, "errno", None) in {errno.EACCES, errno.EPERM}


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
        # AGENTS.md section 10: one unrecoverable row must not abort
        # recovery for the rest. This runs at analysis start, so an
        # exception here would take down the job before it began.
        try:
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
        except Exception:
            LOGGER.exception(
                "could not recover interrupted managed move %s", row["id"]
            )
            continue
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
    if len(relative.parts) < 2:
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


@dataclass(frozen=True)
class SettleDecision:
    destination_directory: Path | None
    outcome: str
    reason: str


@dataclass(frozen=True)
class SettleResult:
    """Counts per outcome, plus what was left behind and why."""

    attempted: int
    moved: int
    outcomes: dict[str, int]
    skipped_reasons: dict[str, int]
    not_terminal: int
    removed_directories: int


def settle_destination_for(
    source_path: Path,
    *,
    failed: bool = False,
) -> SettleDecision:
    """Where an item with a terminal analysis state leaves the Inbox for.

    The Inbox means "not yet looked at". Anything a job has reached a terminal
    state on has been looked at, so it leaves, by exactly one route:

    - analysis failed            -> Holding/Review, so retry has one home
    - regenerable cache          -> Holding/Cache, never into the archive
    - a placement rule applies   -> that destination, structure preserved
    - no rule derives a home     -> Holding/Unidentified

    The cache route is what keeps the 0.22.12 rule true: a generated artifact
    is never placed into Library, Assets or Projects, whichever scope enrolled
    it. Leaving it in the Inbox is not the way to honour that rule, because
    then the Inbox no longer means what it says.
    """
    source = Path(os.path.abspath(source_path))
    inbox = Path(os.path.abspath(INBOX_ROOT))
    if not _is_within(source, inbox):
        return SettleDecision(
            None,
            SETTLE_MISSING,
            "Source is outside the managed Inbox; nothing to settle.",
        )
    relative = source.relative_to(inbox)
    if failed:
        return SettleDecision(
            REVIEW_ROOT / relative.parent,
            SETTLE_REVIEW,
            "Analysis failed; held for review with its Inbox structure "
            "preserved so a retry resolves it by catalog location.",
        )
    if is_hidden_support_path(source):
        return SettleDecision(
            CACHE_ROOT / relative.parent,
            SETTLE_CACHE,
            "Regenerable generated artifact; swept out of the Inbox and never "
            "placed into the archive.",
        )
    decision = analysis_placement_for(source)
    if decision.destination_directory is not None:
        return SettleDecision(
            decision.destination_directory, SETTLE_PLACED, decision.reason
        )
    if decision.reason.startswith("Ignored "):
        return SettleDecision(None, SETTLE_MISSING, decision.reason)
    return SettleDecision(
        UNIDENTIFIED_ROOT / relative.parent,
        SETTLE_UNIDENTIFIED,
        f"No placement rule derives a destination: {decision.reason}",
    )


SETTLE_APPROVED_ROOTS = (
    PROJECTS_ROOT,
    CACHE_ROOT,
    REVIEW_ROOT,
    UNIDENTIFIED_ROOT,
)


def _settle_candidates(
    connection: Any,
    path_prefix: str | Path | None,
) -> list[Any]:
    """Catalog rows beneath the Inbox, with whatever terminal state they hold.

    Scoped by prefix when the job was, so a folder-scoped job drains its own
    folder and nothing else. The state is read from the catalog rather than
    from this job's item rows, because material stranded by an earlier job is
    exactly what has to drain.
    """
    parameters: list[Any] = [str(INBOX_ROOT) + "\\%"]
    prefix_predicate = "1"
    if path_prefix is not None:
        prefix_predicate = (
            f"lower(location.path) LIKE ? ESCAPE '{LIKE_ESCAPE}'"
        )
        parameters.append(like_prefix_pattern(path_prefix))
    return connection.execute(
        f"""
        SELECT location.asset_id AS asset_id,
               location.path AS path,
               (SELECT item.excluded_reason FROM local_analysis_items item
                 WHERE item.asset_id = location.asset_id
                   AND item.excluded_reason IS NOT NULL
                 LIMIT 1) AS excluded_reason,
               (SELECT item.state FROM local_analysis_items item
                 WHERE item.asset_id = location.asset_id
                 ORDER BY item.completed_at DESC LIMIT 1) AS item_state,
               EXISTS(SELECT 1 FROM analysis_results result
                      WHERE result.asset_id = location.asset_id
                        AND result.analysis_kind = 'contextual_metadata'
                        AND result.review_state IN ('candidate','approved')
               ) AS analysed
        FROM locations location
        WHERE lower(location.path) LIKE lower(?)
          AND ({prefix_predicate})
        ORDER BY length(location.path), location.path COLLATE NOCASE
        """,
        parameters,
    ).fetchall()


def settle_inbox_items(
    db_path: Path,
    *,
    path_prefix: str | Path | None = None,
    requested_by: str = "Beacon settle",
    authorization_note: str = "",
) -> SettleResult:
    """Move every looked-at item out of the Inbox. One item never stops another.

    AGENTS.md: no per-item failure may abort a batch. Every per-item call here
    is isolated, the outcome is recorded, and the batch continues. A item left
    behind is counted and named by class in the result rather than silently
    tolerated.

    Idempotent: a settled item's catalog location no longer sits beneath the
    Inbox, so a second run does not select it and moves nothing.
    """
    with connect(db_path) as connection:
        migrate(connection)
        rows = _settle_candidates(connection, path_prefix)
    outcomes: dict[str, int] = {}
    skipped_reasons: dict[str, int] = {}
    attempted = moved = not_terminal = 0

    def count(mapping: dict[str, int], key: str) -> None:
        mapping[key] = mapping.get(key, 0) + 1

    for row in rows:
        source = Path(str(row["path"]))
        state = str(row["item_state"]) if row["item_state"] else None
        failed = state == "failed"
        terminal = (
            failed
            or row["excluded_reason"] is not None
            or bool(row["analysed"])
            or state == "complete"
        )
        if not terminal:
            # Not looked at yet. This is the one thing the Inbox is for.
            not_terminal += 1
            continue
        decision = settle_destination_for(source, failed=failed)
        if decision.destination_directory is None:
            count(outcomes, decision.outcome)
            continue
        if not source.exists():
            count(outcomes, SETTLE_MISSING)
            continue
        attempted += 1
        try:
            move_cataloged_file(
                db_path,
                asset_id=str(row["asset_id"]),
                source_path=source,
                destination_directory=decision.destination_directory,
                requested_by=requested_by,
                authorization=(
                    "The Inbox holds only material not yet looked at; this "
                    "item has a terminal analysis state. "
                    f"{decision.reason} {authorization_note}".strip()
                ),
                approved_roots=SETTLE_APPROVED_ROOTS,
            )
            moved += 1
            count(outcomes, decision.outcome)
        except FileExistsError:
            # An identical file is already at the destination. Never overwrite,
            # never merge, never delete either copy: leave it and say so.
            count(outcomes, SETTLE_DESTINATION_EXISTS)
            count(skipped_reasons, SETTLE_DESTINATION_EXISTS)
        except FileNotFoundError:
            count(outcomes, SETTLE_MISSING)
            count(skipped_reasons, SETTLE_MISSING)
        except RuntimeError as error:
            key = (
                SETTLE_CHECKSUM_MISMATCH
                if "checksum" in str(error).casefold()
                else SETTLE_FAILED
            )
            count(outcomes, key)
            count(skipped_reasons, key)
        except Exception:
            LOGGER.exception("settle failed for one item")
            count(outcomes, SETTLE_FAILED)
            count(skipped_reasons, SETTLE_FAILED)

    removed_directories = _remove_empty_inbox_directories()
    with connect(db_path) as connection:
        record_event(
            connection,
            kind="inbox_settle",
            state="complete" if not skipped_reasons else "partial",
            message=(
                "Settled looked-at Inbox material to final destinations and "
                "holding zones"
            ),
            details={
                "scoped": path_prefix is not None,
                "attempted": attempted,
                "moved": moved,
                "outcomes": outcomes,
                "skipped_reasons": skipped_reasons,
                "not_terminal": not_terminal,
                "removed_directories": removed_directories,
            },
        )
    return SettleResult(
        attempted=attempted,
        moved=moved,
        outcomes=outcomes,
        skipped_reasons=skipped_reasons,
        not_terminal=not_terminal,
        removed_directories=removed_directories,
    )


def _remove_empty_inbox_directories() -> int:
    """Remove directories the settle left empty. Never removes a file."""
    removed = 0
    inbox = Path(os.path.abspath(INBOX_ROOT))
    if not inbox.is_dir():
        return 0
    directories = sorted(
        (path for path in inbox.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        if directory.is_symlink() or bool(
            getattr(os.path, "isjunction", lambda _: False)(directory)
        ):
            continue
        try:
            directory.rmdir()
            removed += 1
        except OSError:
            pass
    return removed


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
