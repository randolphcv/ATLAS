from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from beacon.database import connect, database_integrity, migrate
from beacon.desk import (
    add_beacon_message,
    create_human_thread,
    desk_summary,
    list_threads,
    reply_to_thread,
    resolve_thread,
    seed_threads,
    thread_detail,
)
from beacon.desk_seeds import PILOT_DESK_THREADS


SEEDS = (
    {
        "seed_key": "test:blocker",
        "subject": "Confirm the safe boundary",
        "kind": "blocker",
        "priority": "important",
        "requires_approval": False,
        "body": "Tell Beacon when the bounded intake is stable.",
    },
    {
        "seed_key": "test:approval",
        "subject": "Choose the analysis boundary",
        "kind": "approval",
        "priority": "important",
        "requires_approval": True,
        "body": "Approve local-only analysis or provide another policy.",
    },
)


class BeaconDeskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "beacon.db"
        with connect(self.db) as connection:
            migrate(connection)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_schema_five_and_seed_are_idempotent(self) -> None:
        first = seed_threads(self.db, SEEDS)
        second = seed_threads(self.db, SEEDS)

        self.assertEqual(len(first), 2)
        self.assertEqual(second, [])
        self.assertEqual(database_integrity(self.db)["schema_version"], 5)
        self.assertEqual(desk_summary(self.db)["awaiting_human"], 2)
        self.assertEqual(len(list_threads(self.db)), 2)

    def test_plain_english_reply_queues_without_authorizing_file_action(self) -> None:
        thread_id = seed_threads(self.db, SEEDS)[0]
        message_id = reply_to_thread(
            self.db,
            thread_id,
            "The copy is complete. Use local analysis only.",
        )
        detail = thread_detail(self.db, thread_id)

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["state"], "queued_for_beacon")
        self.assertEqual(len(detail["messages"]), 2)
        self.assertEqual(detail["messages"][-1]["id"], message_id)
        self.assertEqual(detail["messages"][-1]["author"], "human")

        connection = sqlite3.connect(self.db)
        try:
            event = connection.execute(
                """
                SELECT details_json FROM system_events
                WHERE kind = 'beacon_desk'
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        finally:
            connection.close()
        self.assertIsNotNone(event)
        self.assertIn('"file_action_authorized": false', event[0])

    def test_new_request_and_beacon_response_form_a_durable_conversation(self) -> None:
        thread_id = create_human_thread(
            self.db,
            subject="Inspect the naming protocol",
            body="What should we settle before a large intake?",
        )
        self.assertEqual(desk_summary(self.db)["queued_for_beacon"], 1)

        add_beacon_message(
            self.db,
            thread_id,
            "Please define which parts of filenames are meaningful.",
        )
        detail = thread_detail(self.db, thread_id)

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["state"], "awaiting_human")
        self.assertEqual(
            [message["author"] for message in detail["messages"]],
            ["human", "beacon"],
        )

    def test_resolving_removes_thread_from_open_desk_and_does_not_reseed(self) -> None:
        thread_id = seed_threads(self.db, SEEDS)[0]
        resolve_thread(self.db, thread_id)
        seed_threads(self.db, SEEDS)

        self.assertNotIn(
            thread_id,
            {thread["id"] for thread in list_threads(self.db)},
        )
        detail = thread_detail(self.db, thread_id)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["state"], "resolved")

    def test_empty_or_oversized_user_content_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Subject is required"):
            create_human_thread(self.db, subject=" ", body="message")
        with self.assertRaisesRegex(ValueError, "8,000"):
            create_human_thread(
                self.db,
                subject="Long request",
                body="x" * 8001,
            )

    def test_pilot_seeds_distinguish_gates_from_optional_enrichment(self) -> None:
        inserted = seed_threads(self.db, PILOT_DESK_THREADS)
        rows = list_threads(self.db)

        self.assertEqual(len(inserted), 6)
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            sum(row["priority"] == "important" for row in rows),
            3,
        )
        self.assertEqual(
            sum(bool(row["requires_approval"]) for row in rows),
            2,
        )
        optional = [row for row in rows if row["priority"] == "normal"]
        self.assertTrue(
            all(str(row["latest_message"]).startswith("Optional enrichment") for row in optional)
        )


if __name__ == "__main__":
    unittest.main()
