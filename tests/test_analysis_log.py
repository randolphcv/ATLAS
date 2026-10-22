"""The analysis log and the error field may hold structure and nothing else.

AGENTS.md section 7: record what was proven -- counts, states, durations,
error classes, job outcomes -- never which specific files proved it. Two
defects sat on the wrong side of that line. The application log recorded
nothing at all about analysis, so an eight-hour stall had to be diagnosed from
the catalog. And an item's ``error`` field was written as the string of a
``FileNotFoundError`` raised with a bare path, so the audit trail read as a
deployment path with no explanation.

These tests hold ``beacon.analysis_log`` to its guarantee. Every fixture path
here is assembled from fragments, because a test that writes a path shape into
the repository in order to prove paths are stripped would be the defect it is
testing for. The separator and drive-letter assertions are the load-bearing
ones: they are what makes the guarantee mechanical rather than a convention
each call site has to remember.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from beacon import analysis_log
from beacon.catalog import catalog_file
from beacon.local_analysis import (
    LOCAL_RESPONSE_ATTEMPTS,
    _default_analyzer,
    create_local_analysis_job,
    recover_local_analysis_jobs,
    retry_local_analysis_failures,
    run_local_analysis_job,
)

# Path shapes, assembled rather than written. ``instance-terms`` and the
# structural detectors in tests/test_no_instance_data.py both read this file.
SEPARATOR = "\\"
POSIX_SEPARATOR = "/"
DRIVE_PREFIX = "Q" + ":" + SEPARATOR
WINDOWS_PATH = (
    DRIVE_PREFIX
    + "fixture_archive"
    + SEPARATOR
    + "inbox"
    + SEPARATOR
    + "fixture_client_a"
    + SEPARATOR
    + "SAMPLE_0001.CR3"
)
POSIX_PATH = POSIX_SEPARATOR.join(
    ("", "fixture_pool", "inbox", "project_alpha", "SAMPLE_0002.mp4")
)

DRIVE_SHAPE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:")

TRUNCATED_JSON_MESSAGE = (
    "local model failed content validation after three attempts: "
    "Unterminated string starting at: line 1 column 1114 (char 1113)"
)

CAMERA_INDEX_EXCLUSION = (
    "Excluded camera metadata or generated editor index from contextual "
    "content inference; the file remains cataloged and searchable."
)


class StructuralAssertions(unittest.TestCase):
    """Shared check. Every string this module produces must pass it."""

    def assertStructural(self, text: str) -> None:
        self.assertNotIn(
            SEPARATOR,
            text,
            "A recorded string carries a path separator. Section 7 permits "
            f"classes and counts, not locations: {text!r}",
        )
        self.assertNotIn(
            POSIX_SEPARATOR,
            text,
            "A recorded string carries a path separator. Section 7 permits "
            f"classes and counts, not locations: {text!r}",
        )
        self.assertIsNone(
            DRIVE_SHAPE.search(text),
            "A recorded string carries a drive-letter prefix, which names "
            f"one deployment's volume: {text!r}",
        )


class RedactionTests(StructuralAssertions):
    """The mechanical half. Exception text is not ours to trust."""

    def test_windows_path_leaves_nothing_behind(self) -> None:
        redacted = analysis_log.redact(WINDOWS_PATH)
        self.assertStructural(redacted)
        self.assertNotIn("SAMPLE_0001", redacted)
        self.assertNotIn("fixture_client_a", redacted)

    def test_posix_path_leaves_nothing_behind(self) -> None:
        redacted = analysis_log.redact(POSIX_PATH)
        self.assertStructural(redacted)
        self.assertNotIn("project_alpha", redacted)

    def test_path_embedded_in_prose_is_replaced_and_prose_survives(
        self,
    ) -> None:
        redacted = analysis_log.redact(
            f"could not open {WINDOWS_PATH} for reading"
        )
        self.assertStructural(redacted)
        self.assertIn("could not open", redacted)
        self.assertIn("for reading", redacted)
        self.assertNotIn("SAMPLE_0001", redacted)

    def test_bare_drive_letter_is_replaced(self) -> None:
        self.assertStructural(analysis_log.redact("the volume " + "Q" + ":"))

    def test_diagnostic_prose_survives_intact(self) -> None:
        """The detail that made one diagnosis possible carries no location."""
        self.assertEqual(
            analysis_log.redact(TRUNCATED_JSON_MESSAGE),
            TRUNCATED_JSON_MESSAGE,
        )

    def test_redaction_accepts_a_non_string(self) -> None:
        self.assertStructural(analysis_log.redact(FileNotFoundError(POSIX_PATH)))


class SizeClassTests(unittest.TestCase):
    """Bytes are instance data at full precision, structural once bucketed."""

    def test_each_bucket(self) -> None:
        self.assertEqual(analysis_log.size_class(0), "empty")
        self.assertEqual(analysis_log.size_class(900), "tiny")
        self.assertEqual(analysis_log.size_class(900_000), "small")
        self.assertEqual(analysis_log.size_class(90_000_000), "medium")
        self.assertEqual(analysis_log.size_class(900_000_000), "large")
        self.assertEqual(analysis_log.size_class(9_000_000_000), "very_large")

    def test_absent_or_unusable_size_is_unknown_not_an_error(self) -> None:
        for value in (None, "", "not a number", -1, object()):
            self.assertEqual(analysis_log.size_class(value), "unknown")


class ExtensionLabelTests(StructuralAssertions):
    """The suffix is permitted. The rest of the path is not."""

    def test_suffix_is_taken_and_lowercased(self) -> None:
        self.assertEqual(analysis_log.extension_label(WINDOWS_PATH), ".cr3")
        self.assertEqual(analysis_log.extension_label(POSIX_PATH), ".mp4")

    def test_label_never_carries_the_rest_of_the_path(self) -> None:
        for path in (WINDOWS_PATH, POSIX_PATH):
            self.assertStructural(analysis_log.extension_label(path))

    def test_file_without_a_suffix_reports_none(self) -> None:
        self.assertEqual(
            analysis_log.extension_label(
                POSIX_SEPARATOR.join(("", "fixture_pool", "NOTICE"))
            ),
            "none",
        )

    def test_absent_source_reports_none(self) -> None:
        self.assertEqual(analysis_log.extension_label(None), "none")


class ReasonClassTests(unittest.TestCase):
    """A class, always. Never an occurrence."""

    def test_missing_source_is_its_own_class(self) -> None:
        self.assertEqual(
            analysis_log.reason_class(FileNotFoundError(WINDOWS_PATH)),
            "source_missing",
        )

    def test_catalog_drift_keeps_the_class_the_existing_guard_expects(
        self,
    ) -> None:
        self.assertEqual(
            analysis_log.reason_class(
                ValueError("catalog checksum changed for " + "a" * 64)
            ),
            "catalog_identity_changed",
        )

    def test_changed_source_bytes(self) -> None:
        self.assertEqual(
            analysis_log.reason_class(
                ValueError("source bytes changed since cataloging")
            ),
            "source_bytes_changed",
        )

    def test_truncated_model_output(self) -> None:
        self.assertEqual(
            analysis_log.reason_class(ValueError(TRUNCATED_JSON_MESSAGE)),
            "model_output_invalid",
        )
        self.assertEqual(
            analysis_log.reason_class(
                json.JSONDecodeError("Unterminated string", "{", 0)
            ),
            "model_output_invalid",
        )

    def test_unreachable_endpoint(self) -> None:
        self.assertEqual(
            analysis_log.reason_class(
                ConnectionError("local model endpoint unavailable")
            ),
            "model_endpoint_unavailable",
        )

    def test_unrecognised_failure_falls_back_to_its_type_name(self) -> None:
        """A class nobody mapped is still a class, and never a path."""
        self.assertEqual(
            analysis_log.reason_class(KeyError("nothing recognisable")),
            "key_error",
        )


class ExclusionClassTests(unittest.TestCase):
    """71 of the stalled job's 73 items were exclusions, all unlogged."""

    def test_each_rule_has_its_own_class(self) -> None:
        self.assertEqual(
            analysis_log.exclusion_class(CAMERA_INDEX_EXCLUSION),
            "camera_or_editor_index",
        )
        self.assertEqual(
            analysis_log.exclusion_class(
                "Excluded empty file from contextual content inference."
            ),
            "empty_file",
        )
        self.assertEqual(
            analysis_log.exclusion_class(
                "Excluded editable production project file from inference."
            ),
            "production_project_file",
        )
        self.assertEqual(
            analysis_log.exclusion_class(
                "Deferred presentation document pending text extraction."
            ),
            "document_text_extraction_deferred",
        )
        self.assertEqual(
            analysis_log.exclusion_class(
                "Excluded confidently generated cache, autosave, or sidecar "
                "artifact."
            ),
            "generated_artifact",
        )

    def test_unknown_reason_is_classified_rather_than_echoed(self) -> None:
        self.assertEqual(
            analysis_log.exclusion_class("a rule nobody has mapped yet"),
            "unclassified_rule",
        )


