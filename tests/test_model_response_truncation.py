"""A cut-off model response must not cost the item or the batch.

AGENTS.md section 10: model output is an untrusted input source, a malformed
field is retryable, an exhausted retry degrades rather than losing the item, and
no per-item failure aborts a batch.

The failure these tests pin down is specific. The request carries a JSON schema
with maxLength on every prose field, but the runtime's grammar does not enforce
length -- the catalog records the model returning a 419-character title against
a declared limit of 300 -- so nothing bounds a string the model starts except
the generation budget. When the budget lands inside a string, the response ends
mid-string and is not JSON. Three attempts that differ only in temperature,
while replaying the cut-off text and so growing the prompt against the same
budget, never once recovered from it.

One detail worth keeping written down, because it is what made the cause hard to
see: the offset in "Unterminated string starting at: line 1 column 44 (char 43)"
is where the unterminated string *opens*, not how long the response was. Two
failures reporting char 43 and char 1113 are not two different truncation
lengths. They are two responses cut off at the same budget, in different fields.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from beacon.catalog import catalog_file
from beacon.local_analysis import (
    ANALYSIS_CORRECTION_KEY,
    LOCAL_RESPONSE_ATTEMPTS,
    LOCAL_RESPONSE_TOKEN_BUDGET,
    LOCAL_RESPONSE_TOKEN_BUDGET_RETRY,
    _cut_off_reason,
    _default_analyzer,
    _ended_mid_string,
    _normalize_payload,
    _repair_truncated_json,
    create_local_analysis_job,
    run_local_analysis_job,
)

VALID_PAYLOAD = {
    "title": "Synthetic Text Fixture",
    "description": "A bounded synthetic fixture used as text evidence.",
    "content_observations": ["The fixture text names a synthetic subject."],
    "evidence_mode": "text_content",
    "media_category": "document",
    "tags": ["fixture", "synthetic"],
    "privacy_flags": [],
    "organization_suggestion": "Leave in test scope; no move authorized.",
    "stock_metadata": {},
    "confidence": 0.8,
}


def truncated_early() -> str:
    """Cut off inside the description, which no repair can make valid.

    The repair keeps the title and nothing else, so a required field is missing
    and only a fresh generation can produce a usable result. This is the shape
    that proves the retry does something.
    """
    return '{"title":"Synthetic Text Fixture","description":"' + "d" * 400


def truncated_late() -> str:
    """Cut off inside a trailing list, after every required field completed.

    The repair keeps the complete entries and drops the partial one whole, so
    the item needs no further generation at all.
    """
    ordered = {key: value for key, value in VALID_PAYLOAD.items() if key != "tags"}
    ordered["tags"] = ["fixture", "synthetic", "bounded"]
    text = json.dumps(ordered)
    head, separator, _ = text.rpartition('"bounded"]}')
    assert separator, "fixture must end with the tags list"
    return head + '"' + "b" * 300


def cut_off_response(content: str) -> dict[str, object]:
    """What the local runtime returns when it runs out of room.

    done_reason and eval_count are the runtime's own account of why it stopped.
    Beacon used to discard both, which is why this class of failure was recorded
    for four months as an unexplained decoder offset.
    """
    return {
        "message": {"content": content},
        "done": True,
        "done_reason": "length",
        "eval_count": LOCAL_RESPONSE_TOKEN_BUDGET,
    }


class TruncationEvidenceTests(unittest.TestCase):
    """What the recorded evidence does and does not mean."""

    def test_reported_offset_is_where_the_string_opens_not_the_length(self) -> None:
        document = '{"title":"Synthetic Fixture","description":"' + "d" * 50_000
        with self.assertRaises(json.JSONDecodeError) as caught:
            json.loads(document)

        # A 50,000-character response reports a column in the forties. The
        # offset is the opening quote of the field the cut landed in, so two
        # failures at char 43 and char 1113 are consistent with one budget.
        self.assertLess(caught.exception.pos, 100)
        self.assertIn("Unterminated string", str(caught.exception))
        self.assertGreater(len(document), 50_000)

    def test_a_cut_off_response_is_distinguishable_from_a_malformed_one(self) -> None:
        self.assertTrue(_ended_mid_string(truncated_early()))
        self.assertTrue(_ended_mid_string(truncated_late()))
        # A model that emits bad JSON of its own accord still closes its quotes.
        self.assertFalse(_ended_mid_string("{not-json"))
        self.assertFalse(_ended_mid_string('{"title":"done"}'))

    def test_the_runtime_reason_is_named_in_structural_form(self) -> None:
        reason = _cut_off_reason(cut_off_response(truncated_early()))
        assert reason is not None
        self.assertIn("generation budget", reason)
        self.assertIn(str(LOCAL_RESPONSE_TOKEN_BUDGET), reason)
        # No model output in the reason: it goes into an error field and the
        # audit trail, which carry counts and states, not content.
        self.assertNotIn("Synthetic", reason)
        self.assertNotIn("dddd", reason)

    def test_a_complete_response_is_not_reported_as_cut_off(self) -> None:
        self.assertIsNone(
            _cut_off_reason(
                {"message": {"content": "{}"}, "done_reason": "stop"}
            )
        )
        self.assertIsNone(_cut_off_reason({"message": {"content": "{}"}}))


class TruncatedResponseRepairTests(unittest.TestCase):
    """The repair keeps what completed and drops the partial value whole."""

    def test_complete_entries_are_kept_and_the_partial_one_dropped(self) -> None:
        repaired, note = _repair_truncated_json(truncated_late())

        assert repaired is not None
        self.assertEqual(repaired["tags"], ["fixture", "synthetic"])
        self.assertEqual(repaired["title"], VALID_PAYLOAD["title"])
        self.assertEqual(
            repaired["description"], VALID_PAYLOAD["description"]
        )
        # Dropped whole, not truncated into the field.
        self.assertNotIn("bbb", json.dumps(repaired))
        assert note is not None
        self.assertIn("dropped", note)

    def test_the_repair_is_always_valid_json(self) -> None:
        text = json.dumps(VALID_PAYLOAD)
        # Every cut point in a real response, not one chosen to be convenient.
        for cut in range(1, len(text)):
            repaired, _ = _repair_truncated_json(text[:cut])
            if repaired is not None:
                json.loads(json.dumps(repaired))
                self.assertIsInstance(repaired, dict)

    def test_balanced_but_wrong_output_is_not_papered_over(self) -> None:
        # Not cut off, so there is nothing to repair and a repair would only
        # hide a different fault.
        self.assertEqual(_repair_truncated_json('{"a":1,"b":2}'), (None, None))
        self.assertEqual(_repair_truncated_json("{not-json"), (None, None))
        self.assertEqual(_repair_truncated_json(""), (None, None))

    def test_a_repair_never_raises_on_hostile_input(self) -> None:
        for hostile in (
            "}",
            "]}",
            '{"a":"\\',
            '{"a":[1,2,',
            '{"a":{"b":[{"c":"',
            '[[[[[',
            '{"a":"\\u00",',
        ):
            with self.subTest(hostile=hostile):
                value, _ = _repair_truncated_json(hostile)
                self.assertTrue(value is None or isinstance(value, dict))


class TruncatedRetryTests(unittest.TestCase):
    """The analyzer's retry after a cut-off, which previously changed nothing."""

    def _asset(self, root: Path) -> dict[str, object]:
        source = root / "fixture_note.txt"
        source.write_text(
            "A bounded synthetic fixture used as text evidence.",
            encoding="utf-8",
        )
        return {
            "source_path": str(source),
            "media_metadata": {},
            "thumbnail_path": "",
        }

    def test_truncated_once_then_valid_completes_the_item(self) -> None:
        """The headline: a retry that recovers, where three never did."""
        responses = [
            cut_off_response(truncated_early()),
            {"message": {"content": json.dumps(VALID_PAYLOAD)}},
        ]
        calls: list[dict[str, object]] = []

        def respond(endpoint, path, payload=None, *, timeout=5):
            calls.append(payload or {})
            return responses[len(calls) - 1]

        with tempfile.TemporaryDirectory() as temp:
            asset = self._asset(Path(temp))
            with patch(
                "beacon.local_analysis._request_json", side_effect=respond
            ):
                result = _default_analyzer("http://127.0.0.1:11434", "m", asset)

        self.assertEqual(result["title"], VALID_PAYLOAD["title"])
        self.assertEqual(result["evidence_mode"], "text_content")
        self.assertEqual(len(calls), 2)

    def test_the_retry_after_a_cut_off_actually_differs(self) -> None:
        responses = [
            cut_off_response(truncated_early()),
            {"message": {"content": json.dumps(VALID_PAYLOAD)}},
        ]
        calls: list[dict[str, object]] = []

        def respond(endpoint, path, payload=None, *, timeout=5):
            calls.append(payload or {})
            return responses[len(calls) - 1]

        with tempfile.TemporaryDirectory() as temp:
            asset = self._asset(Path(temp))
            with patch(
                "beacon.local_analysis._request_json", side_effect=respond
            ):
                _default_analyzer("http://127.0.0.1:11434", "m", asset)

        first, second = calls[0], calls[1]
        self.assertEqual(
            first["options"]["num_predict"], LOCAL_RESPONSE_TOKEN_BUDGET
        )
        self.assertEqual(
            second["options"]["num_predict"], LOCAL_RESPONSE_TOKEN_BUDGET_RETRY
        )
        instruction = second["messages"][0]["content"]
        self.assertIn("cut off", instruction)
        self.assertIn("Answer briefly", instruction)
        # The cut-off text is not replayed: doing so grows the prompt against
        # the same budget and is why the later attempts fared worse.
        self.assertNotIn(
            "dddd", json.dumps(second["messages"], ensure_ascii=False)
        )
        self.assertEqual(
            [m["role"] for m in second["messages"]], ["system", "user"]
        )

    def test_a_repairable_cut_off_costs_no_further_generation(self) -> None:
        calls: list[dict[str, object]] = []

        def respond(endpoint, path, payload=None, *, timeout=5):
            calls.append(payload or {})
            return cut_off_response(truncated_late())

        with tempfile.TemporaryDirectory() as temp:
            asset = self._asset(Path(temp))
            with patch(
                "beacon.local_analysis._request_json", side_effect=respond
            ):
                result = _default_analyzer("http://127.0.0.1:11434", "m", asset)

        self.assertEqual(len(calls), 1, "the repair replaces a generation")
        self.assertEqual(result["tags"], ["fixture", "synthetic"])

    def test_every_repair_is_recorded_not_silent(self) -> None:
        def respond(endpoint, path, payload=None, *, timeout=5):
            return cut_off_response(truncated_late())

        with tempfile.TemporaryDirectory() as temp:
            asset = self._asset(Path(temp))
            with patch(
                "beacon.local_analysis._request_json", side_effect=respond
            ):
                result = _default_analyzer("http://127.0.0.1:11434", "m", asset)

        self.assertIn(ANALYSIS_CORRECTION_KEY, result)
        result.pop("confidence")
        payload, note = _normalize_payload(result)
        assert note is not None
        self.assertIn("cut off", note)
        self.assertIn("generation budget", note)
        # The note is carried in provenance; the reserved key never reaches the
        # saved payload.
        self.assertNotIn(ANALYSIS_CORRECTION_KEY, payload)

    def test_an_unrecoverable_cut_off_names_the_cause(self) -> None:
        calls: list[dict[str, object]] = []

        def respond(endpoint, path, payload=None, *, timeout=5):
            calls.append(payload or {})
            return cut_off_response(truncated_early())

        with tempfile.TemporaryDirectory() as temp:
            asset = self._asset(Path(temp))
            with patch(
                "beacon.local_analysis._request_json", side_effect=respond
            ):
                with self.assertRaises(ValueError) as caught:
                    _default_analyzer("http://127.0.0.1:11434", "m", asset)

        self.assertEqual(len(calls), LOCAL_RESPONSE_ATTEMPTS)
        message = str(caught.exception)
        self.assertIn("cut off at the generation budget", message)
        self.assertIn(f"of {LOCAL_RESPONSE_ATTEMPTS} attempt(s)", message)


