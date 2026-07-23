from __future__ import annotations

import sqlite3
import os
import tempfile
import unittest
from pathlib import Path

from beacon.catalog import catalog_file
from beacon.database import SCHEMA_VERSION, database_integrity
from beacon.local_analysis import (
    analysis_scope_preview,
    create_local_analysis_job,
    list_local_analysis_jobs,
    recover_local_analysis_jobs,
    retry_local_analysis_failures,
    request_local_analysis_cancel,
    run_local_analysis_job,
    _process_is_alive,
)


class LocalAnalysisJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "runtime" / "beacon.db"
        self.sources = self.root / "sources"
        self.sources.mkdir()
        for name, content in (
            ("one.txt", b"one"),
            ("two.txt", b"two"),
        ):
            source = self.sources / name
            source.write_bytes(content)
            catalog_file(
                source,
                self.db,
                stability_seconds=0,
                include_media_probe=False,
                include_thumbnail_generation=False,
            )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_worker_liveness_detects_current_and_missing_processes(self) -> None:
        self.assertTrue(_process_is_alive(os.getpid()))
        self.assertFalse(_process_is_alive(2_147_483_647))

    @staticmethod
    def _analyzer(endpoint: str, model: str, asset: dict[str, object]) -> dict:
        return {
            "title": Path(str(asset["source_path"])).stem.title(),
            "description": "Candidate derived from verified local context.",
            "media_category": "text fixture",
            "tags": ["local", "fixture"],
            "privacy_flags": ["none detected from bounded context"],
            "organization_suggestion": "Leave in test scope; no move authorized.",
            "confidence": 0.8,
        }

    def test_local_job_imports_checksum_bound_candidates(self) -> None:
        preview = analysis_scope_preview(self.db)
        self.assertEqual(preview["assets"], 2)
        job_id = create_local_analysis_job(self.db, model="fixture-model")

        result = run_local_analysis_job(
            self.db, job_id, analyzer=self._analyzer
        )

        self.assertEqual(result.state, "complete")
        self.assertEqual(result.completed, 2)
        self.assertEqual(result.failed, 0)
        [job] = list_local_analysis_jobs(self.db)
        self.assertEqual(job["id"], job_id)
        self.assertEqual(job["completed_count"], 2)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM analysis_results"
                ).fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT SUM(external_inference) FROM analysis_runs"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT MIN(attempts),MAX(attempts) FROM local_analysis_items"
                ).fetchone(),
                (1, 1),
            )
        finally:
            connection.close()
        self.assertEqual(analysis_scope_preview(self.db)["assets"], 0)
        self.assertEqual(database_integrity(self.db)["schema_version"], SCHEMA_VERSION)

    def test_percentage_confidence_is_normalized_with_provenance(self) -> None:
        def percentage_analyzer(
            endpoint: str, model: str, asset: dict[str, object]
        ) -> dict:
            result = self._analyzer(endpoint, model, asset)
            result["confidence"] = 95
            return result

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        result = run_local_analysis_job(
            self.db, job_id, analyzer=percentage_analyzer
        )

        self.assertEqual(result.state, "complete")
        connection = sqlite3.connect(self.db)
        try:
            rows = connection.execute(
                "SELECT confidence,provenance_json FROM analysis_results"
            ).fetchall()
            self.assertTrue(all(row[0] == 0.95 for row in rows))
            self.assertTrue(
                all("percentage-style" in row[1] for row in rows)
            )
        finally:
            connection.close()

    def test_empty_organization_suggestion_gets_safe_fallback(self) -> None:
        def empty_suggestion_analyzer(
            endpoint: str, model: str, asset: dict[str, object]
        ) -> dict:
            result = self._analyzer(endpoint, model, asset)
            result["organization_suggestion"] = ""
            return result

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        result = run_local_analysis_job(
            self.db, job_id, analyzer=empty_suggestion_analyzer
        )

        self.assertEqual(result.state, "complete")
        connection = sqlite3.connect(self.db)
        try:
            payload, provenance = connection.execute(
                "SELECT payload_json,provenance_json FROM analysis_results LIMIT 1"
            ).fetchone()
            self.assertIn("Human review is required", payload)
            self.assertIn("empty organization suggestion", provenance)
        finally:
            connection.close()

    def test_interrupted_item_recovers_to_pending(self) -> None:
        job_id = create_local_analysis_job(self.db, model="fixture-model")
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "UPDATE local_analysis_jobs SET state='running' WHERE id=?",
                (job_id,),
            )
            connection.execute(
                """
                UPDATE local_analysis_items SET state='running'
                WHERE id=(SELECT id FROM local_analysis_items WHERE job_id=? LIMIT 1)
                """,
                (job_id,),
            )
            connection.commit()
        finally:
            connection.close()

        self.assertEqual(recover_local_analysis_jobs(self.db), 1)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT state FROM local_analysis_jobs WHERE id=?", (job_id,)
                ).fetchone()[0],
                "paused",
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM local_analysis_items WHERE job_id=? AND state='pending'",
                    (job_id,),
                ).fetchone()[0],
                2,
            )
        finally:
            connection.close()

    def test_cancel_stops_between_assets_and_preserves_pending(self) -> None:
        job_id = create_local_analysis_job(self.db, model="fixture-model")
        callbacks = 0

        def cancel_after_first() -> None:
            nonlocal callbacks
            callbacks += 1
            if callbacks == 1:
                request_local_analysis_cancel(self.db, job_id)

        result = run_local_analysis_job(
            self.db,
            job_id,
            analyzer=self._analyzer,
            progress_callback=cancel_after_first,
        )

        self.assertEqual(result.state, "cancelled")
        self.assertEqual(result.completed, 1)
        self.assertEqual(result.pending, 1)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT SUM(attempts) FROM local_analysis_items WHERE job_id=?",
                    (job_id,),
                ).fetchone()[0],
                1,
            )
        finally:
            connection.close()

    def test_failed_items_can_retry_in_the_same_job(self) -> None:
        calls = 0

        def fail_once(endpoint: str, model: str, asset: dict[str, object]) -> dict:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("bounded fixture failure")
            return self._analyzer(endpoint, model, asset)

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        first = run_local_analysis_job(self.db, job_id, analyzer=fail_once)
        self.assertEqual(first.state, "partial")
        self.assertEqual(retry_local_analysis_failures(self.db, job_id), 1)
        second = run_local_analysis_job(
            self.db, job_id, analyzer=self._analyzer
        )
        self.assertEqual(second.state, "complete")
        self.assertEqual(second.completed, 2)
