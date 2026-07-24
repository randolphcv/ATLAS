from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import Callable

from beacon.catalog import catalog_file
from beacon.conversation_worker import (
    AgentAction,
    AgentGoal,
    AgentResponse,
    _candidate_series_hint,
    _is_nonproduction_path,
    _search_catalog_tool,
    claim_next_thread,
    run_worker_once,
    validate_loopback_endpoint,
)
from beacon.database import SCHEMA_VERSION, database_integrity
from beacon.desk import create_human_thread, reply_to_thread, thread_detail
from beacon.local_analysis import create_local_analysis_job
from beacon.metadata import save_asset_metadata

ActionFactory = Callable[
    [list[dict[str, str]], list[dict], list[dict]],
    AgentAction,
]


class FakeAdapter:
    def __init__(
        self,
        actions: list[AgentAction | ActionFactory] | None = None,
        *,
        fail: bool = False,
        goal: AgentGoal | None = None,
    ) -> None:
        self.actions = list(actions or [])
        self.fail = fail
        self.goal = goal or AgentGoal(
            request_summary="Handle the latest human request.",
            requires_catalog_evidence=True,
        )
        self.calls: list[dict] = []

    def understand(self, messages: list[dict[str, str]]) -> AgentGoal:
        if self.fail:
            raise RuntimeError("synthetic local model failure")
        return self.goal

    def decide(
        self,
        _goal: AgentGoal,
        messages: list[dict[str, str]],
        observations: list[dict],
        available_assets: list[dict],
    ) -> AgentAction:
        if self.fail:
            raise RuntimeError("synthetic local model failure")
        self.calls.append(
            {
                "messages": messages,
                "observations": observations,
                "available_assets": available_assets,
            }
        )
        if self.actions:
            action = self.actions.pop(0)
            if callable(action):
                return action(messages, observations, available_assets)
            return action
        if not observations:
            return AgentAction(
                "search_catalog",
                queries=("waterfall",),
                media_type="video",
                result_limit=4,
                decision_summary="The request needs catalog evidence.",
            )
        return AgentAction(
            "respond",
            message="I found the waterfall clip.",
            selected_asset_ids=(
                str(available_assets[0]["asset_id"]),
            ) if available_assets else (),
            decision_summary="The observed match answers the request.",
        )

    def compose(
        self,
        _goal: AgentGoal,
        _messages: list[dict[str, str]],
        _available_assets: list[dict],
        draft: AgentAction,
    ) -> AgentResponse:
        return AgentResponse(
            message=draft.message,
            selected_asset_ids=draft.selected_asset_ids,
            request_fully_satisfied=True,
        )