class StructuralErrorTests(StructuralAssertions):
    """Item 2. What an item's error field is allowed to hold."""

    def test_file_not_found_names_the_reason_and_the_extension(self) -> None:
        """The exact defect: the whole recorded error was a path.

        ``FileNotFoundError`` raised with a bare path has no prose to keep, so
        the reason class and its canned explanation are all the field can say.
        What matters is that it says something, and that the path is gone.
        """
        recorded = analysis_log.structural_error(
            FileNotFoundError(WINDOWS_PATH),
            source=WINDOWS_PATH,
            size_bytes=4096,
        )
        self.assertStructural(recorded)
        self.assertIn("source_missing", recorded)
        self.assertIn(".cr3", recorded)
        self.assertIn("size class small", recorded)
        self.assertNotIn("SAMPLE_0001", recorded)
        self.assertNotIn("fixture_client_a", recorded)
        self.assertNotEqual(recorded.strip(), "")

    def test_posix_file_not_found_is_equally_covered(self) -> None:
        recorded = analysis_log.structural_error(
            FileNotFoundError(POSIX_PATH),
            source=POSIX_PATH,
            size_bytes=0,
        )
        self.assertStructural(recorded)
        self.assertIn("source_missing", recorded)
        self.assertIn(".mp4", recorded)
        self.assertIn("size class empty", recorded)

    def test_prose_that_carries_no_location_is_kept(self) -> None:
        """Truncation detail is why one diagnosis was possible at all."""
        recorded = analysis_log.structural_error(
            ValueError(TRUNCATED_JSON_MESSAGE),
            source=POSIX_PATH,
            size_bytes=900,
        )
        self.assertStructural(recorded)
        self.assertIn("model_output_invalid", recorded)
        self.assertIn("column 1114", recorded)
        self.assertIn("size class tiny", recorded)

    def test_catalog_drift_message_survives_for_the_existing_guard(
        self,
    ) -> None:
        recorded = analysis_log.structural_error(
            ValueError("catalog checksum changed for " + "a" * 64),
            source=POSIX_PATH,
        )
        self.assertStructural(recorded)
        self.assertIn("catalog checksum changed", recorded)

    def test_a_path_inside_prose_is_stripped_and_the_prose_kept(self) -> None:
        recorded = analysis_log.structural_error(
            RuntimeError(f"derivative generation failed for {WINDOWS_PATH}"),
            source=WINDOWS_PATH,
            size_bytes=90_000_000,
        )
        self.assertStructural(recorded)
        self.assertIn("derivative generation failed", recorded)
        self.assertIn("size class medium", recorded)

    def test_prefix_is_redacted_like_everything_else(self) -> None:
        recorded = analysis_log.structural_error(
            ValueError("rejected"),
            source=POSIX_PATH,
            prefix=f"while finalizing {WINDOWS_PATH}:",
        )
        self.assertStructural(recorded)
        self.assertIn("while finalizing", recorded)

    def test_unknown_size_is_reported_rather_than_omitted(self) -> None:
        recorded = analysis_log.structural_error(
            ValueError("rejected"), source=POSIX_PATH
        )
        self.assertIn("size class unknown", recorded)

    def test_describing_a_failure_cannot_itself_fail(self) -> None:
        """This runs while recording a failure. It may not have one."""
        recorded = analysis_log.structural_error(
            _Hostile(), source=_Hostile(), size_bytes=_Hostile()
        )
        self.assertStructural(recorded)
        self.assertNotEqual(recorded.strip(), "")

    def test_field_is_bounded(self) -> None:
        recorded = analysis_log.structural_error(
            ValueError("x" * 50_000), source=POSIX_PATH
        )
        self.assertLessEqual(len(recorded), analysis_log.ERROR_FIELD_LIMIT)


