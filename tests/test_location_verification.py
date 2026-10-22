"""Marking a catalog row missing, without walking a folder being written to.

A catalog row whose file is gone had no way to be marked: there was no
missing state anywhere in the schema or the code, so a stale row looked
identical to a live one.

The guard that matters most here is that verification does not descend by
default. A recursive sweep of a root receiving a transfer would examine files
mid-copy, find them absent, and mark them missing -- recording wrong state
about files that are arriving perfectly well. Marking is also never deleting:
the row is the evidence that the file was once observed, and an absent file
may mean a disconnected volume rather than a deletion.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from beacon.catalog import catalog_file
from beacon.database import connect
from beacon.repository import (
    missing_catalog_locations,
    verify_catalog_locations,
)


class LocationVerificationTests(unittest.TestCase):
    """Marking a row missing, without ever walking a folder being written to."""

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "beacon.db"
        self.inbox = self.root / "Inbox"
        self.inbox.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _catalog(self, relative: str, payload: bytes) -> Path:
        source = self.inbox / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(payload)
        catalog_file(
            source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        return source

    def test_an_absent_file_is_marked_and_never_deleted(self) -> None:
        source = self._catalog("stale_at_the_root.txt", b"gone soon")
        with connect(self.db) as connection:
            before = connection.execute(
                "SELECT COUNT(*) AS n FROM locations"
            ).fetchone()["n"]
        source.unlink()

        counts = verify_catalog_locations(self.db, self.inbox)

        self.assertEqual(counts["checked"], 1)
        self.assertEqual(counts["marked_missing"], 1)
        with connect(self.db) as connection:
            after = connection.execute(
                "SELECT COUNT(*) AS n FROM locations"
            ).fetchone()["n"]
        self.assertEqual(after, before, "a row is marked, never removed")
        marked = missing_catalog_locations(self.db)
        self.assertEqual(len(marked), 1)
        self.assertEqual(Path(marked[0]["path"]).name, "stale_at_the_root.txt")

    def test_a_present_file_is_left_alone(self) -> None:
        self._catalog("still_here.txt", b"present")
        counts = verify_catalog_locations(self.db, self.inbox)
        self.assertEqual(counts["present"], 1)
        self.assertEqual(counts["marked_missing"], 0)
        self.assertEqual(missing_catalog_locations(self.db), [])

    def test_a_mark_is_cleared_when_the_file_comes_back(self) -> None:
        """A disconnected volume is not a deletion."""
        source = self._catalog("comes_back.txt", b"here")
        source.unlink()
        verify_catalog_locations(self.db, self.inbox)
        self.assertEqual(len(missing_catalog_locations(self.db)), 1)

        source.write_bytes(b"here")
        counts = verify_catalog_locations(self.db, self.inbox)

        self.assertEqual(counts["mark_cleared"], 1)
        self.assertEqual(missing_catalog_locations(self.db), [])

    def test_verification_does_not_descend_by_default(self) -> None:
        """The guard that protects a folder receiving a transfer.

        A recursive sweep of a root being written to would examine files
        mid-copy, find them absent, and mark them missing -- writing wrong
        state about files that are arriving perfectly well.
        """
        root_level = self._catalog("stale_at_the_root.txt", b"root")
        arriving = self._catalog("incoming_batch/SAMPLE_0001.mov", b"arriving")
        root_level.unlink()
        arriving.unlink()  # stands in for a file not yet fully copied

        counts = verify_catalog_locations(self.db, self.inbox)

        self.assertEqual(counts["checked"], 1, "only the direct child")
        self.assertEqual(counts["marked_missing"], 1)
        marked = {Path(row["path"]).name for row in missing_catalog_locations(self.db)}
        self.assertEqual(
            marked,
            {"stale_at_the_root.txt"},
            "a file inside a subfolder must not be examined or marked",
        )

    def test_recursive_is_available_when_explicitly_asked_for(self) -> None:
        self._catalog("stale_at_the_root.txt", b"root").unlink()
        self._catalog("subfolder/SAMPLE_0002.mov", b"deep").unlink()
        counts = verify_catalog_locations(self.db, self.inbox, recursive=True)
        self.assertEqual(counts["checked"], 2)
        self.assertEqual(counts["marked_missing"], 2)

    def test_verification_moves_nothing(self) -> None:
        self._catalog("still_here.txt", b"present")
        verify_catalog_locations(self.db, self.inbox)
        with connect(self.db) as connection:
            moves = connection.execute(
                "SELECT COUNT(*) AS n FROM managed_moves"
            ).fetchone()["n"]
        self.assertEqual(moves, 0)


class VerificationIsReachableTests(unittest.TestCase):
    """A mechanism the owner cannot invoke is not a mechanism.

    This was built with its tests passing and left unwired, so the action it
    exists for could not be performed. The test asserts the whole path: the
    controller exposes it as a slot, and the window carries a control bound to
    that slot.
    """

    def test_the_controller_exposes_verification_as_a_slot(self) -> None:
        """Invokable from QML, which means registered on the meta-object.

        Checked through QMetaObject rather than by inspecting the attribute:
        a plain method is callable from Python and invisible to QML, so
        callability proves nothing about reachability.
        """
        from beacon.desktop_controller import DesktopController

        meta = DesktopController.staticMetaObject
        names = {
            bytes(meta.method(index).name()).decode()
            for index in range(meta.methodCount())
        }
        self.assertIn(
            "verifyInboxRoot",
            names,
            "verification must be registered as a slot, or QML cannot call it",
        )

    def test_the_window_carries_a_control_bound_to_it(self) -> None:
        qml = (
            Path(__file__).resolve().parents[1]
            / "beacon" / "qml" / "Main.qml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "verifyInboxRootButton",
            qml,
            "the System surface must carry a verification control",
        )
        self.assertTrue(
            "backend.verifyInboxRoot(" in qml,
            "the control must be bound to the controller slot",
        )


class VerificationReachesSubfoldersTests(unittest.TestCase):
    """The control must be able to reach a stale row at any depth.

    The function could always recurse; the control could not ask it to, and
    passed False unconditionally. So a stale row one directory down was
    unreachable from the application however many times it was clicked, and
    the Inbox row count -- which AGENTS.md section 6 now makes load-bearing,
    since the Inbox means "not yet looked at" -- stayed wrong.

    Tested through the controller rather than the function, because the
    function was never the broken part.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtCore import QCoreApplication

        cls.qt_app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        from beacon.desktop_controller import DesktopController, DesktopSettings

        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "runtime" / "beacon.db"
        self.inbox = self.root / "Inbox"
        self.inbox.mkdir()
        self.at_root = self._stale("stale_at_the_root.txt")
        self.in_subfolder = self._stale(
            "fixture_client_a/project_alpha/SAMPLE_0001.txt"
        )
        self.controller = DesktopController(
            DesktopSettings(self.db, self.root / "runtime" / "backups")
        )
        self._patch = patch(
            "beacon.desktop_controller.inbox_root", lambda: self.inbox
        )
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self.controller.shutdown()
        self.controller.deleteLater()
        self.temp.cleanup()

    def _stale(self, relative: str) -> Path:
        source = self.inbox / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(relative.encode())
        catalog_file(
            source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        source.unlink()
        return source

    def _marked(self) -> set[str]:
        return {
            Path(row["path"]).name
            for row in missing_catalog_locations(self.db)
        }

    def test_the_root_only_pass_leaves_a_subfolder_row_alone(self) -> None:
        """The default stays non-recursive; that is the safe one."""
        self.controller.verifyInboxRoot(False)
        self.assertEqual(self._marked(), {"stale_at_the_root.txt"})

    def test_asking_it_to_recurse_reaches_the_subfolder_row(self) -> None:
        """The defect: this row could not be reached from the application."""
        self.controller.verifyInboxRoot(True)
        self.assertEqual(
            self._marked(),
            {"stale_at_the_root.txt", "SAMPLE_0001.txt"},
            "a stale row below the root must be reachable from the control",
        )

    def test_recursing_still_deletes_no_row(self) -> None:
        with connect(self.db) as connection:
            before = connection.execute(
                "SELECT COUNT(*) AS n FROM locations"
            ).fetchone()["n"]
        self.controller.verifyInboxRoot(True)
        with connect(self.db) as connection:
            after = connection.execute(
                "SELECT COUNT(*) AS n FROM locations"
            ).fetchone()["n"]
        self.assertEqual(after, before, "marking is never deleting")

    def test_the_control_offers_the_choice_rather_than_deciding_it(self) -> None:
        """Off by default, and the window must carry the switch."""
        qml = (
            Path(__file__).resolve().parents[1]
            / "beacon" / "qml" / "Main.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("verifyRecursivelyCheck", qml)
        self.assertIn(
            "backend.verifyInboxRoot(",
            qml,
            "the control must pass the operator's choice through",
        )
        self.assertIn(
            "checked: false",
            qml,
            "descending must be opt-in, not the default",
        )


if __name__ == "__main__":
    unittest.main()
