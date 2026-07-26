from __future__ import annotations

import json
import sqlite3
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from beacon.catalog import catalog_file
from beacon.database import SCHEMA_VERSION, database_integrity
from beacon.local_analysis import (
    analysis_scope_preview,
    create_local_analysis_job,
    create_selected_local_analysis_job,
    list_local_analysis_jobs,
    recover_local_analysis_jobs,
    retry_local_analysis_failures,
    request_local_analysis_cancel,
    run_local_analysis_job,
    _default_analyzer,
    _prepare_media_context,
    _process_is_alive,
)
from beacon.media import should_probe
from beacon.repository import asset_detail
from beacon.transcripts import get_asset_transcript, save_asset_transcript


class LocalAnalysisJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "runtime" / "beacon.db"
        self.sources = self.root / "sources"
        self.sources.mkdir()
        for name, content in (
            ("one.txt", b"one"),
            ("two.txt", b"two"),
        ):
            source = self.sources / name
            source.write_bytes(content)
            catalog_file(
                source,
                self.db,
                stability_seconds=0,
                include_media_probe=False,
                include_thumbnail_generation=False,
            )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_worker_liveness_detects_current_and_missing_processes(self) -> None:
        self.assertTrue(_process_is_alive(os.getpid()))
        self.assertFalse(_process_is_alive(2_147_483_647))

    def test_transcript_is_checksum_bound_and_visible_in_asset_detail(self) -> None:
        connection = sqlite3.connect(self.db)
        try:
            asset_id, source_sha256 = connection.execute(
                "SELECT id,sha256 FROM assets ORDER BY id LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
        saved = save_asset_transcript(
            self.db,
            asset_id=asset_id,
            source_sha256=source_sha256,
            text="A complete local transcript fixture.",
            language="en",
            language_probability=0.99,
        )
        self.assertEqual(saved["text"], "A complete local transcript fixture.")
        cached = get_asset_transcript(
            self.db, asset_id, source_sha256=source_sha256
        )
        self.assertIsNotNone(cached)
        detail = asset_detail(self.db, asset_id)
        assert detail is not None
        self.assertEqual(
            detail["transcript"]["text"],
            "A complete local transcript fixture.",
        )

    @staticmethod
    def _analyzer(endpoint: str, model: str, asset: dict[str, object]) -> dict:
        return {
            "title": Path(str(asset["source_path"])).stem.title(),
            "description": "Candidate derived from verified local context.",
            "content_observations": [
                "The bounded text fixture contains locally verified content."
            ],
            "evidence_mode": "text_content",
            "media_category": "text fixture",
            "tags": ["local", "fixture"],
            "privacy_flags": ["none detected from bounded context"],
            "organization_suggestion": "Leave in test scope; no move authorized.",
            "confidence": 0.8,
        }

    def test_local_job_imports_checksum_bound_candidates(self) -> None:
        preview = analysis_scope_preview(self.db)
        self.assertEqual(preview["assets"], 2)
        job_id = create_local_analysis_job(self.db, model="fixture-model")

        result = run_local_analysis_job(
            self.db, job_id, analyzer=self._analyzer
        )

        self.assertEqual(result.state, "complete")
        self.assertEqual(result.completed, 2)
        self.assertEqual(result.failed, 0)
        [job] = list_local_analysis_jobs(self.db)
        self.assertEqual(job["id"], job_id)
        self.assertEqual(job["completed_count"], 2)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM analysis_results"
                ).fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT SUM(external_inference) FROM analysis_runs"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT MIN(attempts),MAX(attempts) FROM local_analysis_items"
                ).fetchone(),
                (1, 1),
            )
        finally:
            connection.close()
        self.assertEqual(analysis_scope_preview(self.db)["assets"], 0)
        self.assertEqual(database_integrity(self.db)["schema_version"], SCHEMA_VERSION)
        resumed = run_local_analysis_job(
            self.db, job_id, analyzer=self._analyzer
        )
        self.assertEqual(resumed.analysis_run_id, result.analysis_run_id)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM analysis_results"
                ).fetchone()[0],
                2,
            )
        finally:
            connection.close()

    def test_support_files_are_excluded_from_analysis_scope(self) -> None:
        sidecar = self.sources / "camera-settings.xmp"
        sidecar.write_text("<x:xmpmeta>fixture</x:xmpmeta>", encoding="utf-8")
        preview_cache = (
            self.sources
            / "PROJECT"
            / "Adobe Premiere Pro Video Previews"
            / "sequence.prv"
            / "rendered-cache.mpeg"
        )
        preview_cache.parent.mkdir(parents=True)
        preview_cache.write_bytes(b"generated preview cache")
        catalog_file(
            sidecar,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        catalog_file(
            preview_cache,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        preview = analysis_scope_preview(self.db)
        self.assertEqual(preview["assets"], 2)

    def test_selected_analysis_job_contains_only_explicit_assets(self) -> None:
        connection = sqlite3.connect(self.db)
        try:
            asset_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT id FROM assets ORDER BY id"
                ).fetchall()
            ]
        finally:
            connection.close()

        job_id = create_selected_local_analysis_job(
            self.db,
            asset_ids=[asset_ids[1]],
            model="fixture-model",
        )

        connection = sqlite3.connect(self.db)
        try:
            rows = connection.execute(
                """
                SELECT asset_id FROM local_analysis_items
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(rows, [(asset_ids[1],)])

    def test_still_image_keeps_thumbnail_instead_of_video_sampling(self) -> None:
        source = self.sources / "photograph.jpg"
        source.write_bytes(b"source bytes are checksum context only")
        thumbnail = self.root / "thumbnail.jpg"
        Image.new("RGB", (80, 48), "#4A8C91").save(thumbnail)
        asset = {
            "source_path": str(source),
            "media_metadata": {
                "beacon_kind": "image",
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "mjpeg",
                        "duration": "0.040000",
                    }
                ],
            },
            "thumbnail_path": str(thumbnail),
        }

        with patch("beacon.local_analysis.subprocess.run") as run:
            context, images, temporary_root = _prepare_media_context(asset)
        try:
            self.assertEqual(context["media_mode"], "still_image")
            self.assertEqual(images, [thumbnail])
            run.assert_not_called()
        finally:
            import shutil

            shutil.rmtree(temporary_root, ignore_errors=True)

    def test_incomplete_audio_metadata_is_reprobed_and_persisted(self) -> None:
        source = self.sources / "field-recording.aiff"
        source.write_bytes(b"valid source fixture")
        cataloged = catalog_file(
            source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        job_id = create_selected_local_analysis_job(
            self.db,
            asset_ids=[cataloged.asset_id],
            model="fixture-model",
        )
        refreshed = {
            "format": {"duration": "12.5"},
            "streams": [
                {
                    "codec_name": "pcm_s16be",
                    "codec_type": "audio",
                    "sample_rate": "48000",
                }
            ],
        }

        def audio_analyzer(
            endpoint: str, model: str, asset: dict[str, object]
        ) -> dict:
            metadata = asset["media_metadata"]
            assert isinstance(metadata, dict)
            self.assertEqual(metadata["streams"][0]["codec_type"], "audio")
            result = self._analyzer(endpoint, model, asset)
            result["evidence_mode"] = "audio_content"
            return result

        with patch("beacon.local_analysis.probe", return_value=refreshed):
            result = run_local_analysis_job(
                self.db,
                job_id,
                analyzer=audio_analyzer,
            )

        self.assertEqual(result.state, "complete")
        connection = sqlite3.connect(self.db)
        try:
            stored = connection.execute(
                "SELECT media_metadata_json FROM assets WHERE id=?",
                (cataloged.asset_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(json.loads(stored), refreshed)

    def test_black_video_samples_fall_back_to_audio_content(self) -> None:
        source = self.sources / "black-with-audio.mp4"
        source.write_bytes(b"source fixture")
        asset = {
            "source_path": str(source),
            "media_metadata": {
                "format": {"duration": "10"},
                "streams": [
                    {"codec_type": "video", "duration": "10"},
                    {"codec_type": "audio", "duration": "10"},
                ],
            },
            "thumbnail_path": "",
        }

        def create_derivative(command: list[str], **kwargs: object):
            destination = Path(command[-1])
            color = "#000000" if destination.suffix == ".jpg" else "#A36B35"
            Image.new("RGB", (64, 48), color).save(destination)

            class Completed:
                returncode = 0

            return Completed()

        with (
            patch("beacon.local_analysis.shutil.which", return_value="ffmpeg"),
            patch(
                "beacon.local_analysis.subprocess.run",
                side_effect=create_derivative,
            ),
            patch(
                "beacon.local_analysis._transcribe_audio",
                return_value={
                    "status": "complete",
                    "analysis_excerpt": "Two people discuss an upcoming trip.",
                },
            ),
        ):
            context, images, temporary_root = _prepare_media_context(asset)
        try:
            self.assertEqual(
                context["visual_sampling_outcome"],
                "uniformly_near_black",
            )
            self.assertEqual(context["expected_evidence_mode"], "audio_content")
            self.assertEqual(
                context["speech_analysis"]["transcript"],
                "Two people discuss an upcoming trip.",
            )
            self.assertEqual(len(images), 1)
            self.assertEqual(images[0].name, "audio-spectrum.png")
        finally:
            import shutil

            shutil.rmtree(temporary_root, ignore_errors=True)

    def test_aiff_is_in_the_media_probe_scope(self) -> None:
        self.assertTrue(should_probe(Path("field-recording.aiff")))
        self.assertTrue(should_probe(Path("field-recording.AIF")))

    def test_local_model_retries_invalid_structured_content(self) -> None:
        source = self.sources / "retry-evidence.txt"
        source.write_text(
            "A local transcript about a sunrise over a lake.",
            encoding="utf-8",
        )
        valid = {
            "title": "Sunrise Over a Lake",
            "description": "Text describing a sunrise over a lake.",
            "content_observations": [
                "The text discusses a sunrise over a lake."
            ],
            "evidence_mode": "text_content",
            "media_category": "document",
            "tags": ["sunrise", "lake"],
            "privacy_flags": [],
            "organization_suggestion": "Documents/Nature",
            "stock_metadata": {},
            "confidence": 0.8,
        }
        responses = [
            {"message": {"content": "{not-json"}},
            {"message": {"content": json.dumps(valid)}},
        ]

        with patch(
            "beacon.local_analysis._request_json",
            side_effect=responses,
        ) as request:
            result = _default_analyzer(
                "http://127.0.0.1:11434",
                "fixture-model",
                {
                    "source_path": str(source),
                    "media_metadata": {},
                    "thumbnail_path": "",
                    "size_bytes": source.stat().st_size,
                },
            )

        self.assertEqual(result["evidence_mode"], "text_content")
        self.assertEqual(request.call_count, 2)

    def test_pipeline_stage_is_durable_and_clears_at_completion(self) -> None:
        observed: list[tuple[str, str | None]] = []

        def stage_aware_analyzer(
            endpoint: str, model: str, asset: dict[str, object]
        ) -> dict:
            [job] = list_local_analysis_jobs(self.db)
            observed.append(
                (str(job["current_stage"]), job["current_source_path"])
            )
            callback = asset["stage_callback"]
            assert callable(callback)
            callback("transcribing_audio")
            [job] = list_local_analysis_jobs(self.db)
            observed.append(
                (str(job["current_stage"]), job["current_source_path"])
            )
            return self._analyzer(endpoint, model, asset)

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        result = run_local_analysis_job(
            self.db, job_id, analyzer=stage_aware_analyzer
        )

        self.assertEqual(result.state, "complete")
        self.assertTrue(
            all(path and Path(path).name in {"one.txt", "two.txt"}
                for _, path in observed)
        )
        self.assertIn("verifying_source", {stage for stage, _ in observed})
        self.assertIn("transcribing_audio", {stage for stage, _ in observed})
        [job] = list_local_analysis_jobs(self.db)
        self.assertIsNone(job["current_stage"])
        self.assertIsNone(job["current_asset_id"])
        self.assertIsNotNone(job["current_stage_updated_at"])

    def test_percentage_confidence_is_normalized_with_provenance(self) -> None:
        def percentage_analyzer(
            endpoint: str, model: str, asset: dict[str, object]
        ) -> dict:
            result = self._analyzer(endpoint, model, asset)
            result["confidence"] = 95
            return result

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        result = run_local_analysis_job(
            self.db, job_id, analyzer=percentage_analyzer
        )

        self.assertEqual(result.state, "complete")
        connection = sqlite3.connect(self.db)
        try:
            rows = connection.execute(
                "SELECT confidence,provenance_json FROM analysis_results"
            ).fetchall()
            self.assertTrue(all(row[0] == 0.95 for row in rows))
            self.assertTrue(
                all("percentage-style" in row[1] for row in rows)
            )
        finally:
            connection.close()

    def test_empty_organization_suggestion_gets_safe_fallback(self) -> None:
        def empty_suggestion_analyzer(
            endpoint: str, model: str, asset: dict[str, object]
        ) -> dict:
            result = self._analyzer(endpoint, model, asset)
            result["organization_suggestion"] = ""
            return result

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        result = run_local_analysis_job(
            self.db, job_id, analyzer=empty_suggestion_analyzer
        )

        self.assertEqual(result.state, "complete")
        connection = sqlite3.connect(self.db)
        try:
            payload, provenance = connection.execute(
                "SELECT payload_json,provenance_json FROM analysis_results LIMIT 1"
            ).fetchone()
            self.assertIn("Human review is required", payload)
            self.assertIn("empty organization suggestion", provenance)
        finally:
            connection.close()

    def test_invalid_candidate_fails_without_blocking_valid_publication(self) -> None:
        calls = 0

        def one_invalid(
            endpoint: str, model: str, asset: dict[str, object]
        ) -> dict:
            nonlocal calls
            calls += 1
            result = self._analyzer(endpoint, model, asset)
            if calls == 1:
                result["title"] = ""
            return result

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        result = run_local_analysis_job(
            self.db,
            job_id,
            analyzer=one_invalid,
        )

        self.assertEqual(result.state, "partial")
        self.assertEqual(result.completed, 1)
        self.assertEqual(result.failed, 1)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM analysis_results"
                ).fetchone()[0],
                1,
            )
            state, worker_pid, stage = connection.execute(
                """
                SELECT state,worker_pid,current_stage
                FROM local_analysis_jobs WHERE id=?
                """,
                (job_id,),
            ).fetchone()
            self.assertEqual(state, "partial")
            self.assertIsNone(worker_pid)
            self.assertIsNone(stage)
        finally:
            connection.close()

    def test_finalization_resume_does_not_duplicate_metadata_revisions(
        self,
    ) -> None:
        job_id = create_local_analysis_job(self.db, model="fixture-model")
        first = run_local_analysis_job(
            self.db,
            job_id,
            analyzer=self._analyzer,
        )
        connection = sqlite3.connect(self.db)
        try:
            revision_count = connection.execute(
                "SELECT COUNT(*) FROM asset_metadata_revisions"
            ).fetchone()[0]
            connection.execute(
                """
                UPDATE local_analysis_jobs
                SET state='paused',completed_at=NULL
                WHERE id=?
                """,
                (job_id,),
            )
            connection.commit()
        finally:
            connection.close()

        second = run_local_analysis_job(
            self.db,
            job_id,
            analyzer=self._analyzer,
        )

        self.assertEqual(first.analysis_run_id, second.analysis_run_id)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM asset_metadata_revisions"
                ).fetchone()[0],
                revision_count,
            )
        finally:
            connection.close()

    def test_finalization_failure_is_terminal_and_truthful(self) -> None:
        job_id = create_local_analysis_job(self.db, model="fixture-model")

        with patch(
            "beacon.local_analysis.import_analysis_manifest",
            side_effect=RuntimeError("synthetic publication failure"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "synthetic publication failure",
            ):
                run_local_analysis_job(
                    self.db,
                    job_id,
                    analyzer=self._analyzer,
                )

        connection = sqlite3.connect(self.db)
        try:
            state, worker_pid, stage, error = connection.execute(
                """
                SELECT state,worker_pid,current_stage,error
                FROM local_analysis_jobs WHERE id=?
                """,
                (job_id,),
            ).fetchone()
            self.assertEqual(state, "failed")
            self.assertIsNone(worker_pid)
            self.assertIsNone(stage)
            self.assertIn("synthetic publication failure", error)
        finally:
            connection.close()

    def test_selected_generated_artifact_is_excluded_without_model_call(
        self,
    ) -> None:
        cache = (
            self.sources
            / "PROJECT"
            / "Adobe Premiere Pro Video Previews"
            / "sequence.prv"
            / "rendered-cache.mpeg"
        )
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b"generated preview cache")
        cataloged = catalog_file(
            cache,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        job_id = create_selected_local_analysis_job(
            self.db,
            asset_ids=[cataloged.asset_id],
            model="fixture-model",
        )

        analyzer = patch(
            "beacon.local_analysis._default_analyzer"
        )
        with analyzer as mocked:
            result = run_local_analysis_job(self.db, job_id)

        mocked.assert_not_called()
        self.assertEqual(result.state, "complete")
        self.assertEqual(result.completed, 0)
        self.assertEqual(result.excluded, 1)
        self.assertEqual(result.failed, 0)

    def test_interrupted_item_recovers_to_pending(self) -> None:
        job_id = create_local_analysis_job(self.db, model="fixture-model")
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                """
                UPDATE local_analysis_jobs
                SET state='running',current_stage='visually_observing',
                    current_stage_updated_at='fixture'
                WHERE id=?
                """,
                (job_id,),
            )
            connection.execute(
                """
                UPDATE local_analysis_items SET state='running'
                WHERE id=(SELECT id FROM local_analysis_items WHERE job_id=? LIMIT 1)
                """,
                (job_id,),
            )
            connection.commit()
        finally:
            connection.close()

        self.assertEqual(recover_local_analysis_jobs(self.db), 1)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    """
                    SELECT state,current_stage,current_asset_id
                    FROM local_analysis_jobs WHERE id=?
                    """,
                    (job_id,),
                ).fetchone()[0],
                "paused",
            )
            self.assertEqual(
                connection.execute(
                    """
                    SELECT current_stage,current_asset_id
                    FROM local_analysis_jobs WHERE id=?
                    """,
                    (job_id,),
                ).fetchone(),
                (None, None),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM local_analysis_items WHERE job_id=? AND state='pending'",
                    (job_id,),
                ).fetchone()[0],
                2,
            )
        finally:
            connection.close()

    def test_cancel_stops_between_assets_and_preserves_pending(self) -> None:
        job_id = create_local_analysis_job(self.db, model="fixture-model")
        callbacks = 0

        def cancel_after_first() -> None:
            nonlocal callbacks
            callbacks += 1
            if callbacks == 1:
                request_local_analysis_cancel(self.db, job_id)

        result = run_local_analysis_job(
            self.db,
            job_id,
            analyzer=self._analyzer,
            progress_callback=cancel_after_first,
        )

        self.assertEqual(result.state, "cancelled")
        self.assertEqual(result.completed, 1)
        self.assertEqual(result.pending, 1)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT SUM(attempts) FROM local_analysis_items WHERE job_id=?",
                    (job_id,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    """
                    SELECT current_stage,current_asset_id
                    FROM local_analysis_jobs WHERE id=?
                    """,
                    (job_id,),
                ).fetchone(),
                (None, None),
            )
        finally:
            connection.close()

    def test_failed_items_can_retry_in_the_same_job(self) -> None:
        calls = 0

        def fail_once(endpoint: str, model: str, asset: dict[str, object]) -> dict:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("bounded fixture failure")
            return self._analyzer(endpoint, model, asset)

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        first = run_local_analysis_job(self.db, job_id, analyzer=fail_once)
        self.assertEqual(first.state, "partial")
        self.assertEqual(retry_local_analysis_failures(self.db, job_id), 1)
        second = run_local_analysis_job(
            self.db, job_id, analyzer=self._analyzer
        )
        self.assertEqual(second.state, "complete")
        self.assertEqual(second.completed, 2)