class LoggedLine(StructuralAssertions):
    """Captures what the module writes, the way a log file would receive it."""

    def setUp(self) -> None:
        self.records: list[logging.LogRecord] = []
        self.handler = _Collector(self.records)
        analysis_log.LOGGER.addHandler(self.handler)
        self.previous_level = analysis_log.LOGGER.level
        self.previous_propagate = analysis_log.LOGGER.propagate
        analysis_log.LOGGER.setLevel(logging.INFO)
        analysis_log.LOGGER.propagate = False

    def tearDown(self) -> None:
        analysis_log.LOGGER.removeHandler(self.handler)
        analysis_log.LOGGER.setLevel(self.previous_level)
        analysis_log.LOGGER.propagate = self.previous_propagate

    def lines(self) -> list[str]:
        return [record.getMessage() for record in self.records]

    def only(self) -> str:
        self.assertEqual(len(self.records), 1, self.lines())
        return self.records[0].getMessage()

    def fields(self, line: str) -> dict[str, str]:
        tokens = line.split()
        return dict(
            token.split("=", 1) for token in tokens[1:] if "=" in token
        )


class _Collector(logging.Handler):
    def __init__(self, sink: list[logging.LogRecord]) -> None:
        super().__init__()
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self.sink.append(record)


class EventShapeTests(LoggedLine):
    """Item 1. Every event class, in structural form."""

    def test_job_lifecycle_events_carry_their_counts(self) -> None:
        analysis_log.job_created(
            "fixture-job", total_items=73, scope_kind="all",
            scoped_to_folder=False,
        )
        analysis_log.job_started("fixture-job", pending=73, total_items=73)
        analysis_log.job_paused(
            "fixture-job", pending=72, reason="worker released"
        )
        analysis_log.job_resumed("fixture-job", pending=72, total_items=73)
        analysis_log.job_finished(
            "fixture-job", state="partial", complete=0, failed=2,
            excluded=71, pending=0, duration_seconds=235.5,
        )
        lines = self.lines()
        self.assertEqual(
            [line.split()[0] for line in lines],
            [
                analysis_log.JOB_CREATED,
                analysis_log.JOB_STARTED,
                analysis_log.JOB_PAUSED,
                analysis_log.JOB_RESUMED,
                analysis_log.JOB_FINISHED,
            ],
        )
        created = self.fields(lines[0])
        self.assertEqual(created["items"], "73")
        self.assertEqual(created["scope"], "all")
        self.assertEqual(created["scoped_to_folder"], "false")
        finished = self.fields(lines[4])
        self.assertEqual(finished["state"], "partial")
        self.assertEqual(finished["excluded"], "71")
        self.assertEqual(finished["failed"], "2")
        self.assertEqual(finished["seconds"], "235.500")
        for line in lines:
            self.assertStructural(line)

    def test_item_outcomes_carry_class_extension_size_and_duration(
        self,
    ) -> None:
        analysis_log.item_complete(
            "fixture-job", source=POSIX_PATH, size_bytes=90_000_000,
            duration_seconds=12.5,
        )
        analysis_log.item_excluded(
            "fixture-job", source=WINDOWS_PATH,
            reason=CAMERA_INDEX_EXCLUSION, size_bytes=1200,
            duration_seconds=0.017,
        )
        analysis_log.item_failed(
            "fixture-job", error=FileNotFoundError(WINDOWS_PATH),
            source=WINDOWS_PATH, size_bytes=10, duration_seconds=0.007,
        )
        lines = self.lines()
        self.assertEqual(
            [line.split()[0] for line in lines],
            [
                analysis_log.ITEM_COMPLETE,
                analysis_log.ITEM_EXCLUDED,
                analysis_log.ITEM_FAILED,
            ],
        )
        complete = self.fields(lines[0])
        self.assertEqual(complete["extension"], ".mp4")
        self.assertEqual(complete["size"], "medium")
        self.assertEqual(complete["seconds"], "12.500")
        excluded = self.fields(lines[1])
        self.assertEqual(excluded["reason_class"], "camera_or_editor_index")
        failed = self.fields(lines[2])
        self.assertEqual(failed["reason_class"], "source_missing")
        self.assertEqual(failed["extension"], ".cr3")
        for line in lines:
            self.assertStructural(line)
            self.assertNotIn("SAMPLE_0001", line)
            self.assertNotIn("project_alpha", line)

    def test_model_attempts_carry_the_attempt_number_and_failure_class(
        self,
    ) -> None:
        analysis_log.model_attempt(
            "fixture-job", attempt=1, attempts_allowed=3, source=POSIX_PATH,
            failure=ValueError(TRUNCATED_JSON_MESSAGE),
            duration_seconds=77.25,
        )
        analysis_log.model_attempt(
            "fixture-job", attempt=2, attempts_allowed=3, source=POSIX_PATH,
            duration_seconds=80.0,
        )
        rejected, accepted = (self.fields(line) for line in self.lines())
        self.assertEqual(rejected["attempt"], "1")
        self.assertEqual(rejected["of"], "3")
        self.assertEqual(rejected["outcome"], "rejected")
        self.assertEqual(rejected["failure_class"], "model_output_invalid")
        self.assertEqual(accepted["attempt"], "2")
        self.assertEqual(accepted["outcome"], "accepted")
        self.assertNotIn("failure_class", accepted)
        for line in self.lines():
            self.assertStructural(line)

    def test_model_attempt_without_a_job_still_records_the_attempt(
        self,
    ) -> None:
        """A missing job id loses a correlation, not the event."""
        analysis_log.model_attempt(None, attempt=1, attempts_allowed=3)
        self.assertEqual(self.fields(self.only())["job"], "unknown")

    def test_no_event_carries_model_output(self) -> None:
        """Model prose is derivative content and is not a log value."""
        analysis_log.item_failed(
            "fixture-job",
            error=ValueError(
                "local model returned: a sunlit kitchen with a red kettle"
            ),
            source=POSIX_PATH,
        )
        line = self.only()
        self.assertNotIn("kettle", line)
        self.assertNotIn("sunlit", line)
        self.assertEqual(
            self.fields(line)["reason_class"], "model_output_invalid"
        )


