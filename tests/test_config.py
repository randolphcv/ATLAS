from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from beacon import config


class CatalogDiscoveryTests(unittest.TestCase):
    """AGENTS.md section 5: the catalog's home is the archive volume."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True)
        self.archive = self.root / "archive"
        self.archive.mkdir(parents=True)
        self._env = patch.dict(
            os.environ,
            {"BEACON_RUNTIME_ROOT": str(self.runtime)},
            clear=False,
        )
        self._env.start()
        for name in ("BEACON_DB", "BEACON_ARCHIVE_ROOT", "BEACON_BACKUP_DIR"):
            os.environ.pop(name, None)
        config._warned.clear()

    def tearDown(self) -> None:
        self._env.stop()
        self.temp.cleanup()

    def _write_settings(self, payload: dict[str, str]) -> None:
        (self.runtime / config.SETTINGS_FILENAME).write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_explicit_environment_setting_wins(self) -> None:
        explicit = self.root / "elsewhere" / "catalog.db"
        self._write_settings({"BEACON_ARCHIVE_ROOT": str(self.archive)})
        with patch.dict(os.environ, {"BEACON_DB": str(explicit)}):
            self.assertEqual(config.resolve_catalog_path(), explicit)

    def test_settings_file_setting_beats_the_archive_default(self) -> None:
        explicit = self.root / "elsewhere" / "catalog.db"
        self._write_settings(
            {
                "BEACON_ARCHIVE_ROOT": str(self.archive),
                "BEACON_DB": str(explicit),
            }
        )
        self.assertEqual(config.resolve_catalog_path(), explicit)

    def test_archive_root_resolves_beneath_system_beacon(self) -> None:
        self._write_settings({"BEACON_ARCHIVE_ROOT": str(self.archive)})
        self.assertEqual(
            config.resolve_catalog_path(),
            self.archive / "System" / "Beacon" / "beacon.db",
        )
        self.assertEqual(
            config.backups_dir(),
            self.archive / "System" / "Beacon" / "backups",
        )

    def test_unconfigured_resolves_to_nothing_rather_than_a_local_path(
        self,
    ) -> None:
        """The defect this closes: never silently fall back and look healthy."""
        self.assertIsNone(config.resolve_catalog_path())
        with self.assertRaises(config.CatalogNotConfiguredError):
            config.catalog_path()
        with self.assertRaises(config.CatalogNotConfiguredError):
            config.backups_dir()

    def test_advice_names_the_setting_and_the_expected_location(self) -> None:
        advice = config.catalog_advice()
        self.assertIn(config.ARCHIVE_ROOT_SETTING, advice)
        self.assertIn(str(config.settings_path()), advice)
        self.assertIn("System", advice)
        self.assertIn("beacon.db", advice)

    def test_status_reports_configured_and_exists_separately(self) -> None:
        self._write_settings({"BEACON_ARCHIVE_ROOT": str(self.archive)})
        status = config.catalog_status()
        self.assertTrue(status["configured"])
        self.assertFalse(status["exists"])
        target = Path(str(status["path"]))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")
        self.assertTrue(config.catalog_status()["exists"])

    def test_malformed_settings_file_is_reported_not_swallowed(self) -> None:
        """A typo must not look identical to an unconfigured deployment."""
        (self.runtime / config.SETTINGS_FILENAME).write_text(
            '{"BEACON_ARCHIVE_ROOT": "not closed', encoding="utf-8"
        )
        with self.assertLogs("beacon.config", level="WARNING") as captured:
            self.assertEqual(config.load_settings(), {})
        self.assertIn("could not be read", "".join(captured.output))

    def test_settings_file_must_be_an_object(self) -> None:
        (self.runtime / config.SETTINGS_FILENAME).write_text(
            '["not", "an", "object"]', encoding="utf-8"
        )
        with self.assertLogs("beacon.config", level="WARNING") as captured:
            self.assertEqual(config.load_settings(), {})
        self.assertIn("JSON object", "".join(captured.output))

    def test_absent_settings_file_is_silent(self) -> None:
        with self.assertNoLogs("beacon.config", level="WARNING"):
            self.assertEqual(config.load_settings(), {})

    def test_bulk_derivatives_stay_outside_system(self) -> None:
        """System holds system state; the derivative trees hold content."""
        self._write_settings({"BEACON_ARCHIVE_ROOT": str(self.archive)})
        beacon_dir = self.archive / "Beacon"
        self.assertEqual(config.thumbnails_dir(), beacon_dir / "Thumbnails")
        self.assertEqual(config.previews_dir(), beacon_dir / "Proxies")
        self.assertEqual(config.transcripts_dir(), beacon_dir / "Transcripts")


if __name__ == "__main__":
    unittest.main()
