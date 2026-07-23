from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from beacon.catalog import catalog_file, sha256_file
from beacon.database import SCHEMA_VERSION, connect, database_integrity
from beacon.managed_moves import move_cataloged_file
from beacon.metadata import (
    apply_analysis_metadata,
    get_asset_metadata,
    get_policy,
    save_asset_metadata,
    set_policy,
)
from beacon.repository import asset_detail, search_assets


class EditableMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "beacon.db"
        self.source = self.root / "inbox" / "context.txt"
        self.source.parent.mkdir()
        self.source.write_text("editable context fixture", encoding="utf-8")
        self.asset = catalog_file(
            self.source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_metadata_is_editable_versioned_and_searchable(self) -> None:
        first = save_asset_metadata(
            self.db,
            self.asset.asset_id,
            {
                "display_title": "First contextual title",
                "description": "Human-provided description.",
                "media_category": "reference",
                "tags": ["alpha", "archive"],
                "people": ["Example Person"],
                "project": "Test Project",
                "organization_path": str(self.root / "library"),
            },
            updated_by="human",
            source="test",
        )
        second = save_asset_metadata(
            self.db,
            self.asset.asset_id,
            {
                **{
                    key: value
                    for key, value in get_asset_metadata(
                        self.db,
                        self.asset.asset_id,
                    ).items()
                    if key not in {"revision", "updated_at", "updated_by"}
                },
                "display_title": "Revised contextual title",
            },
            updated_by="human",
            source="test",
        )

        self.assertEqual(first["revision"], 1)
        self.assertEqual(second["revision"], 2)
        detail = asset_detail(self.db, self.asset.asset_id)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(
            detail["editable_metadata"]["display_title"],
            "Revised contextual title",
        )
        found = search_assets(self.db, query="revised contextual")
        self.assertEqual(found["total"], 1)

        with connect(self.db) as connection:
            revisions = connection.execute(
                """
                SELECT COUNT(*) FROM asset_metadata_revisions
                WHERE asset_id = ?
                """,
                (self.asset.asset_id,),
            ).fetchone()[0]
        self.assertEqual(revisions, 2)
        self.assertEqual(
            database_integrity(self.db)["schema_version"], SCHEMA_VERSION
        )

    def test_policy_values_retain_structured_provenance(self) -> None:
        set_policy(
            self.db,
            "ai.analysis.default_execution",
            {"mode": "local_only"},
            source_kind="beacon_thread",
            source_reference="thread-id",
        )
        self.assertEqual(
            get_policy(self.db, "ai.analysis.default_execution"),
            {"mode": "local_only"},
        )

    def test_analysis_refreshes_ai_fields_but_preserves_human_edits(self) -> None:
        applied = apply_analysis_metadata(
            self.db,
            self.asset.asset_id,
            {
                "title": "AI title",
                "description": "AI description",
                "media_category": "stock footage",
                "tags": ["blue", "calm"],
                "stock_metadata": {"dominant_colors": ["blue"]},
            },
            run_id="first",
        )
        self.assertEqual(applied["display_title"], "AI title")
        save_asset_metadata(
            self.db,
            self.asset.asset_id,
            {
                **{key: applied[key] for key in (
                    "display_title", "description", "media_category", "tags",
                    "people", "event_date", "place", "client", "project",
                    "rights", "notes", "organization_path",
                )},
                "display_title": "Human title",
                "tags": ["keeper"],
            },
            updated_by="human",
            source="test-edit",
        )
        refreshed = apply_analysis_metadata(
            self.db,
            self.asset.asset_id,
            {
                "title": "Replacement AI title",
                "description": "Richer AI description",
                "media_category": "B-roll",
                "tags": ["new-ai-tag"],
            },
            run_id="second",
        )
        self.assertEqual(refreshed["display_title"], "Human title")
        self.assertEqual(refreshed["tags"], ["keeper"])
        self.assertEqual(refreshed["description"], "Richer AI description")


class ManagedMoveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "beacon.db"
        self.inbox = self.root / "inbox"
        self.library = self.root / "library"
        self.inbox.mkdir()
        self.source = self.inbox / "managed.txt"
        self.source.write_text("managed move fixture", encoding="utf-8")
        self.before = sha256_file(self.source)
        self.asset = catalog_file(
            self.source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_move_requires_recorded_policy(self) -> None:
        with self.assertRaisesRegex(PermissionError, "not enabled"):
            move_cataloged_file(
                self.db,
                asset_id=self.asset.asset_id,
                source_path=self.source,
                destination_directory=self.library,
                requested_by="human",
                authorization="test",
                approved_roots=(self.library,),
            )
        self.assertTrue(self.source.exists())

    def test_cataloged_file_move_is_verified_and_audited(self) -> None:
        set_policy(
            self.db,
            "files.managed_moves.enabled",
            True,
            source_kind="test",
        )
        duplicate = self.root / "use-test-copy" / self.source.name
        duplicate.parent.mkdir()
        duplicate.write_bytes(self.source.read_bytes())
        catalog_file(
            duplicate,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
        )
        result = move_cataloged_file(
            self.db,
            asset_id=self.asset.asset_id,
            source_path=self.source,
            destination_directory=self.library / "Personal",
            requested_by="human",
            authorization="test authorization",
            approved_roots=(self.library,),
        )

        destination = Path(result.destination_path)
        self.assertFalse(self.source.exists())
        self.assertTrue(destination.exists())
        self.assertEqual(sha256_file(destination), self.before)
        detail = asset_detail(self.db, self.asset.asset_id)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["primary_path"], str(destination))
        self.assertEqual(len(detail["locations"]), 2)
        self.assertEqual(detail["locations"][0]["path"], str(destination))
        self.assertEqual(detail["moves"][0]["state"], "complete")
        self.assertEqual(detail["moves"][0]["authorization"], "test authorization")

    def test_existing_identical_destination_is_not_merged_or_deleted(self) -> None:
        set_policy(
            self.db,
            "files.managed_moves.enabled",
            True,
            source_kind="test",
        )
        destination = self.library / "Personal" / self.source.name
        destination.parent.mkdir(parents=True)
        destination.write_bytes(self.source.read_bytes())

        with self.assertRaisesRegex(FileExistsError, "identical file"):
            move_cataloged_file(
                self.db,
                asset_id=self.asset.asset_id,
                source_path=self.source,
                destination_directory=destination.parent,
                requested_by="human",
                authorization="test authorization",
                approved_roots=(self.library,),
            )
        self.assertTrue(self.source.exists())
        self.assertTrue(destination.exists())


if __name__ == "__main__":
    unittest.main()
