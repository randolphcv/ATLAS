from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from beacon.catalog import catalog_file, scan_directory
from beacon.stability import wait_until_stable


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inbox = self.root / "inbox"
        self.inbox.mkdir()
        self.db = self.root / "runtime" / "beacon.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, name: str, content: bytes) -> Path:
        path = self.inbox / name
        path.write_bytes(content)
        return path

    def test_catalog_is_read_only_and_restart_idempotent(self) -> None:
        source = self._write("synthetic.txt", b"ATLAS synthetic fixture\n")
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        first = catalog_file(source, self.db, 0, include_media_probe=False)
        second = catalog_file(source, self.db, 0, include_media_probe=False)
        after = hashlib.sha256(source.read_bytes()).hexdigest()

        self.assertEqual(before, after)
        self.assertEqual(first.asset_id, second.asset_id)
        self.assertFalse(first.repeated_location)
        self.assertTrue(second.duplicate_content)
        self.assertTrue(second.repeated_location)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM locations").fetchone()[0], 1)
        connection.close()

    def test_duplicate_content_records_two_locations(self) -> None:
        first_path = self._write("one.bin", b"same synthetic bytes")
        second_path = self._write("two.bin", b"same synthetic bytes")
        first = catalog_file(first_path, self.db, 0, include_media_probe=False)
        second = catalog_file(second_path, self.db, 0, include_media_probe=False)

        self.assertEqual(first.asset_id, second.asset_id)
        self.assertTrue(second.duplicate_content)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM locations").fetchone()[0], 2)
        connection.close()

    def test_stability_resets_when_signature_changes(self) -> None:
        source = self._write("growing.bin", b"a")
        calls = 0

        def mutate_once(_: float) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                source.write_bytes(b"ab")

        result = wait_until_stable(source, 0, observations=2, sleep=mutate_once)
        self.assertEqual(result.st_size, 2)
        self.assertEqual(calls, 2)

    def test_scan_continues_after_individual_error(self) -> None:
        source = self._write("valid.txt", b"valid")
        results, errors = scan_directory(self.inbox, self.db, 0)
        self.assertEqual(len(results), 1)
        self.assertEqual(errors, [])
        self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
