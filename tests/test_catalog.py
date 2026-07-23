from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from beacon.catalog import catalog_file, scan_directory, sha256_file, watch_directory
from beacon.media import probe
from beacon.repository import asset_detail
from beacon.stability import wait_until_stable
from beacon.thumbnails import ensure_thumbnail


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

    def test_changed_during_hash_is_rejected_without_database_record(self) -> None:
        source = self._write("changing.bin", b"before")

        def hash_then_change(path: Path) -> str:
            checksum = sha256_file(path)
            path.write_bytes(b"after-content")
            return checksum

        with patch("beacon.catalog.sha256_file", side_effect=hash_then_change):
            with self.assertRaisesRegex(RuntimeError, "changed while hashing"):
                catalog_file(source, self.db, 0, include_media_probe=False)
        self.assertFalse(self.db.exists())

    def test_unavailable_inbox_returns_actionable_error(self) -> None:
        missing = self.root / "unavailable"
        with self.assertLogs("beacon.catalog", level="ERROR"):
            results, errors = scan_directory(missing, self.db, 0)
        self.assertEqual(results, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("inbox unavailable", errors[0][1])

    def test_foreground_watcher_catalogs_synthetic_file(self) -> None:
        source = self._write("noticed.txt", b"noticed by Beacon")
        cataloged, errors = watch_directory(
            self.inbox,
            self.db,
            stability_seconds=0,
            poll_seconds=0,
            max_cycles=2,
            sleep=lambda _: None,
        )
        self.assertEqual(cataloged, 1)
        self.assertEqual(errors, 0)
        self.assertEqual(source.read_bytes(), b"noticed by Beacon")

    def test_scan_continues_after_individual_error(self) -> None:
        first = self._write("first.txt", b"first")
        second = self._write("second.txt", b"second")
        real_catalog = catalog_file

        def fail_one(path: Path, *args: object, **kwargs: object):
            if path.name == "first.txt":
                raise OSError("synthetic read failure")
            return real_catalog(path, *args, **kwargs)

        with patch("beacon.catalog.catalog_file", side_effect=fail_one):
            with self.assertLogs("beacon.catalog", level="ERROR"):
                results, errors = scan_directory(self.inbox, self.db, 0)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("synthetic read failure", errors[0][1])
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_ffprobe_timeout_becomes_retryable_metadata(self) -> None:
        source = self._write("timeout.wav", b"synthetic")
        with patch.dict(os.environ, {"BEACON_FFPROBE": "synthetic-ffprobe"}):
            with patch(
                "beacon.media.subprocess.run",
                side_effect=subprocess.TimeoutExpired("ffprobe", 60),
            ):
                metadata = probe(source)
        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertIsNone(metadata["returncode"])
        self.assertIn("timed out", metadata["error"])

    def test_image_probe_marks_still_image_kind(self) -> None:
        source = self._write("still.JPG", b"synthetic image bytes")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "codec_name": "mjpeg",
                            "codec_type": "video",
                            "width": 4032,
                            "height": 3024,
                        }
                    ]
                }
            ),
            stderr="",
        )
        with patch.dict(os.environ, {"BEACON_FFPROBE": "synthetic-ffprobe"}):
            with patch("beacon.media.subprocess.run", return_value=completed):
                metadata = probe(source)
        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(metadata["beacon_kind"], "image")

    def test_image_metadata_is_visible_to_desktop_repository(self) -> None:
        source = self._write("still.jpg", b"synthetic image bytes")
        metadata = {
            "beacon_kind": "image",
            "streams": [
                {
                    "codec_name": "mjpeg",
                    "codec_type": "video",
                    "width": 4032,
                    "height": 3024,
                }
            ],
        }
        with patch("beacon.catalog.probe", return_value=metadata):
            result = catalog_file(
                source,
                self.db,
                0,
                include_thumbnail_generation=False,
            )
        detail = asset_detail(self.db, result.asset_id)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["kind"], "image")
        self.assertEqual(detail["codec"], "mjpeg")
        self.assertEqual(detail["dimensions"], "4032 × 3024")
        self.assertIsNone(detail["duration_seconds"])

    def test_thumbnail_derivative_is_atomic_verified_and_idempotent(self) -> None:
        source = self._write("wave.wav", b"synthetic source bytes")
        source_hash = sha256_file(source)
        cataloged = catalog_file(
            source,
            self.db,
            0,
            include_media_probe=False,
        )
        metadata = {
            "streams": [{"codec_name": "pcm_s16le", "codec_type": "audio"}]
        }

        def fake_ffmpeg(args: list[str], **_: object) -> subprocess.CompletedProcess:
            Path(args[-1]).write_bytes(b"verified synthetic png")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        thumbnail_probe = {
            "beacon_kind": "image",
            "streams": [
                {
                    "codec_name": "png",
                    "codec_type": "video",
                    "width": 640,
                    "height": 360,
                }
            ],
        }
        with patch.dict(os.environ, {"BEACON_FFMPEG": "synthetic-ffmpeg"}):
            with patch("beacon.thumbnails.subprocess.run", side_effect=fake_ffmpeg) as run:
                with patch("beacon.thumbnails.probe", return_value=thumbnail_probe):
                    first = ensure_thumbnail(
                        source,
                        self.db,
                        asset_id=cataloged.asset_id,
                        source_sha256=source_hash,
                        media_metadata=metadata,
                    )
                    second = ensure_thumbnail(
                        source,
                        self.db,
                        asset_id=cataloged.asset_id,
                        source_sha256=source_hash,
                        media_metadata=metadata,
                    )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(sha256_file(source), source_hash)
        self.assertTrue(Path(first.path).is_file())
        self.assertEqual(list(Path(first.path).parent.glob("*.partial.png")), [])
        with sqlite3.connect(self.db) as connection:
            connection.row_factory = sqlite3.Row
            derivative = connection.execute(
                """
                SELECT asset_id, kind, source_sha256, sha256, state
                FROM derivatives
                """
            ).fetchone()
            complete_events = connection.execute(
                """
                SELECT COUNT(*) FROM system_events
                WHERE kind = 'thumbnail' AND state = 'complete'
                """
            ).fetchone()[0]
        connection.close()
        self.assertEqual(derivative["asset_id"], cataloged.asset_id)
        self.assertEqual(derivative["kind"], "thumbnail")
        self.assertEqual(derivative["source_sha256"], source_hash)
        self.assertEqual(derivative["sha256"], first.sha256)
        self.assertEqual(derivative["state"], "complete")
        self.assertEqual(complete_events, 1)

    @unittest.skipUnless(
        os.environ.get("BEACON_FFPROBE"),
        "set BEACON_FFPROBE to run the real media probe acceptance tests",
    )
    def test_ffprobe_extracts_generated_wave_metadata(self) -> None:
        source = self.inbox / "silence.wav"
        with wave.open(str(source), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8_000)
            stream.writeframes(b"\x00\x00" * 800)
        metadata = probe(source)
        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(metadata["streams"][0]["codec_name"], "pcm_s16le")
        result = catalog_file(source, self.db, 0)
        with sqlite3.connect(self.db) as connection:
            stored = connection.execute(
                "SELECT media_metadata_json FROM assets WHERE id = ?",
                (result.asset_id,),
            ).fetchone()[0]
        connection.close()
        self.assertEqual(json.loads(stored)["streams"][0]["codec_name"], "pcm_s16le")

    @unittest.skipUnless(
        os.environ.get("BEACON_FFPROBE"),
        "set BEACON_FFPROBE to run the real media probe acceptance tests",
    )
    def test_corrupt_media_is_cataloged_with_probe_error(self) -> None:
        source = self._write("corrupt.wav", b"not a wave file")
        result = catalog_file(source, self.db, 0)
        with sqlite3.connect(self.db) as connection:
            stored = connection.execute(
                "SELECT media_metadata_json FROM assets WHERE id = ?",
                (result.asset_id,),
            ).fetchone()[0]
        connection.close()
        metadata = json.loads(stored)
        self.assertNotEqual(metadata["returncode"], 0)
        self.assertTrue(metadata["error"])


if __name__ == "__main__":
    unittest.main()
