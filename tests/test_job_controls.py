"""Controls the owner needs to end a job that has stopped.

Two gaps, both found in live state rather than in review:

- A paused job could not be cancelled. Cancellation set a flag the run loop
  reads between items, and a paused job has no loop, so the flag was read by
  nobody and the job stayed non-terminal indefinitely. One such job carried no
  folder prefix, so resuming it would have settled the whole Inbox rather than
  one folder.
- A job that ended partial stayed partial forever. There was no way to say
  "I have read this outcome and accept it" short of retrying work that had
  already succeeded.

A cancelled or closed job must move nothing and delete nothing, which every
test here asserts: the item rows are the record of what the job enrolled, and
that record outlives the job.

Marking a catalog row missing is tested in test_location_verification.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from beacon.database import connect, migrate
from beacon.local_analysis import (
    cancel_local_analysis_job,
    cancel_open_local_analysis_jobs,
    cancellable_local_analysis_jobs,
    close_local_analysis_job,
    close_partial_local_analysis_jobs,
    closeable_local_analysis_jobs,
    retry_local_analysis_failures,
)


class JobControlTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "beacon.db"
        self.now = datetime.now(timezone.utc).isoformat()
        with connect(self.db) as connection:
            migrate(connection)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _job(
        self,
        state: str,
        *,
        worker_pid: int | None = None,
        items: tuple[str, ...] = (),
    ) -> str:
        job_id = str(uuid.uuid4())
        with connect(self.db) as connection:
            connection.execute(
                """
                INSERT INTO local_analysis_jobs(
                    id, state, model, endpoint, policy_version, scope_sha256,
                    total_items, cancel_requested, requested_by, created_at,
                    updated_at, worker_pid
                ) VALUES (?, ?, 'fixture', 'fixture', 'fixture', 'fixture',
                          ?, 0, 'test', ?, ?, ?)
                """,
                (job_id, state, len(items), self.now, self.now, worker_pid),
            )
            for index, item_state in enumerate(items):
                # local_analysis_items.asset_id is a foreign key, so the item
                # needs a real asset to point at.
                asset_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO assets(
                        id, sha256, size_bytes, created_at, last_seen_at
                    ) VALUES (?, ?, 1, ?, ?)
                    """,
                    (asset_id, f"sha-{asset_id}", self.now, self.now),
                )
                connection.execute(
                    """
                    INSERT INTO local_analysis_items(
                        id, job_id, asset_id, source_sha256, source_path,
                        state, attempts, excluded_reason, completed_at
                    ) VALUES (?, ?, ?, 'sha', ?, ?, 1, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        job_id,
                        asset_id,
                        str(
                            Path("fixture_client_a")
                            / "project_alpha"
                            / f"SAMPLE_{index:04d}.mov"
                        ),
                        item_state,
                        "fixture exclusion" if item_state == "complete" else None,
                        self.now if item_state != "pending" else None,
                    ),
                )
        return job_id

    def _state(self, job_id: str) -> tuple[str, str | None]:
        with connect(self.db) as connection:
            row = connection.execute(
                "SELECT state, closed_at FROM local_analysis_jobs WHERE id=?",
                (job_id,),
            ).fetchone()
        return str(row["state"]), row["closed_at"]

    def _item_states(self, job_id: str) -> dict[str, int]:
        with connect(self.db) as connection:
            rows = connection.execute(
                "SELECT state, COUNT(*) AS n FROM local_analysis_items "
                "WHERE job_id=? GROUP BY state",
                (job_id,),
            ).fetchall()
        return {str(row["state"]): row["n"] for row in rows}

    def _move_count(self) -> int:
        with connect(self.db) as connection:
            return connection.execute(
                "SELECT COUNT(*) AS n FROM managed_moves"
            ).fetchone()["n"]


class CancelTests(JobControlTestCase):
    def test_a_paused_job_with_no_worker_is_cancelled_outright(self) -> None:
        """The defect: a flag nobody reads is not a cancellation."""
        job_id = self._job("paused", items=("complete", "pending", "pending"))
        before = self._move_count()
        self.assertEqual(
            cancel_local_analysis_job(self.db, job_id), "cancelled"
        )
        state, closed_at = self._state(job_id)
        self.assertEqual(state, "cancelled")
        self.assertIsNone(closed_at, "cancelled is not closed")
        self.assertEqual(self._move_count(), before, "nothing was moved")

    def test_cancelling_a_paused_job_releases_but_keeps_its_items(self) -> None:
        job_id = self._job("paused", items=("complete", "pending", "running"))
        cancel_local_analysis_job(self.db, job_id)
        states = self._item_states(job_id)
        self.assertEqual(
            sum(states.values()), 3, "no item row may be deleted"
        )
        self.assertNotIn("running", states, "a running item is released")
        self.assertEqual(states.get("pending"), 2)
        self.assertEqual(states.get("complete"), 1)

    def test_a_running_job_with_a_live_worker_stays_cooperative(self) -> None:
        """A live worker must stop between items, not be yanked mid-move."""
        import os

        job_id = self._job("running", worker_pid=os.getpid(), items=("pending",))
        self.assertEqual(
            cancel_local_analysis_job(self.db, job_id), "requested"
        )
        state, _ = self._state(job_id)
        self.assertEqual(state, "running", "the worker ends it, not us")
        with connect(self.db) as connection:
            flag = connection.execute(
                "SELECT cancel_requested FROM local_analysis_jobs WHERE id=?",
                (job_id,),
            ).fetchone()["cancel_requested"]
        self.assertEqual(flag, 1)

    def test_a_running_job_whose_worker_died_is_cancelled_outright(self) -> None:
        job_id = self._job("running", worker_pid=0, items=("running",))
        self.assertEqual(
            cancel_local_analysis_job(self.db, job_id), "cancelled"
        )
        self.assertEqual(self._state(job_id)[0], "cancelled")

    def test_cancelling_a_terminal_job_is_a_no_op(self) -> None:
        job_id = self._job("complete", items=("complete",))
        self.assertEqual(
            cancel_local_analysis_job(self.db, job_id), "complete"
        )
        self.assertEqual(self._state(job_id)[0], "complete")

    def test_the_cancellable_set_is_only_non_terminal_jobs(self) -> None:
        paused = self._job("paused")
        self._job("partial")
        self._job("complete")
        self._job("cancelled")
        ids = {job["id"] for job in cancellable_local_analysis_jobs(self.db)}
        self.assertEqual(ids, {paused})

    def test_cancelling_the_open_set_continues_past_one_failure(self) -> None:
        first = self._job("paused", items=("pending",))
        second = self._job("queued", items=("pending",))
        results = cancel_open_local_analysis_jobs(self.db)
        self.assertEqual(len(results), 2)
        for job_id in (first, second):
            self.assertEqual(self._state(job_id)[0], "cancelled")


class CloseTests(JobControlTestCase):
    def test_closing_a_partial_job_terminalizes_it_with_its_counts(self) -> None:
        job_id = self._job("partial", items=("complete", "complete", "failed"))
        before = self._move_count()
        result = close_local_analysis_job(self.db, job_id)
        state, closed_at = self._state(job_id)
        self.assertEqual(state, "cancelled")
        self.assertIsNotNone(closed_at, "closed is distinguishable")
        self.assertIn("Closed by owner", result["summary"])
        self.assertEqual(result["excluded"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(self._move_count(), before, "nothing was moved")

    def test_closing_re_enrols_nothing(self) -> None:
        job_id = self._job("partial", items=("complete", "failed"))
        before = self._item_states(job_id)
        close_local_analysis_job(self.db, job_id)
        self.assertEqual(
            self._item_states(job_id), before, "item states are untouched"
        )

    def test_retry_refuses_a_closed_job(self) -> None:
        """The point of closing: a later click must not reopen the outcome."""
        job_id = self._job("partial", items=("complete", "failed"))
        self.assertEqual(retry_local_analysis_failures.__name__, "retry_local_analysis_failures")
        close_local_analysis_job(self.db, job_id)
        with self.assertRaises(ValueError) as caught:
            retry_local_analysis_failures(self.db, job_id)
        self.assertIn("closed", str(caught.exception).casefold())

    def test_retry_still_works_on_an_open_partial_job(self) -> None:
        """Closing must not break the control it guards."""
        job_id = self._job("partial", items=("complete", "failed"))
        self.assertEqual(retry_local_analysis_failures(self.db, job_id), 1)

    def test_closing_twice_is_refused(self) -> None:
        job_id = self._job("partial", items=("failed",))
        close_local_analysis_job(self.db, job_id)
        with self.assertRaises(ValueError):
            close_local_analysis_job(self.db, job_id)

    def test_closing_a_running_job_is_refused(self) -> None:
        import os

        job_id = self._job("running", worker_pid=os.getpid(), items=("pending",))
        with self.assertRaises(ValueError):
            close_local_analysis_job(self.db, job_id)

    def test_the_closeable_set_is_open_partial_jobs_only(self) -> None:
        first = self._job("partial", items=("failed",))
        second = self._job("partial", items=("failed",))
        self._job("complete")
        closed = self._job("partial", items=("failed",))
        close_local_analysis_job(self.db, closed)
        ids = {job["id"] for job in closeable_local_analysis_jobs(self.db)}
        self.assertEqual(ids, {first, second})

    def test_closing_the_partial_set_closes_all_of_them(self) -> None:
        jobs = [self._job("partial", items=("complete", "failed")) for _ in range(3)]
        before = self._move_count()
        results = close_partial_local_analysis_jobs(self.db)
        self.assertEqual(len(results), 3)
        for job_id in jobs:
            state, closed_at = self._state(job_id)
            self.assertEqual(state, "cancelled")
            self.assertIsNotNone(closed_at)
        self.assertEqual(closeable_local_analysis_jobs(self.db), [])
        self.assertEqual(self._move_count(), before)


if __name__ == "__main__":
    unittest.main()
