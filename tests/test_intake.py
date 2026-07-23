from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from beacon.catalog import CatalogResult, catalog_file
from beacon.intake import (
    create_intake_job,
    intake_job_detail,
    list_intake_jobs,
    pause_intake_job,
    recover_intake_jobs,
    request_intake_cancel,
    retry_intake_failures,
    run_intake_job,
)


class IntakeJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inbox = self.root / "inbox"
        self.inbox.mkdir()
        self.db = self.root / "runtime" / "beacon.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, relative: str, content: bytes) -> Path:
        path = self.inbox / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _create(self, limit: int | None = None) -> str:
        return create_intake_job(
            self.db,
            source_root=self.inbox,
            allowed_roots=(self.inbox,),
            item_limit=limit,
        )

    def test_recursive_snapshot_is_deterministic_and_bounded(self) -> None:
        self._write("z-last.txt", b"z")
        self._write("nested/b-first.txt", b"bb")
        self._write("nested/a-first.txt", b"aaa")

        first_id = self._create(limit=2)
        second_id = self._create(limit=2)
        jobs = {job["id"]: job for job in list_intake_jobs(self.db)}

        self.assertEqual(jobs[first_id]["total_items"], 2)
        self.assertEqual(jobs[first_id]["total_bytes"], 5)
        self.assertEqual(
            jobs[first_id]["snapshot_sha256"],
            jobs[second_id]["snapshot_sha256"],
        )
        with sqlite3.connect(self.db) as connection:
            paths = [
                row[0]
                for row in connection.execute(
                    """
                    SELECT relative_path FROM intake_items
                    WHERE job_id = ? ORDER BY relative_path
                    """,
                    (first_id,),
                )
            ]
        connection.close()
        self.assertEqual(paths, ["nested/a-first.txt", "nested/b-first.txt"])

    def test_job_catalogs_recursively_and_is_restart_idempotent(self) -> None:
        first = self._write("first.txt", b"first")
        second = self._write("nested/second.txt", b"second")
        before = {path: path.read_bytes() for path in (first, second)}
        job_id = self._create()

        result = run_intake_job(
            self.db,
            job_id,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )

        self.assertEqual(result.state, "complete")
        self.assertEqual(result.completed, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(first.read_bytes(), before[first])
        self.assertEqual(second.read_bytes(), before[second])
        detail = intake_job_detail(self.db, job_id)
        assert detail is not None
        self.assertEqual(detail["completed_count"], 2)
        self.assertEqual(detail["pending_count"], 0)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0],
                2,
            )
        connection.close()

    def test_cancel_stops_between_files_and_resume_finishes_pending(self) -> None:
        for index in range(3):
            self._write(f"{index}.txt", str(index).encode("ascii"))
        job_id = self._create()
        callback_count = 0

        def cancel_after_first() -> None:
            nonlocal callback_count
            callback_count += 1
            if callback_count == 1:
                request_intake_cancel(self.db, job_id)

        first_run = run_intake_job(
            self.db,
            job_id,
            include_media_probe=False,
            include_thumbnail_generation=False,
            progress_callback=cancel_after_first,
        )
        self.assertEqual(first_run.state, "cancelled")
        self.assertEqual(first_run.completed, 1)
        self.assertEqual(first_run.pending, 2)

        second_run = run_intake_job(
            self.db,
            job_id,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        self.assertEqual(second_run.state, "complete")
        self.assertEqual(second_run.completed, 3)

    def test_interrupted_running_item_recovers_as_paused_and_pending(self) -> None:
        self._write("recover.txt", b"recover")
        job_id = self._create()
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "UPDATE intake_jobs SET state = 'running' WHERE id = ?",
                (job_id,),
            )
            connection.execute(
                """
                UPDATE intake_items
                SET state = 'running', attempts = 1
                WHERE job_id = ?
                """,
                (job_id,),
            )
            connection.commit()
        connection.close()

        self.assertEqual(recover_intake_jobs(self.db), 1)
        detail = intake_job_detail(self.db, job_id)
        assert detail is not None
        self.assertEqual(detail["state"], "paused")
        self.assertEqual(detail["pending_count"], 1)
        self.assertEqual(detail["running_count"], 0)

    def test_pause_stops_after_current_file_and_can_resume(self) -> None:
        for index in range(3):
            self._write(f"pause-{index}.txt", str(index).encode("ascii"))
        job_id = self._create()
        callback_count = 0

        def pause_after_first() -> None:
            nonlocal callback_count
            callback_count += 1
            if callback_count == 1:
                pause_intake_job(self.db, job_id)

        first = run_intake_job(
            self.db,
            job_id,
            include_media_probe=False,
            include_thumbnail_generation=False,
            progress_callback=pause_after_first,
        )
        self.assertEqual(first.state, "paused")
        self.assertEqual(first.completed, 1)
        self.assertEqual(first.pending, 2)

        second = run_intake_job(
            self.db,
            job_id,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        self.assertEqual(second.state, "complete")
        self.assertEqual(second.completed, 3)

    def test_failure_is_recorded_and_retry_only_reprocesses_failure(self) -> None:
        source = self._write("retry.txt", b"retry")
        job_id = self._create()
        attempts = 0

        def flaky_cataloger(path: Path, db_path: Path, **kwargs: object) -> CatalogResult:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("synthetic transient read failure")
            return catalog_file(path, db_path, **kwargs)

        first = run_intake_job(
            self.db,
            job_id,
            cataloger=flaky_cataloger,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        self.assertEqual(first.state, "failed")
        self.assertEqual(first.failed, 1)
        detail = intake_job_detail(self.db, job_id)
        assert detail is not None
        self.assertIn("synthetic transient", detail["failures"][0]["error"])

        self.assertEqual(retry_intake_failures(self.db, job_id), 1)
        second = run_intake_job(
            self.db,
            job_id,
            cataloger=flaky_cataloger,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        self.assertEqual(second.state, "complete")
        self.assertEqual(second.completed, 1)
        self.assertEqual(attempts, 2)
        self.assertEqual(source.read_bytes(), b"retry")

    def test_changed_source_fails_without_cataloging_stale_bytes(self) -> None:
        source = self._write("changed.txt", b"before")
        job_id = self._create()
        source.write_bytes(b"different size and content")

        result = run_intake_job(
            self.db,
            job_id,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )

        self.assertEqual(result.state, "failed")
        detail = intake_job_detail(self.db, job_id)
        assert detail is not None
        self.assertIn("changed after", detail["failures"][0]["error"])
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0],
                0,
            )
        connection.close()


if __name__ == "__main__":
    unittest.main()
