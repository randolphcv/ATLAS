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


if __name__ == "__main__":
    unittest.main()
