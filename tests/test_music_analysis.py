from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from beacon.catalog import catalog_file
from beacon.database import SCHEMA_VERSION, database_integrity
from beacon.music_analysis import analyze_asset_music, runtime_status
from beacon.repository import asset_detail


class MusicAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "beacon.db"
        self.source = self.root / "source.wav"
        self.source.write_bytes(b"synthetic music fixture")
        self.asset = catalog_file(
            self.source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        self.worker = self.root / "worker.py"
        self.worker.write_text(
            """
import argparse, hashlib, json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--status", action="store_true")
p.add_argument("--source")
p.add_argument("--output", type=Path)
p.add_argument("--full", action="store_true")
a=p.parse_args()
if a.status:
    print(json.dumps({"worker_version":"beacon-music-v3","cuda_available":True}))
else:
    a.output.mkdir(parents=True, exist_ok=True)
    midi=a.output/"transcription.mid"
    midi.write_bytes(b"midi fixture")
    print(json.dumps({
      "worker_version":"beacon-music-v3","status":"complete",
      "bpm":120.0,"key":"C major","key_confidence":0.8,
      "music_confidence":0.95,"chords":[{"chord":"C"}],
      "notes":{"note_count":3,"pitch_range":"C4-G4","prominent_notes":["C4","E4","G4"]},
      "stems":[],"derivatives":[{
        "kind":"music_midi","path":str(midi),
        "sha256":hashlib.sha256(midi.read_bytes()).hexdigest(),
        "size_bytes":midi.stat().st_size
      }]
    }))
""".strip(),
            encoding="utf-8",
        )
        self.environment = {
            "BEACON_MUSIC_PYTHON": sys.executable,
            "BEACON_MUSIC_WORKER": str(self.worker),
            "PROGRAMDATA": str(self.root / "programdata"),
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_runtime_analysis_is_verified_persistent_and_cached(self) -> None:
        with patch.dict(os.environ, self.environment):
            self.assertTrue(runtime_status()["available"])
            result = analyze_asset_music(
                self.db,
                asset_id=self.asset.asset_id,
                source_path=self.source,
                source_sha256=self.asset.sha256,
            )
            self.assertEqual(result["cache_status"], "created")
            self.worker.unlink()
            cached = analyze_asset_music(
                self.db,
                asset_id=self.asset.asset_id,
                source_path=self.source,
                source_sha256=self.asset.sha256,
            )
        self.assertEqual(cached["cache_status"], "cached")
        detail = asset_detail(self.db, self.asset.asset_id)
        assert detail is not None
        self.assertEqual(detail["music_analysis"]["key"], "C major")
        self.assertEqual(
            database_integrity(self.db)["schema_version"], SCHEMA_VERSION
        )


if __name__ == "__main__":
    unittest.main()
