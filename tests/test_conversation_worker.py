from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from beacon.catalog import catalog_file
from beacon.conversation_worker import (
    ConversationPlan,
    claim_next_thread,
    run_worker_once,
    validate_loopback_endpoint,
)
from beacon.database import SCHEMA_VERSION, database_integrity
from beacon.desk import create_human_thread, thread_detail
from beacon.local_analysis import create_local_analysis_job


class FakeAdapter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.results: list[dict] = []

    def plan(self, messages: list[dict[str, str]]) -> ConversationPlan:
        if self.fail:
            raise RuntimeError("synthetic local model failure")
        self.asserted_history = messages
        return ConversationPlan(("waterfall",))

    def respond(
        self,
        messages: list[dict[str, str]],
        results: list[dict],
    ) -> str:
        self.results = results
        return "I found one grounded catalog match [1]."


class ConversationWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "beacon.db"
        self.source = self.root / "Iceland-waterfall.mov"
        self.source.write_bytes(b"synthetic waterfall footage")
        self.asset = catalog_file(
            self.source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_loopback_endpoint_is_mandatory(self) -> None:
        self.assertEqual(
            validate_loopback_endpoint("http://127.0.0.1:11434/"),
            "http://127.0.0.1:11434",
        )
        with self.assertRaisesRegex(ValueError, "loopback"):
            validate_loopback_endpoint("https://models.example.com")

    def test_worker_answers_once_with_grounded_asset_card(self) -> None:
        thread_id = create_human_thread(
            self.db,
            subject="Find the waterfall footage",
            body="Please find my Iceland waterfall clip.",
        )
        adapter = FakeAdapter()

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
            worker_id="fixture-worker",
        )

        self.assertEqual(result.state, "complete")
        self.assertEqual(result.thread_id, thread_id)
        self.assertEqual(result.result_count, 1)
        self.assertEqual(adapter.results[0]["id"], self.asset.asset_id)
        detail = thread_detail(self.db, thread_id)
        assert detail is not None
        self.assertEqual(detail["state"], "awaiting_human")
        self.assertEqual(len(detail["messages"]), 2)
        response = detail["messages"][-1]
        self.assertEqual(response["author"], "beacon")
        self.assertEqual(
            response["result_cards"][0]["asset_id"],
            self.asset.asset_id,
        )
        self.assertIn(
            "waterfall",
            response["result_cards"][0]["match_reason"].lower(),
        )
        self.assertEqual(
            database_integrity(self.db)["schema_version"],
            SCHEMA_VERSION,
        )

        idle = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
            worker_id="fixture-worker-2",
        )
        self.assertEqual(idle.state, "idle")

    def test_active_lease_prevents_duplicate_worker_claim(self) -> None:
        thread_id = create_human_thread(
            self.db,
            subject="One worker only",
            body="Do not answer this twice.",
        )
        first, state = claim_next_thread(
            self.db,
            endpoint="http://127.0.0.1:11434",
            model="fixture-model",
            worker_id="first",
        )
        second, second_state = claim_next_thread(
            self.db,
            endpoint="http://127.0.0.1:11434",
            model="fixture-model",
            worker_id="second",
        )

        self.assertEqual(state, "claimed")
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first.thread_id, thread_id)
        self.assertIsNone(second)
        self.assertEqual(second_state, "idle")

    def test_worker_pauses_without_claiming_during_catalog_analysis(self) -> None:
        create_human_thread(
            self.db,
            subject="Wait for analysis",
            body="This must remain queued.",
        )
        job_id = create_local_analysis_job(
            self.db,
            model="fixture-analysis",
        )
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "UPDATE local_analysis_jobs SET state='running' WHERE id=?",
                (job_id,),
            )
            connection.commit()
        finally:
            connection.close()

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=FakeAdapter(),
        )

        self.assertEqual(result.state, "analysis_running")
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM beacon_worker_runs"
                ).fetchone()[0],
                0,
            )
        finally:
            connection.close()

    def test_model_failure_is_durable_and_thread_remains_queued(self) -> None:
        thread_id = create_human_thread(
            self.db,
            subject="Recover after failure",
            body="Keep this queued if the model fails.",
        )

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=FakeAdapter(fail=True),
            worker_id="fixture-worker",
        )

        self.assertEqual(result.state, "failed")
        detail = thread_detail(self.db, thread_id)
        assert detail is not None
        self.assertEqual(detail["state"], "queued_for_beacon")
        connection = sqlite3.connect(self.db)
        try:
            state, error = connection.execute(
                "SELECT state,error FROM beacon_worker_runs"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(state, "failed")
        self.assertIn("synthetic local model failure", error)


if __name__ == "__main__":
    unittest.main()
