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
from beacon.desktop import DEFAULT_RUNTIME, _catalog_label
from beacon.desktop_controller import DesktopController, DesktopSettings
from beacon.desk import seed_threads
from beacon.text_preview import read_text_preview


class TextPreviewTests(unittest.TestCase):
    def test_common_text_encodings_are_read_as_plain_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            utf16 = root / "notes.md"
            utf16.write_text("Beacon reads UTF-16 ✦", encoding="utf-16")
            windows = root / "legacy.txt"
            windows.write_bytes(b"caf\xe9 archive")

            utf16_preview = read_text_preview(utf16)
            windows_preview = read_text_preview(windows)

            self.assertIsNotNone(utf16_preview)
            self.assertEqual(utf16_preview.text, "Beacon reads UTF-16 ✦")
            self.assertEqual(utf16_preview.encoding, "UTF-16 LE")
            self.assertIsNotNone(windows_preview)
            self.assertEqual(windows_preview.text, "café archive")
            self.assertEqual(windows_preview.encoding, "Windows-1252")

    def test_utf8_text_without_an_extension_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "field-notes"
            source.write_text("plain text with no suffix", encoding="utf-8")

            preview = read_text_preview(source)

            self.assertIsNotNone(preview)
            self.assertEqual(preview.text, "plain text with no suffix")
            self.assertEqual(preview.encoding, "UTF-8")

    def test_text_preview_is_bounded_without_splitting_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "large.log"
            source.write_text("A" * 15 + "✦" + "tail", encoding="utf-8")

            preview = read_text_preview(source, max_bytes=17)

            self.assertIsNotNone(preview)
            self.assertEqual(preview.text, "A" * 15)
            self.assertTrue(preview.truncated)

    def test_binary_content_is_not_treated_as_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "payload.bin"
            source.write_bytes(bytes(range(32)) * 32)

            self.assertIsNone(read_text_preview(source))


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
        self.assertEqual(row["thumbnailUrl"], "")
        self.assertEqual(
            self.controller.selectedAsset["atlas_uri"],
            f"atlas://asset/{self.cataloged.asset_id}",
        )
        self.assertEqual(self.controller.selectedAsset["previewKind"], "text")
        self.assertTrue(self.controller.selectedAsset["previewAvailable"])
        self.assertEqual(
            self.controller.selectedAsset["textPreview"],
            "synthetic native desktop signal",
        )
        self.assertIn("UTF-8", self.controller.selectedAsset["textPreviewLabel"])
        self.assertEqual(self.controller.selectedAsset["extensionLabel"], "TXT")
        self.assertTrue(
            self.controller.selectedAsset["previewUrl"].startswith("file:")
        )
        self.assertEqual(self.controller.summary["assets"], 1)
        self.assertEqual(self.controller.databaseHealth["state"], "healthy")
        self.assertEqual(self.controller.catalogLabel, "Custom catalog")

        self.controller.setSearchQuery("does-not-exist")
        self.assertEqual(self.controller.assets.rowCount(), 0)
        self.assertEqual(self.controller.selectedAsset, {})

        self.controller.setSearchQuery("native")
        self.assertEqual(self.controller.assets.rowCount(), 1)

    def test_catalog_context_is_explicit(self) -> None:
        self.assertEqual(
            _catalog_label(DEFAULT_RUNTIME / "beacon.db"),
            "Live catalog",
        )
        self.assertEqual(
            _catalog_label(
                self.root / "use-tests" / "UseTest-01" / "beacon.db"
            ),
            "Isolated use test",
        )

    def test_beacon_desk_models_create_reply_and_resolve_threads(self) -> None:
        [thread_id] = seed_threads(
            self.db,
            (
                {
                    "seed_key": "desktop:test-question",
                    "subject": "Choose the local boundary",
                    "kind": "approval",
                    "priority": "important",
                    "requires_approval": True,
                    "body": "Should analysis remain local?",
                },
            ),
        )
        self.controller.refresh()

        self.assertEqual(self.controller.beaconThreads.rowCount(), 1)
        self.assertEqual(
            self.controller.selectedBeaconThread["id"],
            thread_id,
        )
        self.assertEqual(self.controller.beaconMessages.rowCount(), 1)
        self.assertEqual(
            self.controller.beaconDeskSummary["awaiting_human"],
            1,
        )

        self.controller.replyToBeaconThread("Yes. Keep it local.")
        self.assertEqual(
            self.controller.selectedBeaconThread["state"],
            "queued_for_beacon",
        )
        self.assertEqual(self.controller.beaconMessages.rowCount(), 2)
        self.assertIn("No file action", self.controller.statusMessage)

        self.controller.createBeaconThread(
            "Review a naming rule",
            "Ask me which abbreviations matter.",
        )
        self.assertEqual(self.controller.beaconThreads.rowCount(), 2)
        self.assertEqual(
            self.controller.selectedBeaconThread["subject"],
            "Review a naming rule",
        )

        self.controller.resolveBeaconThread()
        self.assertEqual(self.controller.beaconThreads.rowCount(), 1)

    def test_external_catalog_changes_refresh_automatically(self) -> None:
        second = self.source.parent / "second-signal.txt"
        second.write_bytes(b"second synthetic native desktop signal")
        catalog_file(
            second,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
        )
        self.assertEqual(self.controller.assets.rowCount(), 1)
        self.controller.refreshIfChanged()
        self.assertEqual(self.controller.assets.rowCount(), 2)

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

    def test_space_opens_preview_even_when_a_button_has_focus(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "focused-button.txt"
            source.write_text("Space belongs to preview.", encoding="utf-8")
            catalog_file(
                source,
                root / "beacon.db",
                stability_seconds=0,
                include_media_probe=False,
            )
            environment = os.environ.copy()
            environment["QT_QPA_PLATFORM"] = "offscreen"
            environment["QT_QUICK_BACKEND"] = "software"
            script = r"""
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QMetaObject, QTimer, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from beacon.desktop_controller import DesktopController, DesktopSettings

QQuickStyle.setStyle("Fusion")
app = QApplication(["beacon-hotkey-test"])
controller = DesktopController(
    DesktopSettings(Path(sys.argv[1]), Path(sys.argv[2]))
)
controller.setCurrentView("library")
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("backend", controller)
engine.rootContext().setContextProperty("previewMuted", True)
qml = Path.cwd() / "beacon" / "qml" / "Main.qml"
engine.load(QUrl.fromLocalFile(str(qml)))
if not engine.rootObjects():
    raise SystemExit(10)
window = engine.rootObjects()[0]
button = window.findChild(QObject, "detailPreviewButton")
if button is None:
    raise SystemExit(11)

def press_with_button_focused():
    QMetaObject.invokeMethod(button, "forceActiveFocus")
    if not button.property("activeFocus"):
        app.exit(12)
        return
    QTest.keyClick(window, Qt.Key.Key_Space)
    QTimer.singleShot(150, verify_open)

def verify_open():
    if not window.property("previewOpen"):
        app.exit(13)
        return
    QTest.keyClick(window, Qt.Key.Key_Space)
    QTimer.singleShot(150, verify_closed)

def verify_closed():
    app.exit(14 if window.property("previewOpen") else 0)

QTimer.singleShot(250, press_with_button_focused)
raise SystemExit(app.exec())
"""
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(root / "beacon.db"),
                    str(root / "backups"),
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

    def test_space_types_in_beacon_reply_without_opening_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "desk-hotkey.txt"
            source.write_text("Space should stay in the reply.", encoding="utf-8")
            catalog_file(
                source,
                root / "beacon.db",
                stability_seconds=0,
                include_media_probe=False,
            )
            environment = os.environ.copy()
            environment["QT_QPA_PLATFORM"] = "offscreen"
            environment["QT_QUICK_BACKEND"] = "software"
            script = r"""
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QMetaObject, QTimer, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from beacon.desk import seed_threads
from beacon.desktop_controller import DesktopController, DesktopSettings

db = Path(sys.argv[1])
seed_threads(
    db,
    ({
        "seed_key": "desktop:reply-hotkey",
        "subject": "Reply without opening preview",
        "kind": "question",
        "priority": "normal",
        "body": "Type a reply here.",
    },),
)
QQuickStyle.setStyle("Fusion")
app = QApplication(["beacon-reply-hotkey-test"])
controller = DesktopController(DesktopSettings(db, Path(sys.argv[2])))
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("backend", controller)
engine.rootContext().setContextProperty("previewMuted", True)
qml = Path.cwd() / "beacon" / "qml" / "Main.qml"
engine.load(QUrl.fromLocalFile(str(qml)))
if not engine.rootObjects():
    raise SystemExit(20)
window = engine.rootObjects()[0]
reply = window.findChild(QObject, "beaconReplyField")
if reply is None:
    raise SystemExit(21)

def press_space_in_reply():
    QMetaObject.invokeMethod(reply, "forceActiveFocus")
    if not reply.property("activeFocus"):
        app.exit(22)
        return
    QTest.keyClick(window, Qt.Key.Key_Space)
    QTimer.singleShot(150, verify)

def verify():
    if window.property("previewOpen"):
        app.exit(23)
        return
    app.exit(0 if reply.property("text") == " " else 24)

QTimer.singleShot(250, press_space_in_reply)
raise SystemExit(app.exec())
"""
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(root / "beacon.db"),
                    str(root / "backups"),
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
