from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pillow_heif import from_pillow

from beacon.catalog import catalog_file, sha256_file
from beacon.media import probe
from beacon.preview_derivatives import (
    ensure_video_preview,
    needs_video_compatibility_preview,
)
from beacon.repository import asset_detail


class HeicPreviewTests(unittest.TestCase):
    def test_heic_catalog_creates_verified_png_preview_without_source_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic.heic"
            image = Image.new("RGB", (80, 48), "#C39A58")
            from_pillow(image).save(source, quality=90)
            source_hash = sha256_file(source)
            db_path = root / "runtime" / "beacon.db"

            with patch.dict(
                os.environ,
                {"BEACON_THUMBNAIL_ROOT": str(root / "thumbnails")},
            ):
                result = catalog_file(
                    source,
                    db_path,
                    stability_seconds=0,
                )

            detail = asset_detail(db_path, result.asset_id)
            self.assertIsNotNone(detail)
            self.assertEqual(detail["kind"], "image")
            stream = detail["media_metadata"]["streams"][0]
            self.assertEqual((stream["width"], stream["height"]), (80, 48))
            thumbnail = Path(str(detail["thumbnail_path"]))
            self.assertTrue(thumbnail.is_file())
            self.assertEqual(thumbnail.suffix, ".png")
            self.assertEqual(sha256_file(source), source_hash)


class VideoPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            self.skipTest("FFmpeg and ffprobe are required")

    def test_apple_high_frame_rate_video_gets_idempotent_cfr_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "synthetic-slo-mo.mov"
            completed = subprocess.run(
                [
                    str(self.ffmpeg),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=320x180:rate=120:duration=1",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=1",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-metadata",
                    "make=Apple",
                    "-shortest",
                    str(source),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            metadata = probe(source)
            self.assertIsNotNone(metadata)
            self.assertTrue(
                needs_video_compatibility_preview(source, metadata)
            )
            source_hash = sha256_file(source)
            db_path = root / "runtime" / "beacon.db"
            cataloged = catalog_file(
                source,
                db_path,
                stability_seconds=0,
                include_thumbnail_generation=False,
            )

            with patch.dict(
                os.environ,
                {
                    "BEACON_FFMPEG": str(self.ffmpeg),
                    "BEACON_FFPROBE": str(self.ffprobe),
                    "BEACON_PREVIEW_ROOT": str(root / "previews"),
                },
            ):
                first = ensure_video_preview(
                    source,
                    db_path,
                    asset_id=cataloged.asset_id,
                    source_sha256=source_hash,
                )
                second = ensure_video_preview(
                    source,
                    db_path,
                    asset_id=cataloged.asset_id,
                    source_sha256=source_hash,
                )

            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.path, second.path)
            proxy_metadata = probe(Path(first.path))
            video = next(
                stream
                for stream in proxy_metadata["streams"]
                if stream.get("codec_type") == "video"
            )
            self.assertEqual(video["codec_name"], "h264")
            self.assertAlmostEqual(
                float(video["avg_frame_rate"].split("/")[0])
                / float(video["avg_frame_rate"].split("/")[1]),
                30.0,
                places=2,
            )
            self.assertEqual(sha256_file(source), source_hash)

    def test_standard_video_does_not_require_proxy(self) -> None:
        source = Path("ordinary.mp4")
        metadata = {
            "streams": [
                {
                    "codec_type": "video",
                    "r_frame_rate": "30/1",
                    "avg_frame_rate": "30/1",
                }
            ],
            "format": {"tags": {"encoder": "synthetic"}},
        }
        self.assertFalse(
            needs_video_compatibility_preview(source, metadata)
        )


if __name__ == "__main__":
    unittest.main()