class EmitterIsolationTests(LoggedLine):
    """Logging is bookkeeping about an item, never a reason it fails."""

    def test_an_unrenderable_value_does_not_raise(self) -> None:
        analysis_log.item_failed(
            "fixture-job", error=_Hostile(), source=_Hostile()
        )

    def test_a_handler_that_throws_does_not_reach_the_caller(self) -> None:
        analysis_log.LOGGER.addHandler(_Exploding())
        try:
            analysis_log.job_started("fixture-job", pending=1, total_items=1)
        finally:
            for handler in list(analysis_log.LOGGER.handlers):
                if isinstance(handler, _Exploding):
                    analysis_log.LOGGER.removeHandler(handler)


class _Hostile:
    """Stands in for anything whose text cannot be obtained."""

    def __str__(self) -> str:
        raise RuntimeError("this value refuses to render")

    __repr__ = __str__


class _Exploding(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        raise RuntimeError("this handler refuses to write")

    def handleError(self, record: logging.LogRecord) -> None:
        raise RuntimeError("this handler refuses to recover")


class FixtureJobLogTestCase(StructuralAssertions):
    """A real job, a temporary log file, and what the log then holds.

    The log file is a temporary one and never the deployment's runtime log:
    ``beacon.analysis`` gets a handler of its own here and ``propagate`` is
    switched off, so nothing reaches the root logger either. Fixtures live in
    a temporary directory, which is outside any configured Inbox, so the
    settle step this job performs finds no candidates and moves nothing.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "runtime" / "beacon.db"
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.log_path = self.root / "fixture-analysis.log"
        self.handler = logging.FileHandler(self.log_path, encoding="utf-8")
        self.handler.setFormatter(logging.Formatter("%(name)s %(message)s"))
        analysis_log.LOGGER.addHandler(self.handler)
        self.previous_level = analysis_log.LOGGER.level
        self.previous_propagate = analysis_log.LOGGER.propagate
        analysis_log.LOGGER.setLevel(logging.INFO)
        analysis_log.LOGGER.propagate = False

    def tearDown(self) -> None:
        analysis_log.LOGGER.removeHandler(self.handler)
        self.handler.close()
        analysis_log.LOGGER.setLevel(self.previous_level)
        analysis_log.LOGGER.propagate = self.previous_propagate
        self.temp.cleanup()

    def catalog(self, name: str, content: bytes) -> Path:
        source = self.sources / name
        source.write_bytes(content)
        catalog_file(
            source,
            self.db,
            stability_seconds=0,
            include_media_probe=False,
            include_thumbnail_generation=False,
        )
        return source

    def analyzer(
        self, endpoint: str, model: str, asset: dict[str, object]
    ) -> dict[str, object]:
        return {
            "title": "Synthetic Fixture",
            "description": "Candidate derived from verified local context.",
            "content_observations": [
                "The bounded text fixture contains locally verified content."
            ],
            "evidence_mode": "text_content",
            "media_category": "text fixture",
            "tags": ["local", "fixture"],
            "privacy_flags": ["none detected from bounded context"],
            "organization_suggestion": (
                "Leave in test scope; no move authorized."
            ),
            "confidence": 0.8,
        }

    def log_lines(self) -> list[str]:
        self.handler.flush()
        text = self.log_path.read_text(encoding="utf-8")
        return [line for line in text.splitlines() if line.strip()]

    def events(self) -> list[str]:
        """The event name of each line, which is its second token."""
        names = []
        for line in self.log_lines():
            tokens = line.split()
            if len(tokens) >= 2 and tokens[1] in analysis_log.EVENTS:
                names.append(tokens[1])
        return names

    def fields_for(self, event: str) -> list[dict[str, str]]:
        found = []
        for line in self.log_lines():
            tokens = line.split()
            if len(tokens) >= 2 and tokens[1] == event:
                found.append(
                    dict(
                        token.split("=", 1)
                        for token in tokens[2:]
                        if "=" in token
                    )
                )
        return found

    def assertLogIsStructural(self) -> None:
        for line in self.log_lines():
            self.assertStructural(line)


class FixtureJobEventsTests(FixtureJobLogTestCase):
    """Item 1, end to end. Every event class reaches the log."""

    def test_a_fixture_job_logs_every_event_class(self) -> None:
        analysed = self.catalog("fixture_sample_a.txt", b"synthetic content")
        self.catalog("fixture_index_a.mif", b"synthetic camera index")
        missing = self.catalog("fixture_absent_a.txt", b"synthetic missing")

        job_id = create_local_analysis_job(self.db, model="fixture-model")
        # Enrolment is a snapshot taken at creation, so removing the file now
        # reproduces the stale-row failure the diagnosis found: a row that
        # pointed at a location the Inbox drain had already emptied.
        missing.unlink()

        result = run_local_analysis_job(
            self.db, job_id, analyzer=self.analyzer
        )

        self.assertEqual(result.state, "partial")
        self.assertEqual(result.failed, 1)

        emitted = self.events()
        for event in (
            analysis_log.JOB_CREATED,
            analysis_log.JOB_STARTED,
            analysis_log.ITEM_COMPLETE,
            analysis_log.ITEM_EXCLUDED,
            analysis_log.ITEM_FAILED,
            analysis_log.JOB_FINISHED,
        ):
            self.assertIn(
                event,
                emitted,
                f"{event} never reached the log. The whole defect was a log "
                f"that recorded start, stop and cataloging only; emitted "
                f"{sorted(set(emitted))}",
            )

        [created] = self.fields_for(analysis_log.JOB_CREATED)
        self.assertEqual(created["job"], job_id)
        self.assertEqual(created["items"], "3")
        self.assertEqual(created["scope"], "all")
        self.assertEqual(created["scoped_to_folder"], "false")

        [started] = self.fields_for(analysis_log.JOB_STARTED)
        self.assertEqual(started["pending"], "3")
        self.assertEqual(started["items"], "3")

        [complete] = self.fields_for(analysis_log.ITEM_COMPLETE)
        self.assertEqual(complete["extension"], ".txt")
        self.assertEqual(complete["size"], "tiny")
        self.assertIn("seconds", complete)

        [excluded] = self.fields_for(analysis_log.ITEM_EXCLUDED)
        self.assertEqual(excluded["extension"], ".mif")
        self.assertEqual(excluded["reason_class"], "camera_or_editor_index")

        [failed] = self.fields_for(analysis_log.ITEM_FAILED)
        self.assertEqual(failed["extension"], ".txt")
        self.assertEqual(failed["reason_class"], "source_missing")

        [finished] = self.fields_for(analysis_log.JOB_FINISHED)
        self.assertEqual(finished["state"], "partial")
        self.assertEqual(finished["complete"], "1")
        self.assertEqual(finished["excluded"], "1")
        self.assertEqual(finished["failed"], "1")
        self.assertEqual(finished["pending"], "0")
        self.assertIn("seconds", finished)

        self.assertLogIsStructural()
        # The names are the fixtures'; none of them may appear.
        whole = "\n".join(self.log_lines())
        for name in ("fixture_sample_a", "fixture_index_a", "fixture_absent_a"):
            self.assertNotIn(name, whole)
        self.assertNotIn(str(analysed.parent), whole)

    def test_pause_and_resume_are_distinct_events(self) -> None:
        """Eight of the stall's eight hours were paused time, unlogged."""
        self.catalog("fixture_sample_b.txt", b"synthetic content b")
        job_id = create_local_analysis_job(self.db, model="fixture-model")

        # A job whose worker is gone. 2_147_483_647 is the pid the existing
        # liveness guard uses for "certainly not running".
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "UPDATE local_analysis_jobs SET state='running',worker_pid=? "
                "WHERE id=?",
                (2_147_483_647, job_id),
            )
            connection.commit()
        finally:
            connection.close()

        self.assertEqual(recover_local_analysis_jobs(self.db), 1)
        run_local_analysis_job(self.db, job_id, analyzer=self.analyzer)

        emitted = self.events()
        self.assertIn(analysis_log.JOB_PAUSED, emitted)
        self.assertIn(analysis_log.JOB_RESUMED, emitted)
        self.assertNotIn(
            analysis_log.JOB_STARTED,
            emitted,
            "A resumed job logged a start. The distinction is the whole "
            "point: the log could not say when the stalled job came back.",
        )
        [paused] = self.fields_for(analysis_log.JOB_PAUSED)
        self.assertEqual(paused["reason"], "worker_released")
        self.assertEqual(paused["pending"], "1")
        self.assertLogIsStructural()

    def test_retrying_failures_logs_its_own_pause(self) -> None:
        self.catalog("fixture_sample_c.txt", b"synthetic content c")
        missing = self.catalog("fixture_absent_c.txt", b"synthetic absent c")
        job_id = create_local_analysis_job(self.db, model="fixture-model")
        missing.unlink()
        run_local_analysis_job(self.db, job_id, analyzer=self.analyzer)

        self.assertEqual(retry_local_analysis_failures(self.db, job_id), 1)

        reasons = [
            fields["reason"]
            for fields in self.fields_for(analysis_log.JOB_PAUSED)
        ]
        self.assertIn("failures_returned_to_pending", reasons)
        self.assertLogIsStructural()


