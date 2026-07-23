from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from beacon.catalog import catalog_file
from beacon.desktop_controller import DesktopController, DesktopSettings


class DesktopControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "runtime" / "beacon.db"
        self.backups = self.root / "runtime" / "backups"
        self.source = self.root / "fixtures" / "native-signal.txt"
        self.source.parent.mkdir()
        self.source.write_bytes(b"synthetic native desktop signal")
        self.cataloged = catalog_file(
            self.source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
        )
        self.controller = DesktopController(
            DesktopSettings(self.db, self.backups)
        )

    def tearDown(self) -> None:
        self.controller.deleteLater()
        self.temp.cleanup()

    def test_native_models_expose_catalog_and_detail(self) -> None:
        self.assertEqual(self.controller.assets.rowCount(), 1)
        row = self.controller.assets.get(0)
        self.assertEqual(row["filename"], "native-signal.txt")
        self.assertEqual(row["assetId"], self.cataloged.asset_id)
        self.assertEqual(
            self.controller.selectedAsset["atlas_uri"],
            f"atlas://asset/{self.cataloged.asset_id}",
        )
        self.assertEqual(self.controller.summary["assets"], 1)
        self.assertEqual(self.controller.databaseHealth["state"], "healthy")

        self.controller.setSearchQuery("does-not-exist")
        self.assertEqual(self.controller.assets.rowCount(), 0)
        self.assertEqual(self.controller.selectedAsset, {})

        self.controller.setSearchQuery("native")
        self.assertEqual(self.controller.assets.rowCount(), 1)

    def test_verified_backup_runs_without_blocking_the_controller(self) -> None:
        loop = QEventLoop()
        timed_out = False

        def stop_when_finished() -> None:
            if not self.controller.busy:
                loop.quit()

        def timeout() -> None:
            nonlocal timed_out
            timed_out = True
            loop.quit()

        self.controller.busyChanged.connect(stop_when_finished)
        QTimer.singleShot(10000, timeout)
        self.controller.createBackup()
        self.assertTrue(self.controller.busy)
        loop.exec()

        self.assertFalse(timed_out)
        self.assertFalse(self.controller.busy)
        self.assertEqual(self.controller.statusKind, "success")
        self.assertEqual(self.controller.backups.rowCount(), 1)


class NativeQmlSmokeTests(unittest.TestCase):
    def test_qml_window_loads_offscreen(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            environment = os.environ.copy()
            environment["QT_QPA_PLATFORM"] = "offscreen"
            environment["QT_QUICK_BACKEND"] = "software"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "beacon.desktop",
                    "--db",
                    str(root / "beacon.db"),
                    "--backup-dir",
                    str(root / "backups"),
                    "--log-file",
                    str(root / "desktop.log"),
                    "--smoke-test",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