class TruncationBatchTests(unittest.TestCase):
    """At the control level: one item's cut-off response never stops the job."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "runtime" / "beacon.db"
        self.sources = self.root / "sources"
        self.sources.mkdir()
        # Distinct content per file: identical bytes are one asset with two
        # locations, which would make this a one-item batch. The text itself is
        # what identifies the item in the request, because the request carries
        # the evidence and not the filename.
        for name, text in (
            ("fixture_one.txt", "The first bounded synthetic fixture."),
            ("fixture_two.txt", "The second bounded synthetic fixture."),
        ):
            source = self.sources / name
            source.write_text(text, encoding="utf-8")
            catalog_file(
                source,
                self.db,
                stability_seconds=0,
                include_media_probe=False,
                include_thumbnail_generation=False,
            )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _item_errors(self) -> list[str]:
        connection = sqlite3.connect(self.db)
        try:
            return [
                row[0] or ""
                for row in connection.execute(
                    "SELECT error FROM local_analysis_items WHERE state='failed'"
                )
            ]
        finally:
            connection.close()

    def test_three_cut_offs_fail_the_item_and_the_batch_continues(self) -> None:
        seen: list[str] = []

        def respond(endpoint, path, payload=None, *, timeout=5):
            body = json.dumps(payload or {}, ensure_ascii=False)
            # One item's responses are always cut off; the other answers
            # normally. The item is identified by its own text evidence.
            if "The first bounded" in body:
                seen.append("cut-off")
                return cut_off_response(truncated_early())
            return {"message": {"content": json.dumps(VALID_PAYLOAD)}}

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        with patch("beacon.local_analysis._request_json", side_effect=respond):
            result = run_local_analysis_job(self.db, job_id)

        self.assertEqual(len(seen), LOCAL_RESPONSE_ATTEMPTS)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.completed, 1)
        self.assertEqual(result.pending, 0)
        self.assertEqual(result.state, "partial")

        [error] = self._item_errors()
        self.assertIn(
            "local model failed content validation after three attempts", error
        )
        self.assertIn("cut off at the generation budget", error)

    def test_a_recovered_cut_off_leaves_the_batch_complete(self) -> None:
        attempts: dict[str, int] = {}

        def respond(endpoint, path, payload=None, *, timeout=5):
            body = json.dumps(payload or {}, ensure_ascii=False)
            key = "one" if "The first bounded" in body else "two"
            attempts[key] = attempts.get(key, 0) + 1
            if key == "one" and attempts[key] == 1:
                return cut_off_response(truncated_early())
            return {"message": {"content": json.dumps(VALID_PAYLOAD)}}

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        with patch("beacon.local_analysis._request_json", side_effect=respond):
            result = run_local_analysis_job(self.db, job_id)

        self.assertEqual(result.failed, 0)
        self.assertEqual(result.completed, 2)
        self.assertEqual(result.state, "complete")
        self.assertEqual(attempts["one"], 2, "one cut-off, then recovered")


if __name__ == "__main__":
    unittest.main()