class ModelAttemptLogTests(FixtureJobLogTestCase):
    """Item 1's third class. Nothing recorded that an attempt was made."""

    VALID_RESPONSE = {
        "title": "Synthetic Fixture",
        "description": "Text describing a synthetic fixture.",
        "content_observations": ["The text discusses a synthetic fixture."],
        "evidence_mode": "text_content",
        "media_category": "document",
        "tags": ["fixture"],
        "privacy_flags": [],
        "organization_suggestion": "Leave in test scope.",
        "stock_metadata": {},
        "confidence": 0.8,
    }

    def context(self, source: Path) -> dict[str, object]:
        return {
            "job_id": "fixture-job",
            "source_path": str(source),
            "media_metadata": {},
            "thumbnail_path": "",
            "size_bytes": source.stat().st_size,
        }

    def test_a_rejected_then_accepted_response_logs_both_attempts(
        self,
    ) -> None:
        source = self.sources / "fixture_sample_d.txt"
        source.write_text("A synthetic local fixture.", encoding="utf-8")
        responses = [
            {"message": {"content": "{not-json"}},
            {"message": {"content": json.dumps(self.VALID_RESPONSE)}},
        ]

        with patch(
            "beacon.local_analysis._request_json", side_effect=responses
        ):
            _default_analyzer(
                "http://127.0.0.1:11434", "fixture-model", self.context(source)
            )

        attempts = self.fields_for(analysis_log.MODEL_ATTEMPT)
        self.assertEqual(len(attempts), 2, self.log_lines())
        self.assertEqual(attempts[0]["attempt"], "1")
        self.assertEqual(attempts[0]["of"], str(LOCAL_RESPONSE_ATTEMPTS))
        self.assertEqual(attempts[0]["outcome"], "rejected")
        self.assertEqual(attempts[0]["failure_class"], "model_output_invalid")
        self.assertEqual(attempts[0]["extension"], ".txt")
        self.assertEqual(attempts[1]["attempt"], "2")
        self.assertEqual(attempts[1]["outcome"], "accepted")
        self.assertNotIn("failure_class", attempts[1])
        for fields in attempts:
            self.assertEqual(fields["job"], "fixture-job")
            self.assertIn("seconds", fields)
        self.assertLogIsStructural()

    def test_a_cut_off_response_is_classed_from_the_runtime_s_own_reason(
        self,
    ) -> None:
        """The log and the error field must name one cause, not two.

        A response the generation budget truncated surfaces as a decoder
        error. Classifying it from that exception would file it under
        ``model_output_invalid`` alongside output the model simply got wrong,
        which is the conflation that let this failure class go unexplained for
        four months. The class comes from ``_cut_off_reason`` instead, which
        is also what the item's error field is built from.
        """
        source = self.sources / "fixture_sample_e.txt"
        source.write_text("A synthetic local fixture.", encoding="utf-8")
        truncated = json.dumps(self.VALID_RESPONSE)[:40]
        responses = [
            {
                "message": {"content": truncated},
                "done_reason": "length",
                "eval_count": 8192,
            },
            {"message": {"content": json.dumps(self.VALID_RESPONSE)}},
        ]

        with patch(
            "beacon.local_analysis._request_json", side_effect=responses
        ):
            _default_analyzer(
                "http://127.0.0.1:11434", "fixture-model", self.context(source)
            )

        classes = [
            fields.get("failure_class")
            for fields in self.fields_for(analysis_log.MODEL_ATTEMPT)
        ]
        self.assertIn(
            "model_response_cut_off",
            classes,
            "A cut-off response was not classed as one. Its class must come "
            "from the runtime's own reason, so the log line and the error "
            f"field say the same thing; got {classes}",
        )
        self.assertLogIsStructural()


