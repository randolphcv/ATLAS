"""The Inbox holds only material that has not been looked at yet.

The owner's rule of 2026-10-20: every analysis job moves all analysed files
to a final destination or a holding zone; nothing analysed is left in the Inbox,
because otherwise a human cannot tell what has and has not been analysed.

These tests assert the invariant itself rather than the steps that produce it.
The headline is `test_no_terminal_item_remains_under_the_inbox`: a fixture
Inbox holding one of every outcome class, settled once, must be empty of
terminal items. The rest pin the edges that made the real Inbox fill up --
a per-item failure must not strand its neighbours, an absent archive neighbour
must not strand a folder, and a destination that already exists must be left
alone rather than overwritten.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from beacon.catalog import catalog_file, sha256_file
from beacon.database import connect
from beacon.local_analysis import (
    _artifact_exclusion_reason,
    _resolve_item_source,
)
from beacon.local_analysis import create_local_analysis_job
from beacon.managed_moves import (
    SETTLE_CACHE,
    SETTLE_DESTINATION_EXISTS,
    SETTLE_PLACED,
    SETTLE_REVIEW,
    SETTLE_UNIDENTIFIED,
    count_settleable,
    settle_destination_for,
    settle_inbox_items,
)
from beacon.metadata import set_policy
from beacon.repository import verify_catalog_locations

FIXTURE_JOB = "fixture-settle-job"


class InboxSettleTests(unittest.TestCase):
    """AGENTS.md section 6, plus the Inbox-clearing rule of 2026-10-20."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "beacon.db"
        self.inbox = self.root / "Inbox"
        self.projects = self.root / "Projects"
        self.holding = self.root / "Holding"
        self.cache = self.holding / "Cache"
        self.review = self.holding / "Review"
        self.unidentified = self.holding / "Unidentified"
        self.inbox.mkdir()
        self.now = datetime.now(timezone.utc).isoformat()
        self._seed_job = False

    def tearDown(self) -> None:
        self.temp.cleanup()

    # --- fixture helpers -------------------------------------------------

    def _settled(self, **kwargs: object) -> object:
        """Run settle against the fixture roots, never the real archive."""
        with (
            patch("beacon.managed_moves.INBOX_ROOT", self.inbox),
            patch("beacon.managed_moves.PROJECTS_ROOT", self.projects),
            patch("beacon.managed_moves.CACHE_ROOT", self.cache),
            patch("beacon.managed_moves.REVIEW_ROOT", self.review),
            patch("beacon.managed_moves.UNIDENTIFIED_ROOT", self.unidentified),
            patch(
                "beacon.managed_moves.SETTLE_APPROVED_ROOTS",
                (self.projects, self.holding),
            ),
        ):
            return settle_inbox_items(self.db, **kwargs)  # type: ignore[arg-type]

    def _add(self, relative: str, payload: bytes) -> object:
        source = self.inbox / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(payload)
        asset = catalog_file(
            source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        set_policy(
            self.db, "files.managed_moves.enabled", True, source_kind="test"
        )
        return asset

    def _ensure_job(self, connection: sqlite3.Connection) -> None:
        if self._seed_job:
            return
        connection.execute(
            """
            INSERT INTO local_analysis_jobs(
                id, state, model, endpoint, policy_version, scope_sha256,
                total_items, cancel_requested, requested_by, created_at,
                updated_at
            ) VALUES (?, 'complete', 'fixture', 'fixture', 'fixture',
                      'fixture', 0, 0, 'test', ?, ?)
            """,
            (FIXTURE_JOB, self.now, self.now),
        )
        self._seed_job = True

    def _item(
        self,
        asset: object,
        source: Path,
        *,
        state: str,
        excluded_reason: str | None = None,
        error: str | None = None,
    ) -> None:
        with connect(self.db) as connection:
            self._ensure_job(connection)
            connection.execute(
                """
                INSERT INTO local_analysis_items(
                    id, job_id, asset_id, source_sha256, source_path, state,
                    attempts, error, excluded_reason, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    FIXTURE_JOB,
                    asset.asset_id,  # type: ignore[attr-defined]
                    sha256_file(source) if source.exists() else "",
                    str(source),
                    state,
                    error,
                    excluded_reason,
                    self.now,
                ),
            )

    def _analysed(self, asset: object) -> None:
        run_id = str(uuid.uuid4())
        with connect(self.db) as connection:
            connection.execute(
                """INSERT INTO analysis_runs VALUES
                (?, ?, 'test', '1', 'test', 'local', 0, 'test',
                 'complete', '{}', ?, ?, NULL)""",
                (run_id, str(uuid.uuid4()), self.now, self.now),
            )
            connection.execute(
                """INSERT INTO analysis_results VALUES
                (?, ?, ?, ?, 'contextual_metadata', ?, '{}', '{}',
                 1.0, 'candidate', ?, NULL)""",
                (
                    str(uuid.uuid4()),
                    run_id,
                    asset.asset_id,  # type: ignore[attr-defined]
                    asset.sha256,  # type: ignore[attr-defined]
                    str(uuid.uuid4()),
                    self.now,
                ),
            )

    def _remaining_under_inbox(self) -> list[Path]:
        if not self.inbox.exists():
            return []
        return sorted(p for p in self.inbox.rglob("*") if p.is_file())

    def _move_rows(self) -> list[sqlite3.Row]:
        with connect(self.db) as connection:
            return connection.execute(
                "SELECT * FROM managed_moves ORDER BY created_at, source_path"
            ).fetchall()

    # --- the invariant ---------------------------------------------------

    def test_no_terminal_item_remains_under_the_inbox(self) -> None:
        """One of every outcome class in, an empty Inbox out."""
        media = self._add(
            "fixture_client_a/project_alpha/SAMPLE_0001.mov", b"media bytes"
        )
        project = self._add(
            "fixture_client_a/project_alpha/cut.prproj", b"project bytes"
        )
        companion = self._add(
            "fixture_client_a/project_alpha/SAMPLE_0001.mif", b"index bytes"
        )
        sidecar = self._add(
            "fixture_client_a/project_alpha/SAMPLE_0001.xmp", b"sidecar bytes"
        )
        broken = self._add(
            "fixture_client_a/project_alpha/SAMPLE_0002.mov", b"broken bytes"
        )
        loose = self._add("loose_at_the_top.mov", b"loose bytes")

        media_path = self.inbox / "fixture_client_a/project_alpha/SAMPLE_0001.mov"
        self._analysed(media)
        self._item(media, media_path, state="complete")
        self._item(
            project,
            self.inbox / "fixture_client_a/project_alpha/cut.prproj",
            state="complete",
            excluded_reason="Excluded editable production project file",
        )
        self._item(
            companion,
            self.inbox / "fixture_client_a/project_alpha/SAMPLE_0001.mif",
            state="complete",
            excluded_reason="Excluded camera metadata or generated index",
        )
        self._item(
            sidecar,
            self.inbox / "fixture_client_a/project_alpha/SAMPLE_0001.xmp",
            state="complete",
            excluded_reason="Excluded confidently generated cache artifact",
        )
        self._item(
            broken,
            self.inbox / "fixture_client_a/project_alpha/SAMPLE_0002.mov",
            state="failed",
            error="fixture model failure",
        )
        self._item(
            loose,
            self.inbox / "loose_at_the_top.mov",
            state="complete",
            excluded_reason="fixture exclusion",
        )

        result = self._settled()

        self.assertEqual(
            self._remaining_under_inbox(),
            [],
            "every item had a terminal state, so the Inbox must be empty",
        )
        tree = "fixture_client_a/project_alpha"
        expected = {
            self.projects / tree / "SAMPLE_0001.mov": "analysed media",
            self.projects / tree / "cut.prproj": "project file, with its media",
            self.projects / tree / "SAMPLE_0001.mif": "camera index, with its media",
            self.cache / tree / "SAMPLE_0001.xmp": "regenerable cache",
            self.review / tree / "SAMPLE_0002.mov": "failed analysis",
            self.unidentified / "loose_at_the_top.mov": "no derivable destination",
        }
        for destination, why in expected.items():
            self.assertTrue(
                destination.is_file(), f"{why} is not at {destination}"
            )
        self.assertEqual(result.moved, 6)  # type: ignore[attr-defined]
        self.assertEqual(
            result.outcomes,  # type: ignore[attr-defined]
            {
                SETTLE_PLACED: 3,
                SETTLE_CACHE: 1,
                SETTLE_REVIEW: 1,
                SETTLE_UNIDENTIFIED: 1,
            },
        )
        self.assertEqual(result.skipped_reasons, {})  # type: ignore[attr-defined]

        rows = self._move_rows()
        self.assertEqual(len(rows), 6, "one managed_moves row per move")
        for row in rows:
            self.assertEqual(str(row["state"]), "complete")
            self.assertIn(
                "not yet looked at",
                str(row["authorization"]),
                "every move records why the Inbox could not keep it",
            )
            self.assertEqual(
                sha256_file(Path(str(row["destination_path"]))),
                str(row["source_sha256"]),
                "destination bytes must match the catalogued checksum",
            )

    def test_relative_structure_is_preserved_verbatim(self) -> None:
        """AGENTS.md section 6: placement reorganizes nothing."""
        deep = "fixture_client_a/project_alpha/DAY_01/CARD_A/SAMPLE_0003.mov"
        asset = self._add(deep, b"deep bytes")
        self._item(
            asset, self.inbox / deep, state="complete",
            excluded_reason="fixture exclusion",
        )
        self._settled()
        self.assertTrue((self.projects / deep).is_file())

    def test_an_item_not_yet_looked_at_stays_in_the_inbox(self) -> None:
        """The Inbox's one meaning. A pending item is not settled."""
        asset = self._add(
            "fixture_client_a/project_alpha/SAMPLE_0004.mov", b"pending bytes"
        )
        source = self.inbox / "fixture_client_a/project_alpha/SAMPLE_0004.mov"
        self._item(asset, source, state="pending")
        result = self._settled()
        self.assertEqual(result.moved, 0)  # type: ignore[attr-defined]
        self.assertEqual(result.not_terminal, 1)  # type: ignore[attr-defined]
        self.assertTrue(source.is_file())

    def test_an_item_never_enrolled_stays_in_the_inbox(self) -> None:
        """No row at all means nobody has looked at it."""
        self._add(
            "fixture_client_a/project_alpha/SAMPLE_0005.mov", b"unseen bytes"
        )
        source = self.inbox / "fixture_client_a/project_alpha/SAMPLE_0005.mov"
        result = self._settled()
        self.assertEqual(result.moved, 0)  # type: ignore[attr-defined]
        self.assertTrue(source.is_file())

    # --- the edges that made the real Inbox fill up ----------------------

    def test_one_failure_does_not_strand_its_neighbours(self) -> None:
        """The defect this change closes.

        A single failed item used to skip the placement step for the entire
        job, which is how 1,439 cache files and 803 analysed files came to sit
        in the Inbox behind one model error.
        """
        good = self._add(
            "fixture_client_a/project_alpha/SAMPLE_0006.mov", b"good bytes"
        )
        bad = self._add(
            "fixture_client_a/project_alpha/SAMPLE_0007.mov", b"bad bytes"
        )
        self._item(
            good,
            self.inbox / "fixture_client_a/project_alpha/SAMPLE_0006.mov",
            state="complete",
            excluded_reason="fixture exclusion",
        )
        self._item(
            bad,
            self.inbox / "fixture_client_a/project_alpha/SAMPLE_0007.mov",
            state="failed",
            error="fixture failure",
        )
        result = self._settled()
        self.assertEqual(result.moved, 2)  # type: ignore[attr-defined]
        self.assertEqual(self._remaining_under_inbox(), [])
        self.assertTrue(
            (
                self.projects
                / "fixture_client_a/project_alpha/SAMPLE_0006.mov"
            ).is_file(),
            "the healthy neighbour must still reach its destination",
        )

    def test_settle_is_idempotent(self) -> None:
        """Running it twice moves nothing the second time."""
        asset = self._add(
            "fixture_client_a/project_alpha/SAMPLE_0008.mov", b"once bytes"
        )
        self._item(
            asset,
            self.inbox / "fixture_client_a/project_alpha/SAMPLE_0008.mov",
            state="complete",
            excluded_reason="fixture exclusion",
        )
        first = self._settled()
        second = self._settled()
        self.assertEqual(first.moved, 1)  # type: ignore[attr-defined]
        self.assertEqual(second.moved, 0)  # type: ignore[attr-defined]
        self.assertEqual(second.attempted, 0)  # type: ignore[attr-defined]
        self.assertEqual(len(self._move_rows()), 1, "no second move recorded")

    def test_an_identical_destination_is_left_alone(self) -> None:
        """Never overwrite, never merge, never delete either copy."""
        relative = "fixture_client_a/project_alpha/SAMPLE_0009.mov"
        payload = b"identical bytes"
        asset = self._add(relative, payload)
        source = self.inbox / relative
        self._item(
            asset, source, state="complete",
            excluded_reason="fixture exclusion",
        )
        occupied = self.projects / relative
        occupied.parent.mkdir(parents=True)
        occupied.write_bytes(payload)

        result = self._settled()

        self.assertEqual(result.moved, 0)  # type: ignore[attr-defined]
        self.assertEqual(
            result.skipped_reasons,  # type: ignore[attr-defined]
            {SETTLE_DESTINATION_EXISTS: 1},
        )
        self.assertTrue(source.is_file(), "the source must survive untouched")
        self.assertEqual(source.read_bytes(), payload)
        self.assertEqual(occupied.read_bytes(), payload)
        self.assertEqual(
            self._move_rows(), [], "a refused move records no completed row"
        )

    def test_a_differing_destination_name_is_not_clobbered(self) -> None:
        """Same name, different bytes: both survive, under distinct names."""
        relative = "fixture_client_a/project_alpha/SAMPLE_0010.mov"
        asset = self._add(relative, b"incoming bytes")
        source = self.inbox / relative
        self._item(
            asset, source, state="complete",
            excluded_reason="fixture exclusion",
        )
        occupied = self.projects / relative
        occupied.parent.mkdir(parents=True)
        occupied.write_bytes(b"different bytes already here")

        result = self._settled()

        self.assertEqual(result.moved, 1)  # type: ignore[attr-defined]
        self.assertEqual(
            occupied.read_bytes(),
            b"different bytes already here",
            "the file already there must not be touched",
        )
        self.assertTrue(
            (occupied.parent / "SAMPLE_0010 (2).mov").is_file(),
            "the incoming file lands beside it under a distinct name",
        )
        self.assertFalse(source.exists())

    def test_a_scoped_settle_drains_only_its_own_folder(self) -> None:
        """A folder-scoped job must not move a neighbour's material."""
        mine = self._add(
            "fixture_client_a/project_alpha/SAMPLE_0011.mov", b"mine bytes"
        )
        theirs = self._add(
            "fixture_client_b/project_beta/SAMPLE_0012.mov", b"theirs bytes"
        )
        self._item(
            mine,
            self.inbox / "fixture_client_a/project_alpha/SAMPLE_0011.mov",
            state="complete",
            excluded_reason="fixture exclusion",
        )
        self._item(
            theirs,
            self.inbox / "fixture_client_b/project_beta/SAMPLE_0012.mov",
            state="complete",
            excluded_reason="fixture exclusion",
        )
        result = self._settled(
            path_prefix=self.inbox / "fixture_client_a" / "project_alpha"
        )
        self.assertEqual(result.moved, 1)  # type: ignore[attr-defined]
        self.assertTrue(
            (
                self.inbox / "fixture_client_b/project_beta/SAMPLE_0012.mov"
            ).is_file(),
            "material outside the prefix must stay where it is",
        )

    def test_retry_resolves_a_reviewed_item_by_catalog_location(self) -> None:
        """A failed item held for review must still be retryable.

        Its enrolled Inbox path no longer exists once settle has moved it, so
        a retry that trusted that path would fail on a file sitting safely one
        directory away.
        """
        relative = "fixture_client_a/project_alpha/SAMPLE_0013.mov"
        asset = self._add(relative, b"review bytes")
        enrolled = self.inbox / relative
        self._item(asset, enrolled, state="failed", error="fixture failure")
        self._settled()
        held = self.review / relative
        self.assertTrue(held.is_file())
        self.assertFalse(enrolled.exists())

        resolved = _resolve_item_source(
            self.db,
            asset_id=asset.asset_id,  # type: ignore[attr-defined]
            stored_path=str(enrolled),
        )
        self.assertEqual(
            resolved,
            held,
            "retry must find the file at its current catalog location",
        )

    # --- the routing rule itself -----------------------------------------

    def test_cache_never_lands_in_the_archive(self) -> None:
        """The 0.22.12 rule, kept: a generated artifact is never placed."""
        for relative in (
            "fixture_client_a/project_alpha/SAMPLE_0001.xmp",
            "fixture_client_a/project_alpha/Media Cache/index.cfa",
            "fixture_client_a/project_alpha/Peak Files/take.pek",
        ):
            with self.subTest(relative=relative):
                with (
                    patch("beacon.managed_moves.INBOX_ROOT", self.inbox),
                    patch("beacon.managed_moves.PROJECTS_ROOT", self.projects),
                    patch("beacon.managed_moves.CACHE_ROOT", self.cache),
                ):
                    decision = settle_destination_for(self.inbox / relative)
                self.assertEqual(decision.outcome, SETTLE_CACHE)
                self.assertTrue(
                    str(decision.destination_directory).startswith(
                        str(self.cache)
                    ),
                    "cache leaves the Inbox but never enters the archive",
                )

    def test_authored_and_camera_files_stay_with_their_media(self) -> None:
        """The owner's decision of 2026-10-20: these are not cache."""
        for relative in (
            "fixture_client_a/project_alpha/cut.prproj",
            "fixture_client_a/project_alpha/titles.aep",
            "fixture_client_a/project_alpha/SAMPLE_0001.mif",
            "fixture_client_a/project_alpha/deck.key",
        ):
            with self.subTest(relative=relative):
                with (
                    patch("beacon.managed_moves.INBOX_ROOT", self.inbox),
                    patch("beacon.managed_moves.PROJECTS_ROOT", self.projects),
                    patch("beacon.managed_moves.CACHE_ROOT", self.cache),
                ):
                    decision = settle_destination_for(self.inbox / relative)
                self.assertEqual(decision.outcome, SETTLE_PLACED)
                self.assertEqual(
                    decision.destination_directory,
                    self.projects / "fixture_client_a" / "project_alpha",
                    "it belongs in the same folder as the media it describes",
                )

    def test_a_failed_item_goes_to_review_whatever_its_type(self) -> None:
        with (
            patch("beacon.managed_moves.INBOX_ROOT", self.inbox),
            patch("beacon.managed_moves.REVIEW_ROOT", self.review),
            patch("beacon.managed_moves.CACHE_ROOT", self.cache),
        ):
            decision = settle_destination_for(
                self.inbox / "fixture_client_a/project_alpha/SAMPLE_0001.xmp",
                failed=True,
            )
        self.assertEqual(decision.outcome, SETTLE_REVIEW)
        self.assertTrue(
            str(decision.destination_directory).startswith(str(self.review)),
            "a failure is held for review before it is classified as cache",
        )

    def test_settle_looks_up_an_items_state_by_index_not_by_scan(self) -> None:
        """A correctness-neutral defect that stopped a real drain for minutes.

        Settle asks the catalog for each candidate's terminal state. Before
        0.22.16 the only index on local_analysis_items led with job_id, so
        that question fell back to a full table scan, once per candidate. On
        a 20,374-row table with 2,466 candidates nothing moved for eleven
        minutes while the query ran, and no fixture-sized test could see it:
        a scan of six rows is instant.

        So this asserts the plan rather than the timing. A timing assertion
        would be flaky on a loaded volume; a plan assertion names the defect
        exactly and fails the moment the index stops covering the lookup.
        """
        asset = self._add(
            "fixture_client_a/project_alpha/SAMPLE_0014.mov", b"plan bytes"
        )
        source = self.inbox / "fixture_client_a/project_alpha/SAMPLE_0014.mov"
        self._item(
            asset, source, state="complete",
            excluded_reason="fixture exclusion",
        )
        with connect(self.db) as connection:
            plans = [
                " ".join(str(part) for part in row)
                for row in connection.execute(
                    """
                    EXPLAIN QUERY PLAN
                    SELECT (SELECT item.state FROM local_analysis_items item
                             WHERE item.asset_id = location.asset_id
                             ORDER BY item.completed_at DESC LIMIT 1)
                    FROM locations location
                    WHERE lower(location.path) LIKE lower(?)
                    """,
                    (str(self.inbox) + "\\%",),
                ).fetchall()
            ]
        joined = "\n".join(plans)
        self.assertIn(
            "idx_local_analysis_items_asset_completed",
            joined,
            "the asset_id lookup must use the covering index:\n" + joined,
        )
        self.assertNotIn(
            "SCAN local_analysis_items",
            joined,
            "a full scan per candidate is what stalled the real drain:\n"
            + joined,
        )

    def test_count_settleable_matches_what_settle_then_moves(self) -> None:
        """The dialog's number and the job's work must be the same number.

        This is what makes a drain startable: a folder can hold files that
        have all been looked at, with nothing left to analyse, and the
        operator still has to be able to clear it. If the count and the move
        were computed separately they would drift, so both read one plan.
        """
        for index, relative in enumerate(
            (
                "fixture_client_a/project_alpha/SAMPLE_0020.mov",
                "fixture_client_a/project_alpha/SAMPLE_0020.xmp",
                "fixture_client_a/project_alpha/cut.prproj",
            )
        ):
            asset = self._add(relative, b"settleable %d" % index)
            self._item(
                asset, self.inbox / relative, state="complete",
                excluded_reason="fixture exclusion",
            )
        # One item not looked at yet: counted by neither.
        pending = self._add(
            "fixture_client_a/project_alpha/SAMPLE_0021.mov", b"pending"
        )
        self._item(
            pending,
            self.inbox / "fixture_client_a/project_alpha/SAMPLE_0021.mov",
            state="pending",
        )

        with (
            patch("beacon.managed_moves.INBOX_ROOT", self.inbox),
            patch("beacon.managed_moves.PROJECTS_ROOT", self.projects),
            patch("beacon.managed_moves.CACHE_ROOT", self.cache),
            patch("beacon.managed_moves.REVIEW_ROOT", self.review),
            patch("beacon.managed_moves.UNIDENTIFIED_ROOT", self.unidentified),
        ):
            counted = count_settleable(self.db)
        self.assertEqual(counted["total"], 3, "the pending item is not work")
        self.assertEqual(counted.get("cache"), 1)
        self.assertEqual(counted.get("placed"), 2)

        result = self._settled()
        self.assertEqual(
            result.moved,  # type: ignore[attr-defined]
            counted["total"],
            "the count promised exactly what the move delivered",
        )

    def test_count_settleable_respects_the_folder_prefix(self) -> None:
        """The old gate counted archive-wide while the job was folder-scoped."""
        for relative in (
            "fixture_client_a/project_alpha/SAMPLE_0022.mov",
            "fixture_client_b/project_beta/SAMPLE_0023.mov",
        ):
            asset = self._add(relative, relative.encode())
            self._item(
                asset, self.inbox / relative, state="complete",
                excluded_reason="fixture exclusion",
            )
        with (
            patch("beacon.managed_moves.INBOX_ROOT", self.inbox),
            patch("beacon.managed_moves.PROJECTS_ROOT", self.projects),
            patch("beacon.managed_moves.CACHE_ROOT", self.cache),
            patch("beacon.managed_moves.REVIEW_ROOT", self.review),
            patch("beacon.managed_moves.UNIDENTIFIED_ROOT", self.unidentified),
        ):
            everything = count_settleable(self.db)
            inside = count_settleable(
                self.db,
                path_prefix=self.inbox / "fixture_client_a" / "project_alpha",
            )
            outside = count_settleable(
                self.db, path_prefix=self.inbox / "fixture_client_c"
            )
        self.assertEqual(everything["total"], 2)
        self.assertEqual(inside["total"], 1, "only the scoped folder")
        self.assertEqual(outside["total"], 0, "a folder with nothing in it")

    def test_settle_reports_progress_for_every_item(self) -> None:
        """A job that runs for an hour must never show a blank stage again."""
        relatives = [
            f"fixture_client_a/project_alpha/SAMPLE_003{index}.mov"
            for index in range(4)
        ]
        for index, relative in enumerate(relatives):
            asset = self._add(relative, b"progress %d" % index)
            self._item(
                asset, self.inbox / relative, state="complete",
                excluded_reason="fixture exclusion",
            )
        seen: list[tuple[int, int, str]] = []
        result = self._settled(
            progress_callback=lambda done, total, outcome: seen.append(
                (done, total, outcome)
            )
        )
        self.assertEqual(result.moved, 4)  # type: ignore[attr-defined]
        self.assertEqual(
            [done for done, _, _ in seen],
            [1, 2, 3, 4],
            "one report per item, counting up",
        )
        self.assertEqual({total for _, total, _ in seen}, {4})
        self.assertEqual({outcome for _, _, outcome in seen}, {SETTLE_PLACED})

    def test_a_failing_progress_callback_does_not_stop_the_settle(self) -> None:
        """Reporting is not the work. A broken reporter must not strand files."""
        relative = "fixture_client_a/project_alpha/SAMPLE_0040.mov"
        asset = self._add(relative, b"resilient")
        self._item(
            asset, self.inbox / relative, state="complete",
            excluded_reason="fixture exclusion",
        )

        def broken(done: int, total: int, outcome: str) -> None:
            raise RuntimeError("fixture reporter failure")

        result = self._settled(progress_callback=broken)
        self.assertEqual(result.moved, 1)  # type: ignore[attr-defined]
        self.assertEqual(self._remaining_under_inbox(), [])

    def test_project_files_carry_the_class_in_their_reason(self) -> None:
        """Enrolment must produce a reason naming the class, not a bare skip."""
        reason = _artifact_exclusion_reason(
            self.inbox / "fixture_client_a/project_alpha/cut.prproj"
        )
        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("project file", reason.casefold())

    def test_a_row_marked_missing_enrols_nowhere_and_settles_nowhere(
        self,
    ) -> None:
        """Marking is operational, not decorative: enrol 1, settle 1, fail 0.

        A location verification has marked missing has no file behind it. It
        used to enrol anyway, fail on a source that is not there, and then
        reach the settle with nothing to move -- so the job reported `partial`
        over an item that was never work. The mark is read by both halves now,
        and the row itself is left exactly as verification wrote it.
        """
        present_relative = "fixture_client_a/project_alpha/SAMPLE_0050.mov"
        missing_relative = "fixture_client_a/project_alpha/SAMPLE_0051.mov"
        folder = self.inbox / "fixture_client_a" / "project_alpha"
        present = self._add(present_relative, b"present bytes")
        absent_asset = self._add(missing_relative, b"absent bytes")
        absent_path = self.inbox / missing_relative

        # Terminal in the catalog the way an earlier job would have left them:
        # the present file looked at and excluded, the absent one failed.
        self._item(
            present,
            self.inbox / present_relative,
            state="complete",
            excluded_reason="fixture exclusion",
        )
        self._item(
            absent_asset,
            absent_path,
            state="failed",
            error="fixture failure",
        )

        # Mark through the real verification path rather than by hand, so the
        # test exercises the same column the operator's control writes.
        absent_path.unlink()
        counts = verify_catalog_locations(self.db, folder)
        self.assertEqual(counts["marked_missing"], 1)

        job_id = create_local_analysis_job(
            self.db,
            model="fixture-model",
            path_prefix=str(folder.resolve()),
        )
        with connect(self.db) as connection:
            total_items = connection.execute(
                "SELECT total_items FROM local_analysis_jobs WHERE id=?",
                (job_id,),
            ).fetchone()["total_items"]
            enrolled = [
                str(row["source_path"]).casefold()
                for row in connection.execute(
                    "SELECT source_path FROM local_analysis_items "
                    "WHERE job_id=?",
                    (job_id,),
                )
            ]
        self.assertEqual(total_items, 1, "the marked row must not enrol")
        self.assertEqual(
            enrolled,
            [str((self.inbox / present_relative).resolve()).casefold()],
            "only the present file enrols",
        )

        with (
            patch("beacon.managed_moves.INBOX_ROOT", self.inbox),
            patch("beacon.managed_moves.PROJECTS_ROOT", self.projects),
            patch("beacon.managed_moves.CACHE_ROOT", self.cache),
            patch("beacon.managed_moves.REVIEW_ROOT", self.review),
            patch("beacon.managed_moves.UNIDENTIFIED_ROOT", self.unidentified),
        ):
            counted = count_settleable(self.db)
        self.assertEqual(
            counted["total"],
            1,
            "the counter must not promise a move it cannot make",
        )

        result = self._settled()
        self.assertEqual(result.moved, 1)  # type: ignore[attr-defined]
        self.assertEqual(result.attempted, 1)  # type: ignore[attr-defined]
        self.assertEqual(
            result.outcomes,  # type: ignore[attr-defined]
            {SETTLE_PLACED: 1},
            "a marked row is not an outcome of any kind, least of all missing",
        )
        self.assertEqual(
            result.skipped_reasons,  # type: ignore[attr-defined]
            {},
            "nothing was skipped, so nothing counts as a failure",
        )
        self.assertEqual(result.not_terminal, 0)  # type: ignore[attr-defined]

        # The row is left as verification wrote it, and no move was recorded
        # against it.
        with connect(self.db) as connection:
            row = connection.execute(
                "SELECT path, missing_at FROM locations WHERE asset_id=?",
                (absent_asset.asset_id,),  # type: ignore[attr-defined]
            ).fetchone()
            moved_sources = {
                str(move["source_path"]).casefold()
                for move in connection.execute(
                    "SELECT source_path FROM managed_moves"
                )
            }
        self.assertEqual(str(row["path"]), str(absent_path))
        self.assertIsNotNone(row["missing_at"])
        self.assertNotIn(str(absent_path).casefold(), moved_sources)

    def test_an_asset_still_present_elsewhere_keeps_enrolling(self) -> None:
        """One marked location of several does not withdraw the asset.

        The naive predicate excludes the asset when any of its locations is
        marked, which would quietly drop material that is still on disk. The
        filter is per location: the asset enrols through the location that is
        still there, and the enrolled source path is that one.
        """
        payload = b"the same bytes in two places"
        first_relative = "fixture_client_a/project_alpha/SAMPLE_0060.mov"
        second_relative = "fixture_client_a/project_beta/SAMPLE_0060.mov"
        self._add(first_relative, payload)
        asset = self._add(second_relative, payload)
        first_path = self.inbox / first_relative
        second_path = self.inbox / second_relative

        # Same content at two paths is one asset with two locations.
        with connect(self.db) as connection:
            locations = connection.execute(
                "SELECT COUNT(*) AS n FROM locations WHERE asset_id=?",
                (asset.asset_id,),  # type: ignore[attr-defined]
            ).fetchone()["n"]
        self.assertEqual(locations, 2, "fixture must be one asset, two rows")

        first_path.unlink()
        counts = verify_catalog_locations(self.db, first_path.parent)
        self.assertEqual(counts["marked_missing"], 1)

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        with connect(self.db) as connection:
            enrolled = [
                str(row["source_path"]).casefold()
                for row in connection.execute(
                    "SELECT source_path FROM local_analysis_items "
                    "WHERE job_id=? AND asset_id=?",
                    (job_id, asset.asset_id),  # type: ignore[attr-defined]
                )
            ]
        self.assertEqual(
            enrolled,
            [str(second_path.resolve()).casefold()],
            "the asset enrols once, through the location that still exists",
        )


if __name__ == "__main__":
    unittest.main()
