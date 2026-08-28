"""AGENTS.md section 10: model output must never crash a job.

A local model is an untrusted input source. Over-long strings, wrong types,
missing keys and malformed JSON are normal output. The invariant under test is
not any particular limit: it is that no malformed field escapes as an exception
to the job, and that a usable result survives wherever one can.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from beacon.catalog import catalog_file
from beacon.local_analysis import (
    PAYLOAD_TAG_ENTRY_LIMIT,
    PAYLOAD_TEXT_LIMITS,
    _canonical_json,
    _default_analyzer,
    _degrade_payload,
    _normalize_payload,
    _payload_limit_violations,
    _undecodable_reason,
)
from beacon.metadata import (
    LIST_ENTRY_LIMIT,
    TEXT_LIMITS,
    apply_analysis_metadata,
    get_asset_metadata,
    normalize_metadata,
    normalize_metadata_degraded,
)
from beacon.repository import recent_events


def pathological_cases() -> dict[str, dict[str, object]]:
    """One entry per way a local model is known to misbehave."""
    over_text = "x" * (TEXT_LIMITS["display_title"] + 150)
    over_entry = "y" * (LIST_ENTRY_LIMIT + 100)
    return {
        "over_long_tags_entry": {"tags": ["keep", over_entry, "also-keep"]},
        "over_long_title": {"display_title": over_text},
        "over_long_suggestion": {
            "organization_path": "z" * (TEXT_LIMITS["organization_path"] + 500)
        },
        "tags_is_a_string": {"tags": "one\ntwo\nthree"},
        "tags_is_an_integer": {"tags": 12345},
        "missing_required_key": {},
        "null_where_object_expected": {"display_title": None, "tags": None},
        "wrong_type_for_text_field": {"notes": {"unexpected": "object"}},
        "unknown_field": {"not_a_field": "value"},
        "very_large_payload": {
            "description": "w" * (TEXT_LIMITS["description"] * 3),
            "tags": [f"tag-{n}" for n in range(5_000)],
        },
    }


class DegradedNormalizationTests(unittest.TestCase):
    """Nothing raises, and every correction is reported."""

    def test_no_pathological_input_raises(self) -> None:
        for name, payload in pathological_cases().items():
            with self.subTest(case=name):
                try:
                    metadata, corrections = normalize_metadata_degraded(payload)
                except Exception as error:
                    self.fail(f"{name} raised {type(error).__name__}: {error}")
                self.assertIsInstance(metadata, dict)
                self.assertIsInstance(corrections, list)
                for correction in corrections:
                    self.assertEqual(
                        {"field", "action", "detail"}, set(correction)
                    )

    def test_result_is_always_persistable_after_degrading(self) -> None:
        """Degraded output must satisfy the strict validator."""
        for name, payload in pathological_cases().items():
            with self.subTest(case=name):
                metadata, _ = normalize_metadata_degraded(payload)
                normalize_metadata(metadata)

    def test_over_long_tag_is_dropped_and_siblings_survive(self) -> None:
        metadata, corrections = normalize_metadata_degraded(
            {"tags": ["keep", "y" * (LIST_ENTRY_LIMIT + 100), "also-keep"]}
        )
        self.assertEqual(metadata["tags"], ["keep", "also-keep"])
        self.assertTrue(
            any(c["action"] == "dropped_entries" for c in corrections)
        )

    def test_over_long_prose_is_truncated_not_discarded(self) -> None:
        limit = TEXT_LIMITS["display_title"]
        metadata, corrections = normalize_metadata_degraded(
            {"display_title": "x" * (limit + 150)}
        )
        self.assertEqual(len(metadata["display_title"]), limit)
        self.assertTrue(any(c["action"] == "truncated" for c in corrections))

    def test_strict_path_still_rejects_for_human_edits(self) -> None:
        """A person typing an invalid value must still be told."""
        with self.assertRaises(ValueError):
            normalize_metadata(
                {"display_title": "x" * (TEXT_LIMITS["display_title"] + 1)}
            )
        with self.assertRaises(ValueError):
            normalize_metadata({"tags": ["y" * (LIST_ENTRY_LIMIT + 1)]})


class PayloadRetryAndDegradeTests(unittest.TestCase):
    def test_limit_breach_is_detected_so_it_can_be_retried(self) -> None:
        payload = {
            "title": "x" * (PAYLOAD_TEXT_LIMITS["title"] + 1),
            "tags": ["t" * (PAYLOAD_TAG_ENTRY_LIMIT + 1)],
        }
        self.assertTrue(_payload_limit_violations(payload))

    def test_degrade_makes_an_over_limit_payload_publishable(self) -> None:
        payload = {
            "title": "x" * (PAYLOAD_TEXT_LIMITS["title"] + 400),
            "description": "d",
            "media_category": "c",
            "organization_suggestion": "o"
            * (PAYLOAD_TEXT_LIMITS["organization_suggestion"] + 900),
            "tags": ["keep", "t" * (PAYLOAD_TAG_ENTRY_LIMIT + 50)],
        }
        degraded, notes = _degrade_payload(payload)
        self.assertEqual(_payload_limit_violations(degraded), [])
        self.assertEqual(degraded["tags"], ["keep"])
        self.assertTrue(notes)

    def test_non_dict_payload_reports_rather_than_raising(self) -> None:
        self.assertTrue(_payload_limit_violations("not a payload"))
        self.assertTrue(_payload_limit_violations(None))


class AnalysisMetadataRecordsCorrectionsTests(unittest.TestCase):
    """A correction is audit history, so it must reach the event ledger."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "catalog.db"
        source = self.root / "SAMPLE_0001.txt"
        source.write_text("fixture", encoding="utf-8")
        self.asset = catalog_file(
            source, self.db, stability_seconds=0, include_media_probe=False
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_over_long_model_output_is_saved_degraded_and_recorded(self) -> None:
        limit = TEXT_LIMITS["display_title"]
        result = apply_analysis_metadata(
            self.db,
            self.asset.asset_id,
            {
                "title": "x" * (limit + 200),
                "description": "A usable description survived.",
                "media_category": "video",
                "tags": ["keep", "y" * (LIST_ENTRY_LIMIT + 10)],
            },
            run_id="00000000-0000-0000-0000-000000000001",
        )
        self.assertEqual(len(result["display_title"]), limit)
        self.assertEqual(result["tags"], ["keep"])
        self.assertTrue(result["corrections"])

        stored = get_asset_metadata(self.db, self.asset.asset_id)
        self.assertEqual(stored["description"], "A usable description survived.")

        corrections = [
            event
            for event in recent_events(self.db, 50)
            if event["kind"] == "metadata_correction"
        ]
        self.assertTrue(corrections, "the correction was not audited")

    def test_every_pathological_payload_still_yields_a_saved_result(self) -> None:
        for index, (name, payload) in enumerate(pathological_cases().items()):
            with self.subTest(case=name):
                try:
                    apply_analysis_metadata(
                        self.db,
                        self.asset.asset_id,
                        payload,
                        run_id=f"00000000-0000-0000-0000-{index:012d}",
                    )
                except Exception as error:
                    self.fail(f"{name} raised {type(error).__name__}: {error}")


class UndecodableDiagnosisTests(unittest.TestCase):
    """The error must name the cause, not repeat the symptom."""

    def test_unsupported_extension_is_named_as_such(self) -> None:
        reason = _undecodable_reason(Path("fixture.unknownext"), {})
        self.assertIn("not a supported media type", reason)

    def test_probe_error_is_surfaced(self) -> None:
        reason = _undecodable_reason(Path("fixture.mov"), {"error": "bad header"})
        self.assertIn("bad header", reason)

    def test_stream_kinds_are_named_when_nothing_is_decodable(self) -> None:
        reason = _undecodable_reason(
            Path("fixture.mxf"), {"streams": [{"codec_type": "data"}]}
        )
        self.assertIn("data", reason)

    def test_each_branch_gives_a_distinct_diagnosis(self) -> None:
        reasons = {
            _undecodable_reason(Path("a.unknownext"), {}),
            _undecodable_reason(Path("a.mov"), {}),
            _undecodable_reason(Path("a.mov"), {"error": "x"}),
            _undecodable_reason(Path("a.mov"), {"streams": []}),
            _undecodable_reason(
                Path("a.mov"), {"streams": [{"codec_type": "data"}]}
            ),
        }
        self.assertEqual(len(reasons), 5)


if __name__ == "__main__":
    unittest.main()


class AnalyzerRetryGateTests(unittest.TestCase):
    """The gate inside the analysis retry loop, not the one at metadata save.

    Both gates must degrade. The metadata gate already did; this one discarded
    the whole analysis after three full generations, which is how 14 items in
    the monitored run were lost to nothing worse than a long title.
    """

    def _asset(self, root: Path) -> dict[str, object]:
        source = root / "note.txt"
        source.write_text(
            "A synthetic note used as text evidence for the analyzer.",
            encoding="utf-8",
        )
        return {"source_path": str(source), "media_metadata": {}}

    def _always_over_long(self, calls: list[dict[str, object]]):
        def respond(endpoint, path, payload=None, *, timeout=5):
            calls.append(payload or {})
            mode = "text_content"
            body = _canonical_json(payload or {})
            match = re.search(r'"required_evidence_mode":\s*"([a-z_]+)"', body)
            if match:
                mode = match.group(1)
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "title": "T" * (PAYLOAD_TEXT_LIMITS["title"] + 200),
                            "description": "A grounded description.",
                            "content_observations": ["plain text is present"],
                            "evidence_mode": mode,
                            "media_category": "document",
                            "tags": ["text", "note"],
                            "privacy_flags": [],
                            "organization_suggestion": "Keep with documents.",
                            "confidence": 0.5,
                            "stock_metadata": {},
                        }
                    )
                }
            }

        return respond

    def test_over_long_field_is_kept_and_degraded_not_discarded(self) -> None:
        calls: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as temp:
            asset = self._asset(Path(temp))
            with patch(
                "beacon.local_analysis._request_json",
                side_effect=self._always_over_long(calls),
            ):
                result = _default_analyzer("http://localhost:11434", "m", asset)

        self.assertIsInstance(result, dict)
        payload, note = _normalize_payload(result)
        self.assertEqual(
            len(payload["title"]), PAYLOAD_TEXT_LIMITS["title"]
        )
        self.assertIsNotNone(note)
        self.assertIn("title", str(note))

    def test_a_violation_no_longer_costs_three_generations(self) -> None:
        calls: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as temp:
            asset = self._asset(Path(temp))
            with patch(
                "beacon.local_analysis._request_json",
                side_effect=self._always_over_long(calls),
            ):
                _default_analyzer("http://localhost:11434", "m", asset)

        self.assertEqual(len(calls), 2, "one corrective retry, then degrade")

    def test_request_schema_tells_the_model_the_limits(self) -> None:
        calls: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as temp:
            asset = self._asset(Path(temp))
            with patch(
                "beacon.local_analysis._request_json",
                side_effect=self._always_over_long(calls),
            ):
                _default_analyzer("http://localhost:11434", "m", asset)

        properties = calls[0]["format"]["properties"]
        self.assertEqual(
            properties["title"]["maxLength"], PAYLOAD_TEXT_LIMITS["title"]
        )
        self.assertEqual(
            properties["tags"]["items"]["maxLength"], PAYLOAD_TAG_ENTRY_LIMIT
        )
