from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from beacon.analysis import import_analysis_manifest
from beacon.catalog import catalog_file
from beacon.database import SCHEMA_VERSION, database_integrity
from beacon.repository import asset_detail, search_assets


class AnalysisResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "inbox" / "quiet-note.txt"
        self.source.parent.mkdir()
        self.source.write_text(
            "A synthetic note for the quiet archive.",
            encoding="utf-8",
        )
        self.before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.db = self.root / "runtime" / "beacon.db"
        self.asset = catalog_file(
            self.source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _manifest(self) -> dict[str, object]:
        return {
            "analyzer": "Beacon candidate librarian",
            "analyzer_version": "pilot-1",
            "policy_version": "beacon-context-v1",
            "execution_location": "Codex subagent",
            "external_inference": True,
            "authorization": (
                "Fixture-only external inference explicitly approved for test."
            ),
            "scope": {
                "asset_ids": [self.asset.asset_id],
                "excluded_paths": ["J:\\Inbox"],
            },
            "results": [
                {
                    "asset_id": self.asset.asset_id,
                    "source_sha256": self.asset.sha256,
                    "analysis_kind": "contextual_metadata",
                    "confidence": 0.91,
                    "payload": {
                        "title": "Quiet Archive Note",
                        "description": (
                            "A short synthetic note describing a quiet archive."
                        ),
                        "media_category": "text note",
                        "tags": ["synthetic", "archive", "quiet"],
                        "privacy_flags": [],
                        "organization_suggestion": (
                            "Keep with synthetic acceptance fixtures."
                        ),
                        "field_confidence": {
                            "title": 0.85,
                            "description": 0.95,
                        },
                    },
                    "provenance": {
                        "inputs": [
                            {
                                "kind": "source_text",
                                "sha256": self.asset.sha256,
                            }
                        ],
                        "verified_facts": ["UTF-8 plain text"],
                        "inferences": ["A concise archive-related note"],
                    },
                }
            ],
        }

    def test_candidate_import_is_audited_searchable_and_idempotent(self) -> None:
        first = import_analysis_manifest(self.db, self._manifest())
        second = import_analysis_manifest(self.db, self._manifest())

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.result_ids, second.result_ids)
        self.assertEqual(
            hashlib.sha256(self.source.read_bytes()).hexdigest(),
            self.before,
        )
        self.assertEqual(
            database_integrity(self.db)["schema_version"], SCHEMA_VERSION
        )

        detail = asset_detail(self.db, self.asset.asset_id)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(len(detail["analysis"]), 1)
        analysis = detail["analysis"][0]
        self.assertEqual(analysis["review_state"], "candidate")
        self.assertEqual(analysis["payload"]["title"], "Quiet Archive Note")
        self.assertTrue(analysis["external_inference"])
        self.assertEqual(analysis["confidence"], 0.91)

        found = search_assets(self.db, query="quiet archive")
        self.assertEqual(found["total"], 1)
        self.assertEqual(found["items"][0]["id"], self.asset.asset_id)

        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM analysis_runs"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM analysis_results"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM system_events
                    WHERE kind IN ('analysis', 'analysis_run')
                    """
                ).fetchone()[0],
                2,
            )
        finally:
            connection.close()

    def test_checksum_mismatch_rejects_the_complete_manifest(self) -> None:
        manifest = self._manifest()
        manifest["results"][0]["source_sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            import_analysis_manifest(self.db, manifest)

        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM analysis_runs"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM analysis_results"
                ).fetchone()[0],
                0,
            )
        finally:
            connection.close()

    def test_external_inference_requires_an_authorization_note(self) -> None:
        manifest = self._manifest()
        del manifest["authorization"]

        with self.assertRaisesRegex(ValueError, "explicit authorization"):
            import_analysis_manifest(self.db, manifest)


if __name__ == "__main__":
    unittest.main()
