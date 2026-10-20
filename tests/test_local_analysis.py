from __future__ import annotations

import errno
import json
import sqlite3
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from beacon.config import projects_root
from beacon.catalog import catalog_file
from beacon.database import SCHEMA_VERSION, database_integrity
from beacon.database import connect, migrate
from beacon.local_analysis import (
    ANALYSIS_SCOPE_KINDS,
    DEFERRED_DOCUMENT_EXTENSIONS,
    NON_CONTENT_COMPANION_EXTENSIONS,
    _artifact_exclusion_reason,
    _complete_analysis_exclusion,
    analysis_scope_preview,
    analysis_scope_previews,
    create_local_analysis_job,
    job_may_place,
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
from beacon.repository import asset_detail, is_hidden_support_path
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

    def test_general_scopes_partition_total_analysis_without_batch_caps(
        self,
    ) -> None:
        image = self.sources / "frame.jpg"
        image.write_bytes(b"synthetic image scope")
        raw = self.sources / "negative.cr3"
        raw.write_bytes(b"synthetic raw scope")
        audio = self.sources / "recording.wav"
        audio.write_bytes(b"synthetic audio scope")
        for source in (image, raw, audio):
            catalog_file(
                source,
                self.db,
                stability_seconds=0,
                include_media_probe=False,
                include_thumbnail_generation=False,
            )
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                """
                UPDATE assets SET media_metadata_json=?
                WHERE id=(
                    SELECT asset_id FROM locations WHERE path=?
                )
                """,
                (
                    json.dumps(
                        {
                            "streams": [
                                {
                                    "codec_type": "audio",
                                    "codec_name": "pcm_s16le",
                                }
                            ]
                        }
                    ),
                    str(audio.resolve()),
                ),
            )
            connection.commit()
        finally:
            connection.close()

        self.assertEqual(analysis_scope_preview(self.db)["assets"], 5)
        self.assertEqual(
            analysis_scope_preview(self.db, scope_kind="visual")["assets"],
            2,
        )
        self.assertEqual(
            analysis_scope_preview(self.db, scope_kind="raw")["assets"],
            1,
        )
        self.assertEqual(
            analysis_scope_preview(self.db, scope_kind="audio")["assets"],
            1,
        )
        self.assertEqual(
            analysis_scope_preview(self.db, scope_kind="other")["assets"],
            2,
        )

        job_id = create_local_analysis_job(
            self.db,
            model="fixture-model",
            scope_kind="audio",
        )
        connection = sqlite3.connect(self.db)
        try:
            rows = connection.execute(
                """
                SELECT source_path FROM local_analysis_items
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(rows, [(str(audio.resolve()),)])

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
        project_files = [
            self.sources / "edit.prproj",
            self.sources / "graphics.aep",
            self.sources / "graphics-text.aepx",
        ]
        for project_file in project_files:
            project_file.write_bytes(b"editable production project fixture")
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
        for project_file in project_files:
            catalog_file(
                project_file,
                self.db,
                stability_seconds=0,
                include_media_probe=False,
                include_thumbnail_generation=False,
            )
        preview = analysis_scope_preview(self.db)
        self.assertEqual(preview["assets"], 2)
        job_id = create_local_analysis_job(self.db, model="fixture-model")
        connection = sqlite3.connect(self.db)
        try:
            job_paths = [
                row[0]
                for row in connection.execute(
                    """
                    SELECT source_path FROM local_analysis_items
                    WHERE job_id=? ORDER BY source_path
                    """,
                    (job_id,),
                )
            ]
        finally:
            connection.close()
        self.assertEqual(
            {Path(path).suffix.lower() for path in job_paths},
            {".txt"},
        )

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
            color = "#212121" if destination.suffix == ".jpg" else "#A36B35"
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
        retry_messages = request.call_args_list[1].args[2]["messages"]
        self.assertEqual(
            request.call_args_list[1].args[2]["options"]["num_ctx"],
            32768,
        )
        self.assertEqual(retry_messages[-2]["role"], "assistant")
        self.assertEqual(retry_messages[-2]["content"], "{not-json")
        self.assertIn("Correct your own output", retry_messages[-1]["content"])

    def test_abstract_visual_content_is_reinforced_on_retry(self) -> None:
        source = self.sources / "abstract.jpg"
        source.write_bytes(b"source fixture")
        thumbnail = self.root / "abstract-frame.jpg"
        Image.new("RGB", (80, 48), "#392B6E").save(thumbnail)
        unreadable = {
            "title": "Unreadable Visual",
            "description": "The supplied image was treated as unreadable.",
            "content_observations": ["No subject was recognized."],
            "evidence_mode": "unreadable",
            "media_category": "abstract",
            "tags": ["abstract"],
            "privacy_flags": [],
            "organization_suggestion": "Projects/Abstract",
            "stock_metadata": {},
            "confidence": 0.3,
        }
        valid = {
            **unreadable,
            "title": "Abstract Violet Light",
            "description": "Abstract violet forms and soft light fill the frame.",
            "content_observations": [
                "Soft violet forms create a dark abstract composition."
            ],
            "evidence_mode": "visual_content",
            "confidence": 0.7,
        }
        with patch(
            "beacon.local_analysis._request_json",
            side_effect=[
                {"message": {"content": json.dumps(unreadable)}},
                {"message": {"content": json.dumps(valid)}},
            ],
        ) as request:
            result = _default_analyzer(
                "http://127.0.0.1:11434",
                "fixture-model",
                {
                    "source_path": str(source),
                    "media_metadata": {"beacon_kind": "image"},
                    "thumbnail_path": str(thumbnail),
                    "size_bytes": source.stat().st_size,
                },
            )

        self.assertEqual(result["evidence_mode"], "visual_content")
        retry_system_prompt = request.call_args_list[1].args[2]["messages"][0][
            "content"
        ]
        self.assertIn(
            "Abstract, dark, blurred, defocused, or textural imagery",
            retry_system_prompt,
        )

    def test_audio_spectrogram_is_not_labeled_as_visual_evidence(self) -> None:
        source = self.sources / "black-with-audio.mp4"
        source.write_bytes(b"source fixture")
        temporary_root = self.root / "audio-context"
        temporary_root.mkdir()
        spectrum = temporary_root / "audio-spectrum.png"
        Image.new("RGB", (64, 48), "#A36B35").save(spectrum)
        valid = {
            "title": "Audio Content",
            "description": "Audio-derived content from the supplied evidence.",
            "content_observations": ["The audio spectrum contains changing energy."],
            "evidence_mode": "audio_content",
            "media_category": "audio",
            "tags": ["audio"],
            "privacy_flags": [],
            "organization_suggestion": "Audio",
            "stock_metadata": {},
            "confidence": 0.7,
        }
        context = {
            "expected_evidence_mode": "audio_content",
            "spectrogram": "full-file local frequency/time visualization",
        }
        with (
            patch(
                "beacon.local_analysis._prepare_media_context",
                return_value=(context, [spectrum], temporary_root),
            ),
            patch(
                "beacon.local_analysis._request_json",
                return_value={"message": {"content": json.dumps(valid)}},
            ) as request,
        ):
            result = _default_analyzer(
                "http://127.0.0.1:11434",
                "fixture-model",
                {
                    "source_path": str(source),
                    "media_metadata": {
                        "streams": [
                            {"codec_type": "video"},
                            {"codec_type": "audio"},
                        ]
                    },
                    "thumbnail_path": "",
                    "size_bytes": source.stat().st_size,
                },
            )

        self.assertEqual(result["evidence_mode"], "audio_content")
        user_context = json.loads(
            request.call_args.args[2]["messages"][1]["content"]
        )["local_media_context"]
        self.assertFalse(user_context["visual_evidence_supplied"])
        self.assertTrue(user_context["supplemental_image_evidence_supplied"])

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

    def test_catalog_drift_fails_one_item_without_aborting_the_batch(
        self,
    ) -> None:
        job_id = create_local_analysis_job(self.db, model="fixture-model")
        connection = sqlite3.connect(self.db)
        try:
            drifted_item_id, drifted_asset_id = connection.execute(
                """
                SELECT id,asset_id FROM local_analysis_items
                WHERE job_id=? ORDER BY source_path COLLATE NOCASE LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            connection.execute(
                "UPDATE assets SET sha256=? WHERE id=?",
                ("0" * 64, drifted_asset_id),
            )
            connection.commit()
        finally:
            connection.close()

        result = run_local_analysis_job(
            self.db, job_id, analyzer=self._analyzer
        )

        self.assertEqual(result.state, "partial")
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.completed, 1)
        connection = sqlite3.connect(self.db)
        try:
            state, error = connection.execute(
                "SELECT state,error FROM local_analysis_items WHERE id=?",
                (drifted_item_id,),
            ).fetchone()
            self.assertEqual(state, "failed")
            self.assertIn("catalog checksum changed", error or "")
            remaining = connection.execute(
                """
                SELECT state FROM local_analysis_items
                WHERE job_id=? AND id<>?
                """,
                (job_id, drifted_item_id),
            ).fetchall()
            self.assertEqual([row[0] for row in remaining], ["complete"])
            job_state, worker_pid, stage = connection.execute(
                """
                SELECT state,worker_pid,current_stage
                FROM local_analysis_jobs WHERE id=?
                """,
                (job_id,),
            ).fetchone()
            self.assertEqual(job_state, "partial")
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

    def test_placement_failure_is_durable_and_does_not_block_analysis(self) -> None:
        job_id = create_local_analysis_job(self.db, model="fixture-model")

        with (
            patch(
                "beacon.local_analysis.analysis_placement_for",
                return_value=SimpleNamespace(
                    destination_directory=projects_root() / "project_alpha" / "blocked"
                ),
            ),
            patch(
                "beacon.local_analysis.commit_analyzed_file",
                side_effect=PermissionError(
                    errno.EACCES,
                    "synthetic destination access denied",
                ),
            ) as commit,
        ):
            result = run_local_analysis_job(
                self.db,
                job_id,
                analyzer=self._analyzer,
            )

        self.assertEqual(commit.call_count, 1)
        self.assertEqual(result.state, "complete")
        self.assertEqual(result.completed, 2)
        self.assertEqual(result.failed, 0)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM asset_metadata_revisions"
                ).fetchone()[0],
                2,
            )
            subject, kind, priority = connection.execute(
                """
                SELECT subject,kind,priority FROM beacon_threads
                WHERE seed_key LIKE 'analysis-placement-error:%'
                """
            ).fetchone()
            self.assertEqual(subject, "Beacon could not place an analyzed file")
            self.assertEqual(kind, "blocker")
            self.assertEqual(priority, "important")
            placement_failures = connection.execute(
                """
                SELECT COUNT(*) FROM system_events
                WHERE kind='local_analysis_placement' AND state='failed'
                """
            ).fetchone()[0]
            self.assertEqual(placement_failures, 1)
            event_details = json.loads(
                connection.execute(
                    """
                    SELECT details_json FROM system_events
                    WHERE kind='local_analysis_job' AND state='complete'
                    ORDER BY created_at DESC LIMIT 1
                    """
                ).fetchone()[0]
            )
            self.assertEqual(event_details["placement_failures"], 1)
            self.assertEqual(event_details["deferred_placements"], 1)
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

    def test_selected_production_project_is_excluded_without_model_call(
        self,
    ) -> None:
        project = self.sources / "edit.prproj"
        project.write_bytes(b"editable production project fixture")
        cataloged = catalog_file(
            project,
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

        analyzer = patch("beacon.local_analysis._default_analyzer")
        with analyzer as mocked:
            result = run_local_analysis_job(self.db, job_id)

        mocked.assert_not_called()
        self.assertEqual(result.state, "complete")
        self.assertEqual(result.completed, 0)
        self.assertEqual(result.excluded, 1)
        self.assertEqual(result.failed, 0)

    def test_selected_empty_file_is_excluded_without_model_call(self) -> None:
        empty = self.sources / "empty.dat"
        empty.write_bytes(b"")
        cataloged = catalog_file(
            empty,
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

        analyzer = patch("beacon.local_analysis._default_analyzer")
        with analyzer as mocked:
            result = run_local_analysis_job(self.db, job_id)

        mocked.assert_not_called()
        self.assertEqual(result.state, "complete")
        self.assertEqual(result.completed, 0)
        self.assertEqual(result.excluded, 1)
        self.assertEqual(result.failed, 0)
        connection = sqlite3.connect(self.db)
        try:
            reason = connection.execute(
                """
                SELECT excluded_reason FROM local_analysis_items
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()[0]
            self.assertIn("empty file", reason.lower())
        finally:
            connection.close()

    def test_empty_file_exclusion_requires_current_checksum_identity(self) -> None:
        source = self.sources / "changed-empty.dat"
        source.write_bytes(b"")
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
        source.write_bytes(b"content arrived after the analysis snapshot")

        analyzer = patch("beacon.local_analysis._default_analyzer")
        with analyzer as mocked:
            result = run_local_analysis_job(self.db, job_id)

        mocked.assert_not_called()
        self.assertEqual(result.state, "failed")
        self.assertEqual(result.excluded, 0)
        self.assertEqual(result.failed, 1)

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


class CompanionExclusionScopeTests(unittest.TestCase):
    """Non-media companions leave analysis scope as exclusions, not failures.

    In the monitored retry, 51 of 80 items were these extensions, re-queued to
    fail again at 150-250ms each purely to record a failure they can never
    avoid.
    """

    def test_camera_index_and_editor_index_are_companions(self) -> None:
        for suffix in sorted(NON_CONTENT_COMPANION_EXTENSIONS):
            with self.subTest(suffix=suffix):
                reason = _artifact_exclusion_reason(str(Path("clips") / f"CLIP001{suffix}"))
                self.assertIsNotNone(reason)
                self.assertIn("cataloged and searchable", reason)

    def test_presentation_document_has_its_own_deferred_reason(self) -> None:
        companion = _artifact_exclusion_reason(str(Path("clips") / "CLIP001.mif"))
        document = _artifact_exclusion_reason(str(Path("decks") / "pitch.key"))

        self.assertIsNotNone(document)
        self.assertIn("text extraction", document)
        self.assertNotEqual(
            companion,
            document,
            "a future text path must be able to select these with one query",
        )

    def test_deferred_documents_are_a_named_constant(self) -> None:
        self.assertIn(".key", DEFERRED_DOCUMENT_EXTENSIONS)
        self.assertFalse(
            NON_CONTENT_COMPANION_EXTENSIONS & DEFERRED_DOCUMENT_EXTENSIONS
        )

    def test_nothing_else_is_excluded(self) -> None:
        for suffix in (".mp4", ".mov", ".jpg", ".heic", ".wav", ".txt", ".png"):
            with self.subTest(suffix=suffix):
                self.assertIsNone(
                    _artifact_exclusion_reason(str(Path("media") / f"asset{suffix}"))
                )

    def test_exclusion_records_complete_with_a_companion_marker(self) -> None:
        """excluded_reason IS NOT NULL is how companions are selected."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "runtime" / "beacon.db"
            source = root / "clips" / "A.mif"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"synthetic camera media index")
            catalog_file(
                source, db, stability_seconds=0, include_media_probe=False
            )

            with connect(db) as connection:
                asset_id = connection.execute(
                    "SELECT id FROM assets LIMIT 1"
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO local_analysis_jobs "
                    "(id,state,model,endpoint,policy_version,scope_sha256,"
                    "total_items,requested_by,created_at,updated_at) VALUES "
                    "('job','running','m','http://localhost:11434','v','s',1,"
                    "'test','2026-01-01T00:00:00+00:00',"
                    "'2026-01-01T00:00:00+00:00')"
                )
                connection.execute(
                    "INSERT INTO local_analysis_items "
                    "(id,job_id,asset_id,source_sha256,source_path,state,"
                    "attempts) VALUES ('item','job',?,'sha',?,'failed',1)",
                    (asset_id, str(source)),
                )

            reason = _artifact_exclusion_reason(str(source))
            _complete_analysis_exclusion(db, "item", reason)

            with connect(db) as connection:
                row = connection.execute(
                    "SELECT state, error, excluded_reason FROM "
                    "local_analysis_items WHERE id='item'"
                ).fetchone()

            self.assertEqual(row["state"], "complete")
            self.assertIsNone(row["error"])
            self.assertIsNotNone(row["excluded_reason"])


class ScopedAnalysisEnrolmentTests(unittest.TestCase):
    """A path prefix and an artifacts-only scope confine what a job enrols.

    Fixtures are synthetic per AGENTS.md section 3: these names could not
    occur in a real archive, and everything lives under a temporary
    directory.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "runtime" / "beacon.db"
        self.inside = self.root / "fixture_client_a" / "project_alpha"
        self.outside = self.root / "fixture_client_b" / "project_beta"
        # A directory whose name ends in ".prv" is the generated preview
        # cache the 0.22.11 rule was written to catch.
        self.cache_dir = self.inside / "project_alpha.prv"
        for directory in (self.inside, self.outside, self.cache_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.media_inside = self.inside / "SAMPLE_0001.mov"
        self.media_outside = self.outside / "SAMPLE_0002.mov"
        self.cache_render = self.cache_dir / "SAMPLE_0001_preview.mov"
        self.cache_sidecar = self.inside / "SAMPLE_0001.cfa"
        self.catalogued = (
            self.media_inside,
            self.media_outside,
            self.cache_render,
            self.cache_sidecar,
        )
        for index, source in enumerate(self.catalogued):
            source.write_bytes(f"synthetic fixture bytes {index}".encode())
            catalog_file(
                source,
                self.db,
                stability_seconds=0,
                include_media_probe=False,
                include_thumbnail_generation=False,
            )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _enrolled(self, job_id: str) -> set[str]:
        with connect(self.db) as connection:
            return {
                str(row["source_path"]).casefold()
                for row in connection.execute(
                    "SELECT source_path FROM local_analysis_items WHERE job_id=?",
                    (job_id,),
                )
            }

    def _resolved(self, source: Path) -> str:
        return str(source.resolve()).casefold()

    # ---- group 1: the path prefix -------------------------------------

    def test_path_prefix_enrols_only_assets_beneath_it(self) -> None:
        job_id = create_local_analysis_job(
            self.db,
            model="fixture-model",
            path_prefix=str(self.inside.resolve()),
        )

        enrolled = self._enrolled(job_id)
        self.assertIn(self._resolved(self.media_inside), enrolled)
        self.assertNotIn(self._resolved(self.media_outside), enrolled)

    def test_path_prefix_matching_is_case_insensitive(self) -> None:
        lowered = create_local_analysis_job(
            self.db,
            model="fixture-model",
            path_prefix=str(self.inside.resolve()).lower(),
        )
        uppered = create_local_analysis_job(
            self.db,
            model="fixture-model",
            path_prefix=str(self.inside.resolve()).upper(),
        )

        self.assertEqual(self._enrolled(lowered), self._enrolled(uppered))
        self.assertIn(self._resolved(self.media_inside), self._enrolled(uppered))

    def test_trailing_separator_on_the_prefix_changes_nothing(self) -> None:
        bare = analysis_scope_preview(
            self.db, path_prefix=str(self.inside.resolve())
        )
        trailing = analysis_scope_preview(
            self.db, path_prefix=str(self.inside.resolve()) + os.sep
        )

        self.assertEqual(bare["assets"], trailing["assets"])
        self.assertEqual(bare["scope_sha256"], trailing["scope_sha256"])
        self.assertEqual(bare["assets"], 1)

    def test_blank_prefix_is_the_same_as_no_prefix(self) -> None:
        self.assertEqual(
            analysis_scope_preview(self.db)["scope_sha256"],
            analysis_scope_preview(self.db, path_prefix="   ")["scope_sha256"],
        )

    def test_prefix_composes_with_an_existing_scope_kind(self) -> None:
        job_id = create_local_analysis_job(
            self.db,
            model="fixture-model",
            scope_kind="other",
            path_prefix=str(self.inside.resolve()),
        )

        self.assertEqual(
            self._enrolled(job_id), {self._resolved(self.media_inside)}
        )

    # ---- group 2: the artifacts scope kind -----------------------------

    def test_artifacts_scope_enrols_only_generated_cache(self) -> None:
        job_id = create_local_analysis_job(
            self.db, model="fixture-model", scope_kind="artifacts"
        )

        self.assertEqual(
            self._enrolled(job_id),
            {
                self._resolved(self.cache_render),
                self._resolved(self.cache_sidecar),
            },
        )

    def test_artifacts_scope_matches_the_repository_rule(self) -> None:
        preview = analysis_scope_preview(self.db, scope_kind="artifacts")

        self.assertEqual(preview["assets"], 2)
        self.assertTrue(is_hidden_support_path(self.cache_render))
        self.assertTrue(is_hidden_support_path(self.cache_sidecar))
        self.assertFalse(is_hidden_support_path(self.media_inside))

    def test_artifacts_scope_composes_with_the_path_prefix(self) -> None:
        confined = analysis_scope_preview(
            self.db,
            scope_kind="artifacts",
            path_prefix=str(self.outside.resolve()),
        )

        self.assertEqual(confined["assets"], 0)

    def test_artifacts_is_a_recognized_scope_kind(self) -> None:
        self.assertIn("artifacts", ANALYSIS_SCOPE_KINDS)
        with self.assertRaises(ValueError):
            analysis_scope_preview(self.db, scope_kind="not-a-scope")

    # ---- group 4: no regression on the existing scope kinds ------------

    def test_existing_scope_kinds_are_unchanged(self) -> None:
        previews = analysis_scope_previews(self.db)

        # The two .mov files are the only content-bearing assets; the cache
        # render and the .cfa sidecar stay outside every content scope.
        self.assertEqual(previews["all"]["assets"], 2)
        self.assertEqual(previews["other"]["assets"], 2)
        self.assertEqual(previews["visual"]["assets"], 0)
        self.assertEqual(previews["audio"]["assets"], 0)
        self.assertEqual(previews["raw"]["assets"], 0)
        self.assertEqual(previews["artifacts"]["assets"], 2)

    def test_default_job_creation_is_unchanged(self) -> None:
        job_id = create_local_analysis_job(self.db, model="fixture-model")

        self.assertEqual(
            self._enrolled(job_id),
            {
                self._resolved(self.media_inside),
                self._resolved(self.media_outside),
            },
        )

    def test_scope_kind_and_prefix_are_recorded_on_the_job(self) -> None:
        job_id = create_local_analysis_job(
            self.db,
            model="fixture-model",
            scope_kind="artifacts",
            path_prefix=str(self.inside.resolve()),
        )

        with connect(self.db) as connection:
            row = connection.execute(
                "SELECT scope_kind,scope_path_prefix FROM local_analysis_jobs "
                "WHERE id=?",
                (job_id,),
            ).fetchone()

        self.assertEqual(row["scope_kind"], "artifacts")
        self.assertEqual(
            row["scope_path_prefix"], str(self.inside.resolve())
        )


class ArtifactsPlacementGuardTests(unittest.TestCase):
    """An artifacts job must reach neither movement site in a run.

    There are two: the managed placement of each analyzed candidate, and the
    Inbox-wide companion sweep that follows it. The sweep takes only a
    db_path, so it is not scoped to the job at all and would move the very
    files the job just declined to place.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "runtime" / "beacon.db"
        self.project = self.root / "fixture_client_a" / "project_alpha"
        self.cache_dir = self.project / "project_alpha.prv"
        self.cache_dir.mkdir(parents=True)
        self.media = self.project / "SAMPLE_0001.mov"
        self.cache_render = self.cache_dir / "SAMPLE_0001_preview.mov"
        for index, source in enumerate((self.media, self.cache_render)):
            source.write_bytes(f"synthetic fixture bytes {index}".encode())
            catalog_file(
                source,
                self.db,
                stability_seconds=0,
                include_media_probe=False,
                include_thumbnail_generation=False,
            )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _analyzer(endpoint: str, model: str, asset: dict[str, object]) -> dict:
        return {
            "title": Path(str(asset["source_path"])).stem.title(),
            "description": "Candidate derived from verified local context.",
            "content_observations": [
                "The bounded fixture contains locally verified content."
            ],
            "evidence_mode": "text_content",
            "media_category": "text fixture",
            "tags": ["local", "fixture"],
            "privacy_flags": ["none detected from bounded context"],
            "organization_suggestion": "Leave in test scope; no move authorized.",
            "confidence": 0.8,
        }

    def test_artifacts_job_calls_neither_movement_site(self) -> None:
        """THE guard test: cache and real media in range, nothing moves."""
        job_id = create_local_analysis_job(
            self.db, model="fixture-model", scope_kind="artifacts"
        )

        with connect(self.db) as connection:
            enrolled = [
                str(row["source_path"])
                for row in connection.execute(
                    "SELECT source_path FROM local_analysis_items WHERE job_id=?",
                    (job_id,),
                )
            ]
        # Only the cache item is enrolled, though both sit in range.
        self.assertEqual(
            [Path(path).name for path in enrolled],
            ["SAMPLE_0001_preview.mov"],
        )

        with (
            patch(
                "beacon.local_analysis.commit_analyzed_file"
            ) as commit_mock,
            patch(
                "beacon.local_analysis.archive_contextual_inbox_companions"
            ) as sweep_mock,
        ):
            result = run_local_analysis_job(
                self.db, job_id, analyzer=self._analyzer
            )

        self.assertEqual(commit_mock.call_count, 0)
        self.assertEqual(sweep_mock.call_count, 0)
        self.assertEqual(result.state, "complete")
        self.assertEqual(result.excluded, 1)
        self.assertTrue(self.media.exists())
        self.assertTrue(self.cache_render.exists())

    def test_the_guard_is_recorded_in_the_audit_trail(self) -> None:
        job_id = create_local_analysis_job(
            self.db, model="fixture-model", scope_kind="artifacts"
        )

        with (
            patch("beacon.local_analysis.commit_analyzed_file"),
            patch("beacon.local_analysis.archive_contextual_inbox_companions"),
        ):
            run_local_analysis_job(self.db, job_id, analyzer=self._analyzer)

        with connect(self.db) as connection:
            guard_events = connection.execute(
                "SELECT details_json FROM system_events WHERE kind=?",
                ("local_analysis_placement_guard",),
            ).fetchall()

        self.assertEqual(len(guard_events), 1)
        details = json.loads(guard_events[0]["details_json"])
        self.assertEqual(details["scope_kind"], "artifacts")
        self.assertTrue(details["companion_sweep_skipped"])

    def test_a_content_job_still_reaches_both_movement_sites(self) -> None:
        """The guard discriminates; it is not a blanket disable."""
        job_id = create_local_analysis_job(
            self.db, model="fixture-model", scope_kind="all"
        )

        with (
            patch(
                "beacon.local_analysis.commit_analyzed_file",
                return_value=(None, "fixture placement declined"),
            ) as commit_mock,
            patch(
                "beacon.local_analysis.archive_contextual_inbox_companions",
                return_value=SimpleNamespace(moved=0, skipped=0, failed=0),
            ) as sweep_mock,
            patch(
                "beacon.local_analysis.placement_needs_clarification",
                return_value=False,
            ),
        ):
            run_local_analysis_job(self.db, job_id, analyzer=self._analyzer)

        self.assertEqual(commit_mock.call_count, 1)
        self.assertEqual(sweep_mock.call_count, 1)

    def test_job_may_place_is_the_single_authority(self) -> None:
        """Both call sites read this one answer, so unit-test it directly."""
        self.assertFalse(job_may_place({"scope_kind": "artifacts"}))
        for scope_kind in ("all", "visual", "audio", "other", "raw"):
            with self.subTest(scope_kind=scope_kind):
                self.assertTrue(job_may_place({"scope_kind": scope_kind}))
        # A job row written before schema 17 carries no scope kind, and the
        # placement-free scope did not exist then, so it keeps placing.
        self.assertTrue(job_may_place({}))
        self.assertTrue(job_may_place({"scope_kind": None}))

    def test_generated_artifacts_are_never_placed_even_if_enrolled(
        self,
    ) -> None:
        """The second layer, independent of the job's scope kind.

        Simulates the exclusion rule failing to catch a cache file: the item
        becomes a published candidate inside a placement-allowed job, and the
        per-item guard must still refuse to move it.
        """
        job_id = create_local_analysis_job(
            self.db, model="fixture-model", scope_kind="all"
        )
        with connect(self.db) as connection:
            asset_id, sha256 = connection.execute(
                "SELECT asset_id,sha256 FROM locations "
                "JOIN assets ON assets.id=locations.asset_id WHERE path=?",
                (str(self.cache_render.resolve()),),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO local_analysis_items(
                    id,job_id,asset_id,source_sha256,source_path,state
                ) VALUES ('forced-cache-item', ?, ?, ?, ?, 'pending')
                """,
                (job_id, asset_id, sha256, str(self.cache_render.resolve())),
            )

        with (
            patch(
                "beacon.local_analysis._artifact_exclusion_reason",
                return_value=None,
            ),
            patch(
                "beacon.local_analysis.commit_analyzed_file",
                return_value=(None, "fixture placement declined"),
            ) as commit_mock,
            patch(
                "beacon.local_analysis.archive_contextual_inbox_companions",
                return_value=SimpleNamespace(moved=0, skipped=0, failed=0),
            ),
            patch(
                "beacon.local_analysis.placement_needs_clarification",
                return_value=False,
            ),
        ):
            run_local_analysis_job(self.db, job_id, analyzer=self._analyzer)

        placed = {
            Path(str(call.kwargs["source_path"])).name
            for call in commit_mock.call_args_list
        }
        self.assertEqual(placed, {"SAMPLE_0001.mov"})
        self.assertNotIn("SAMPLE_0001_preview.mov", placed)
