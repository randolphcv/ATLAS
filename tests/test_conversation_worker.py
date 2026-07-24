from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from beacon.catalog import catalog_file
from beacon.conversation_worker import (
    ConversationPlan,
    ConversationResponse,
    _is_nonproduction_path,
    claim_next_thread,
    run_worker_once,
    validate_loopback_endpoint,
)
from beacon.database import SCHEMA_VERSION, database_integrity
from beacon.desk import create_human_thread, reply_to_thread, thread_detail
from beacon.local_analysis import create_local_analysis_job
from beacon.metadata import save_asset_metadata


class FakeAdapter:
    def __init__(
        self,
        *,
        fail: bool = False,
        plan: ConversationPlan | None = None,
        used_references: tuple[int, ...] = (1,),
    ) -> None:
        self.fail = fail
        self.configured_plan = plan or ConversationPlan(("waterfall",))
        self.used_references = used_references
        self.results: list[dict] = []
        self.histories: list[list[dict[str, str]]] = []

    def plan(self, messages: list[dict[str, str]]) -> ConversationPlan:
        if self.fail:
            raise RuntimeError("synthetic local model failure")
        self.histories.append(messages)
        return self.configured_plan

    def respond(
        self,
        messages: list[dict[str, str]],
        results: list[dict],
    ) -> ConversationResponse:
        self.results = results
        references = ", ".join(f"[{item}]" for item in self.used_references)
        return ConversationResponse(
            f"I used these grounded catalog matches: {references}".strip(),
            self.used_references,
        )


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

    def test_explicit_no_search_overrides_model_plan_and_attaches_no_cards(
        self,
    ) -> None:
        thread_id = create_human_thread(
            self.db,
            subject="No catalog search",
            body="Confirm Beacon is active. Do not search the catalog.",
        )
        adapter = FakeAdapter(
            plan=ConversationPlan(("beacon", "waterfall"), max_results=8),
        )

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
        )

        self.assertEqual(result.state, "complete")
        self.assertEqual(result.result_count, 0)
        self.assertEqual(adapter.results, [])
        detail = thread_detail(self.db, thread_id)
        assert detail is not None
        self.assertEqual(detail["messages"][-1]["result_cards"], [])

    def test_exact_filename_defaults_to_one_exact_result(self) -> None:
        other = self.root / "other-waterfall.mov"
        other.write_bytes(b"another waterfall")
        catalog_file(
            other,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        thread_id = create_human_thread(
            self.db,
            subject="Find one exact file",
            body="Please find Iceland-waterfall.mov.",
        )
        adapter = FakeAdapter(
            plan=ConversationPlan(("waterfall", "mov"), max_results=8),
        )

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
        )

        self.assertEqual(result.result_count, 1)
        self.assertEqual(len(adapter.results), 1)
        self.assertEqual(adapter.results[0]["id"], self.asset.asset_id)
        detail = thread_detail(self.db, thread_id)
        assert detail is not None
        self.assertEqual(
            detail["messages"][-1]["result_cards"][0]["asset_id"],
            self.asset.asset_id,
        )

    def test_only_used_evidence_becomes_result_cards(self) -> None:
        second = self.root / "waterfall-alternate.mov"
        second.write_bytes(b"alternate waterfall")
        catalog_file(
            second,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        thread_id = create_human_thread(
            self.db,
            subject="Choose a useful result",
            body="Find waterfall footage.",
        )
        adapter = FakeAdapter(
            plan=ConversationPlan(("waterfall",), max_results=3),
            used_references=(2,),
        )

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
        )

        self.assertEqual(len(adapter.results), 2)
        self.assertEqual(result.result_count, 1)
        detail = thread_detail(self.db, thread_id)
        assert detail is not None
        [card] = detail["messages"][-1]["result_cards"]
        self.assertEqual(card["asset_id"], adapter.results[1]["id"])

    def test_explicit_correction_is_retained_for_the_thread(self) -> None:
        thread_id = create_human_thread(
            self.db,
            subject="Learn from correction",
            body="Find waterfall footage.",
        )
        run_worker_once(
            self.db,
            model="fixture-model",
            adapter=FakeAdapter(),
        )
        reply_to_thread(
            self.db,
            thread_id,
            "That's wrong. I meant only the Iceland waterfall.",
        )
        adapter = FakeAdapter()

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
        )

        self.assertEqual(result.state, "complete")
        self.assertIn(
            "Thread-scoped human corrections",
            adapter.histories[0][0]["body"],
        )
        connection = sqlite3.connect(self.db)
        try:
            row = connection.execute(
                """
                SELECT kind,note FROM beacon_conversation_feedback
                WHERE thread_id=?
                """,
                (thread_id,),
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row[0], "correction")
        self.assertIn("I meant only", row[1])

    def test_live_retrieval_excludes_known_test_and_sandbox_paths(self) -> None:
        self.assertTrue(
            _is_nonproduction_path(
                r"C:\ProgramData\ATLAS\Beacon\use-tests\UseTest-01\item.mov"
            )
        )
        self.assertTrue(
            _is_nonproduction_path(
                r"C:\ProgramData\ATLAS\Beacon\sandbox\inbox\item.mov"
            )
        )
        self.assertFalse(
            _is_nonproduction_path(r"J:\Projects\Client\item.mov")
        )

    def test_explicit_retrieval_phrase_forces_multi_person_cooccurrence(
        self,
    ) -> None:
        save_asset_metadata(
            self.db,
            self.asset.asset_id,
            {
                "display_title": "Connor and Jules together",
                "description": "A portrait containing Connor and Jules.",
                "people": ["Connor", "Jules"],
            },
            updated_by="human",
            source="test",
        )
        for filename, person in (
            ("connor-only.jpg", "Connor"),
            ("jules-only.jpg", "Jules"),
        ):
            source = self.root / filename
            source.write_bytes(person.encode("utf-8"))
            cataloged = catalog_file(
                source,
                self.db,
                stability_seconds=0,
                include_media_probe=False,
                include_thumbnail_generation=False,
            )
            save_asset_metadata(
                self.db,
                cataloged.asset_id,
                {
                    "display_title": f"{person} alone",
                    "description": f"A portrait containing {person}.",
                    "people": [person],
                },
                updated_by="human",
                source="test",
            )
        thread_id = create_human_thread(
            self.db,
            subject="Connor and Jules",
            body="Find me an image of Connor and Jules.",
        )
        adapter = FakeAdapter(fail=True)

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
        )

        self.assertEqual(result.state, "complete")
        self.assertEqual(result.result_count, 1)
        self.assertEqual(len(adapter.results), 1)
        self.assertEqual(adapter.results[0]["id"], self.asset.asset_id)
        detail = thread_detail(self.db, thread_id)
        assert detail is not None
        [card] = detail["messages"][-1]["result_cards"]
        self.assertEqual(card["asset_id"], self.asset.asset_id)


if __name__ == "__main__":
    unittest.main()