class RecordedErrorIsStructuralTests(FixtureJobLogTestCase):
    """Item 2, end to end, read back out of the catalog."""

    def test_missing_source_records_a_reason_not_a_path(self) -> None:
        """The defect: the whole recorded error was a deployment path."""
        missing = self.catalog("fixture_absent_f.txt", b"synthetic absent f")
        job_id = create_local_analysis_job(self.db, model="fixture-model")
        missing.unlink()

        result = run_local_analysis_job(
            self.db, job_id, analyzer=self.analyzer
        )
        self.assertEqual(result.failed, 1)

        connection = sqlite3.connect(self.db)
        try:
            state, recorded = connection.execute(
                "SELECT state,error FROM local_analysis_items WHERE job_id=?",
                (job_id,),
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(state, "failed")
        self.assertTrue(recorded, "The item failed and recorded no reason.")
        # Names the reason.
        self.assertIn("source_missing", recorded)
        # Names the extension.
        self.assertIn(".txt", recorded)
        self.assertIn("size class", recorded)
        # And holds no location at all.
        self.assertStructural(recorded)
        self.assertNotIn("fixture_absent_f", recorded)
        self.assertNotIn(missing.name, recorded)
        self.assertNotIn(str(self.sources), recorded)

    def test_the_job_error_field_is_structural_too(self) -> None:
        """The job's error is shown beside the item's and is read the same."""
        missing = self.catalog("fixture_absent_g.txt", b"synthetic absent g")
        job_id = create_local_analysis_job(self.db, model="fixture-model")
        missing.unlink()
        run_local_analysis_job(self.db, job_id, analyzer=self.analyzer)

        connection = sqlite3.connect(self.db)
        try:
            (recorded,) = connection.execute(
                "SELECT error FROM local_analysis_jobs WHERE id=?",
                (job_id,),
            ).fetchone()
        finally:
            connection.close()
        self.assertStructural(recorded or "")

    def test_catalog_drift_still_names_its_cause(self) -> None:
        """The wrapper may not cost the prose an existing guard asserts on."""
        self.catalog("fixture_sample_h.txt", b"synthetic content h")
        job_id = create_local_analysis_job(self.db, model="fixture-model")
        connection = sqlite3.connect(self.db)
        try:
            connection.execute("UPDATE assets SET sha256=?", ("0" * 64,))
            connection.commit()
        finally:
            connection.close()

        run_local_analysis_job(self.db, job_id, analyzer=self.analyzer)

        connection = sqlite3.connect(self.db)
        try:
            (recorded,) = connection.execute(
                "SELECT error FROM local_analysis_items WHERE job_id=?",
                (job_id,),
            ).fetchone()
        finally:
            connection.close()
        self.assertIn("catalog_identity_changed", recorded)
        self.assertIn("catalog checksum changed", recorded)
        self.assertStructural(recorded)


if __name__ == "__main__":
    unittest.main()