def _respond_with_first(
    _messages: list[dict[str, str]],
    _observations: list[dict],
    available_assets: list[dict],
) -> AgentAction:
    return AgentAction(
        "respond",
        message="This is the grounded result I selected.",
        selected_asset_ids=(str(available_assets[0]["asset_id"]),),
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

    def _catalog_named(
        self,
        filename: str,
        *,
        title: str,
        description: str,
        people: list[str] | None = None,
    ) -> str:
        source = self.root / filename
        source.write_bytes(filename.encode("utf-8"))
        asset = catalog_file(
            source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        save_asset_metadata(
            self.db,
            asset.asset_id,
            {
                "display_title": title,
                "description": description,
                "people": people or [],
            },
            updated_by="human",
            source="test",
        )
        return asset.asset_id

    def test_loopback_endpoint_is_mandatory(self) -> None:
        self.assertEqual(
            validate_loopback_endpoint("http://127.0.0.1:11434/"),
            "http://127.0.0.1:11434",
        )
        with self.assertRaisesRegex(ValueError, "loopback"):
            validate_loopback_endpoint("https://models.example.com")

    def test_agent_searches_then_answers_with_one_grounded_card(self) -> None:
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
        self.assertEqual(len(adapter.calls), 2)
        self.assertEqual(
            adapter.calls[1]["available_assets"][0]["asset_id"],
            self.asset.asset_id,
        )
        detail = thread_detail(self.db, thread_id)
        assert detail is not None
        self.assertEqual(detail["state"], "awaiting_human")
        response = detail["messages"][-1]
        self.assertEqual(response["author"], "beacon")
        self.assertEqual(
            response["result_cards"][0]["asset_id"],
            self.asset.asset_id,
        )
        self.assertEqual(
            database_integrity(self.db)["schema_version"],
            SCHEMA_VERSION,
        )
        with closing(sqlite3.connect(self.db)) as connection:
            count = connection.execute(
                """
                SELECT COUNT(*) FROM system_events
                WHERE kind='beacon_conversation_agent'
                """
            ).fetchone()[0]
        self.assertEqual(count, 2)

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
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute(
                "UPDATE local_analysis_jobs SET state='running' WHERE id=?",
                (job_id,),
            )
            connection.commit()

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=FakeAdapter(),
        )

        self.assertEqual(result.state, "analysis_running")
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM beacon_worker_runs"
                ).fetchone()[0],
                0,
            )

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
        with closing(sqlite3.connect(self.db)) as connection:
            state, error = connection.execute(
                "SELECT state,error FROM beacon_worker_runs"
            ).fetchone()
        self.assertEqual(state, "failed")
        self.assertIn("synthetic local model failure", error)

    def test_agent_can_honor_no_search_without_a_code_router(self) -> None:
        thread_id = create_human_thread(
            self.db,
            subject="No catalog search",
            body="Confirm Beacon is active. Do not search the catalog.",
        )
        adapter = FakeAdapter(
            [
                AgentAction(
                    "respond",
                    message="I’m active, and I did not search your catalog.",
                )
            ]
        )

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
        )

        self.assertEqual(result.state, "complete")
        self.assertEqual(result.result_count, 0)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(adapter.calls[0]["observations"], [])
        detail = thread_detail(self.db, thread_id)
        assert detail is not None
        self.assertEqual(detail["messages"][-1]["result_cards"], [])

    def test_agent_can_retrieve_an_exact_filename_as_one_result(self) -> None:
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
            [
                AgentAction(
                    "search_catalog",
                    queries=("Iceland-waterfall.mov",),
                    media_type="video",
                    result_limit=1,
                ),
                _respond_with_first,
            ]
        )

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
        )

        self.assertEqual(result.result_count, 1)
        detail = thread_detail(self.db, thread_id)
        assert detail is not None
        self.assertEqual(
            detail["messages"][-1]["result_cards"][0]["asset_id"],
            self.asset.asset_id,
        )

    def test_only_agent_selected_observed_assets_become_cards(self) -> None:
        self._catalog_named(
            "waterfall-alternate.mov",
            title="Alternate waterfall",
            description="A different waterfall angle.",
        )
        thread_id = create_human_thread(
            self.db,
            subject="Choose a useful result",
            body="Find waterfall footage.",
        )

        def select_second(
            _messages: list[dict[str, str]],
            _observations: list[dict],
            available: list[dict],
        ) -> AgentAction:
            return AgentAction(
                "respond",
                message="I chose the second observed match.",
                selected_asset_ids=(str(available[1]["asset_id"]),),
            )

        adapter = FakeAdapter(
            [
                AgentAction(
                    "search_catalog",
                    queries=("waterfall",),
                    media_type="video",
                    result_limit=4,
                ),
                select_second,
            ]
        )

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
        )

        self.assertEqual(result.result_count, 1)
        detail = thread_detail(self.db, thread_id)
        assert detail is not None
        [card] = detail["messages"][-1]["result_cards"]
        self.assertEqual(
            card["asset_id"],
            adapter.calls[1]["available_assets"][1]["asset_id"],
        )

    def test_agent_can_search_inspect_and_choose_three_distinct_food_images(
        self,
    ) -> None:
        expected = {
            self._catalog_named(
                "guacamole.jpg",
                title="Guacamole Preparation",
                description="Hands preparing food in a kitchen.",
            ),
            self._catalog_named(
                "birthday-cake.jpg",
                title="Birthday Cake",
                description="A decorated food dessert with candles.",
            ),
            self._catalog_named(
                "tacos.jpg",
                title="Street Tacos",
                description="A plated food meal at a restaurant.",
            ),
        }
        create_human_thread(
            self.db,
            subject="Three unique food images",
            body="Great! Now find me three unique images involving food.",
        )

        def inspect_all(
            _messages: list[dict[str, str]],
            _observations: list[dict],
            available: list[dict],
        ) -> AgentAction:
            return AgentAction(
                "inspect_assets",
                asset_ids=tuple(
                    str(item["asset_id"]) for item in available[:3]
                ),
                decision_summary="Inspect the candidates for scene diversity.",
            )

        def select_three(
            _messages: list[dict[str, str]],
            observations: list[dict],
            available: list[dict],
        ) -> AgentAction:
            self.assertEqual(observations[-1]["tool"], "inspect_assets")
            self.assertTrue(
                all(item.get("inspection") for item in available[:3])
            )
            return AgentAction(
                "respond",
                message=(
                    "I found three different food scenes: preparation, "
                    "dessert, and a plated meal."
                ),
                selected_asset_ids=tuple(
                    str(item["asset_id"]) for item in available[:3]
                ),
            )

        adapter = FakeAdapter(
            [
                AgentAction(
                    "search_catalog",
                    queries=("food",),
                    media_type="photo",
                    result_limit=8,
                ),
                inspect_all,
                select_three,
            ]
        )

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
        )

        self.assertEqual(result.state, "complete")
        self.assertEqual(result.result_count, 3)
        selected = {
            item["asset_id"]
            for item in adapter.calls[-1]["available_assets"][:3]
        }
        self.assertEqual(selected, expected)

    def test_exploratory_search_interleaves_probable_capture_series(
        self,
    ) -> None:
        for filename, title in (
            ("IMG_0413.jpg", "Guacamole variation one"),
            ("IMG_0414.jpg", "Guacamole variation two"),
            ("IMG_9477.jpg", "Food presentation at an event"),
            ("IMG_9493.jpg", "Dark chocolate close-up"),
        ):
            self._catalog_named(
                filename,
                title=title,
                description="A photo involving food.",
            )

        results = _search_catalog_tool(
            self.db,
            AgentAction(
                "search_catalog",
                queries=("food",),
                match_strategy="any",
                media_type="photo",
                result_limit=3,
            ),
        )

        self.assertEqual(len(results), 3)
        self.assertEqual(
            len({_candidate_series_hint(item) for item in results}),
            3,
        )

    def test_unobserved_asset_selection_is_rejected_and_agent_can_recover(
        self,
    ) -> None:
        create_human_thread(
            self.db,
            subject="Ground every result",
            body="Find the waterfall.",
        )
        adapter = FakeAdapter(
            [
                AgentAction(
                    "respond",
                    message="I invented this.",
                    selected_asset_ids=("not-an-observed-asset",),
                ),
                AgentAction(
                    "search_catalog",
                    queries=("waterfall",),
                    media_type="video",
                    result_limit=2,
                ),
                _respond_with_first,
            ]
        )

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
        )

        self.assertEqual(result.state, "complete")
        self.assertEqual(result.result_count, 1)
        self.assertIn(
            "not observed",
            adapter.calls[1]["observations"][0]["error"],
        )

    def test_model_identified_correction_is_retained_for_later_turns(
        self,
    ) -> None:
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
        correcting = FakeAdapter(
            [
                AgentAction(
                    "respond",
                    message="Understood. I’ll keep that correction in mind.",
                )
            ],
            goal=AgentGoal(
                request_summary="Acknowledge and retain the correction.",
                requires_catalog_evidence=False,
                latest_human_corrects_beacon=True,
            ),
        )
        self.assertEqual(
            run_worker_once(
                self.db,
                model="fixture-model",
                adapter=correcting,
            ).state,
            "complete",
        )
        reply_to_thread(
            self.db,
            thread_id,
            "What did I mean before?",
        )
        later = FakeAdapter(
            [AgentAction("respond", message="You meant only Iceland.")]
        )

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=later,
        )

        self.assertEqual(result.state, "complete")
        self.assertIn(
            "Thread-scoped human corrections",
            later.calls[0]["messages"][0]["body"],
        )
        with closing(sqlite3.connect(self.db)) as connection:
            row = connection.execute(
                """
                SELECT kind,note FROM beacon_conversation_feedback
                WHERE thread_id=?
                """,
                (thread_id,),
            ).fetchone()
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

    def test_agent_controls_multi_concept_cooccurrence_search(self) -> None:
        together = self._catalog_named(
            "connor-and-jules.jpg",
            title="Connor and Jules together",
            description="A portrait containing Connor and Jules.",
            people=["Connor", "Jules"],
        )
        self._catalog_named(
            "connor-only.jpg",
            title="Connor alone",
            description="A portrait containing Connor.",
            people=["Connor"],
        )
        self._catalog_named(
            "jules-only.jpg",
            title="Jules alone",
            description="A portrait containing Jules.",
            people=["Jules"],
        )
        thread_id = create_human_thread(
            self.db,
            subject="Connor and Jules",
            body="Find me an image of Connor and Jules.",
        )
        adapter = FakeAdapter(
            [
                AgentAction(
                    "search_catalog",
                    queries=("Connor", "Jules"),
                    match_strategy="all",
                    media_type="photo",
                    result_limit=4,
                ),
                _respond_with_first,
            ]
        )

        result = run_worker_once(
            self.db,
            model="fixture-model",
            adapter=adapter,
        )

        self.assertEqual(result.state, "complete")
        self.assertEqual(result.result_count, 1)
        detail = thread_detail(self.db, thread_id)
        assert detail is not None
        [card] = detail["messages"][-1]["result_cards"]
        self.assertEqual(card["asset_id"], together)


if __name__ == "__main__":
    unittest.main()
