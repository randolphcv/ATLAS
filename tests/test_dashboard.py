from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from beacon.api import AppSettings, create_app
from beacon.catalog import catalog_file
from beacon.database import create_backup, database_integrity


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "runtime" / "beacon.db"
        self.backups = self.root / "runtime" / "backups"
        self.inbox = self.root / "inbox"
        self.inbox.mkdir()
        self.source = self.inbox / "signal.txt"
        self.source.write_bytes(b"synthetic dashboard signal")
        self.result = catalog_file(
            self.source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
        )
        self.client = TestClient(
            create_app(AppSettings(db_path=self.db, backup_dir=self.backups))
        )

    def tearDown(self) -> None:
        self.client.close()
        self.temp.cleanup()

    def test_dashboard_and_read_only_catalog_api(self) -> None:
        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("ATLAS", dashboard.text)
        self.assertIn("frame-ancestors 'none'", dashboard.headers["content-security-policy"])

        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()["local_only"])
        self.assertEqual(health.json()["database"]["integrity"], "ok")
        self.assertEqual(health.headers["cache-control"], "no-store")

        summary = self.client.get("/api/summary").json()
        self.assertEqual(summary["assets"], 1)
        self.assertEqual(summary["locations"], 1)

        assets = self.client.get("/api/assets", params={"q": "signal"}).json()
        self.assertEqual(assets["total"], 1)
        self.assertEqual(assets["items"][0]["id"], self.result.asset_id)

        detail = self.client.get(f"/api/assets/{self.result.asset_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["locations"][0]["path"], str(self.source.resolve()))
        self.assertEqual(
            self.client.get("/api/assets/not-an-asset").status_code,
            404,
        )

    def test_backup_action_requires_explicit_local_intent(self) -> None:
        denied = self.client.post("/api/backups")
        self.assertEqual(denied.status_code, 403)

        response = self.client.post(
            "/api/backups",
            headers={"X-ATLAS-Action": "create-backup"},
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        backup_path = Path(payload["path"])
        self.assertTrue(backup_path.exists())
        self.assertEqual(payload["integrity"], "ok")
        self.assertEqual(
            hashlib.sha256(backup_path.read_bytes()).hexdigest(),
            payload["sha256"],
        )
        self.assertEqual(len(self.client.get("/api/backups").json()["items"]), 1)

    def test_online_backup_is_consistent_and_does_not_change_source(self) -> None:
        source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        backup = create_backup(self.db, self.backups)
        self.assertEqual(database_integrity(Path(backup.path))["state"], "healthy")
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), source_hash)
        with sqlite3.connect(backup.path) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM locations").fetchone()[0],
                1,
            )
        connection.close()
        self.assertEqual(list(self.backups.glob("*.partial")), [])

    def test_corrupt_database_health_is_actionable(self) -> None:
        corrupt = self.root / "corrupt.db"
        corrupt.write_bytes(b"not sqlite")
        result = database_integrity(corrupt)
        self.assertEqual(result["state"], "attention")
        self.assertNotEqual(result["integrity"], "ok")


if __name__ == "__main__":
    unittest.main()
