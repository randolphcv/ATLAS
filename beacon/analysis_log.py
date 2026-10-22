"""Structural vocabulary for everything analysis says about itself.

Two faults share one cause, and so share one module.

The application log recorded start, stop and cataloging and nothing else.
Measured across a whole log file during a live eight-hour stall:
``Traceback 0, ERROR 0, timeout 0, model 0, llama 0, retry 0, attempt 0``.
The diagnosis had to be reconstructed entirely from the catalog, because the
log had nothing to say about the job that was stalled. A log that cannot
answer the question it exists for is not a log.

Separately, an item's ``error`` field was written as ``str(error)`` of a
``FileNotFoundError`` raised with a bare path. The recorded error was
therefore literally a deployment path with no explanation: an audit trail that
reads as a path rather than a reason, and a deployment path in a field shown
to the owner.

Both are the same mistake in two places -- recording an occurrence instead of
recording its structure. AGENTS.md section 7 says what to record: counts,
states, durations, error classes, job outcomes. Never which specific files
proved it. This module is the one place that vocabulary is defined, so there
is one answer to what an analysis event looks like rather than one per call
site.

What may be recorded: event names from the constants below, job ids, counts,
durations, extensions, size classes and reason classes. What may not: paths,
filenames, or model output. ``redact`` is the mechanical guarantee rather than
the polite request -- every string that leaves here passes through it, because
exception text is composed by the operating system and by the local model and
is not ours to trust.

Emitting a log line is bookkeeping about an item, not work on it. It may never
be the reason an item or a batch fails, so ``_emit`` swallows its own
failures.
"""

from __future__ import annotations

import functools
import json
import logging
import re
from typing import Any, Callable, TypeVar

LOGGER = logging.getLogger("beacon.analysis")

# Job lifecycle. Each is a transition an operator asked about during the
# stall diagnosis and could not answer from the log.
JOB_CREATED = "job_created"
JOB_STARTED = "job_started"
JOB_PAUSED = "job_paused"
JOB_RESUMED = "job_resumed"
JOB_FINISHED = "job_finished"

# Per-item outcomes. Three, because an exclusion is a success decided by rule
# and reporting it as a completion loses the distinction the counts rest on.
ITEM_COMPLETE = "item_complete"
ITEM_EXCLUDED = "item_excluded"
ITEM_FAILED = "item_failed"

# One line per model attempt. The stall was one item consuming 230 of a job's
# 233 seconds, and nothing recorded that an attempt had even been made.
MODEL_ATTEMPT = "model_attempt"

EVENTS = (
    JOB_CREATED,
    JOB_STARTED,
    JOB_PAUSED,
    JOB_RESUMED,
    JOB_FINISHED,
    ITEM_COMPLETE,
    ITEM_EXCLUDED,
    ITEM_FAILED,
    MODEL_ATTEMPT,
)

REDACTED = "<redacted>"

# A token is path-shaped if it contains either separator or a drive-letter
# prefix. The whole token goes, not the separator alone: half a path is still
# a filename. The lookbehind keeps ordinary prose such as "attempts:" out of
# the drive-letter form, which needs a single letter standing alone.
_PATH_TOKEN = re.compile(r"\S*(?:[\\/]|(?<![A-Za-z0-9])[A-Za-z]:)\S*")
_DRIVE_LETTER = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:")
# Final sweep. After the token rules there should be no separator left; this
# makes "should" into "is" at the cost of one translate call.
_SEPARATORS = str.maketrans({"\\": " ", "/": " "})

# Size classes. Bytes are instance data at full precision and structural once
# bucketed, which is the whole of the distinction section 7 draws.
_SIZE_CLASSES = (
    (1, "empty"),
    (1024, "tiny"),
    (1024 * 1024, "small"),
    (100 * 1024 * 1024, "medium"),
    (1024 * 1024 * 1024, "large"),
)
_LARGEST_SIZE_CLASS = "very_large"
UNKNOWN = "unknown"

# Reason classes recognised by message, for the failures raised as plain
# ValueError or RuntimeError. Matching text is not elegant, but the
# alternative is a class per raise site in a file this module must not own.
# Anything unrecognised falls back to the exception's own type name, which is
# always a class and never a path.
_REASON_BY_PHRASE = (
    # First, deliberately. A response the generation budget cut off is
    # reported by the local runtime and described by
    # ``local_analysis._cut_off_reason``, whose text this phrase is taken
    # from; the final validation error then says both "content validation"
    # and "generation budget", and the cut-off is the cause while the failed
    # validation is only the symptom. Keyed on the two words both that helper
    # and the raise at the end of the retry loop share, so the log line and
    # the item's error field name one cause in one vocabulary instead of two
    # near-synonyms that drift apart.
    ("generation budget", "model_response_cut_off"),
    ("catalog checksum changed", "catalog_identity_changed"),
    ("source bytes changed", "source_bytes_changed"),
    ("content validation", "model_output_invalid"),
    ("local model endpoint", "model_endpoint_unavailable"),
    ("local model", "model_output_invalid"),
    ("no decodable", "no_content_evidence"),
    ("visual derivative", "derivative_unavailable"),
    ("could not be recovered", "location_unrecoverable"),
)

# Prose for the case the message contributes nothing once redacted, which is
# exactly the defect this module was written for: an exception whose entire
# message was a path.
_REASON_PROSE = {
    "source_missing": (
        "the enrolled source is no longer where the catalog says it is"
    ),
    "catalog_identity_changed": "the catalog identity changed since enrolment",
    "source_bytes_changed": "the source bytes changed since cataloging",
    "model_output_invalid": "the local model returned unusable output",
    "model_response_cut_off": (
        "the local runtime stopped generating at its budget, so the response "
        "was cut off rather than complete"
    ),
    "model_endpoint_unavailable": "the local model endpoint did not answer",
    "no_content_evidence": "no decodable content evidence was available",
    "derivative_unavailable": "a required derivative could not be generated",
    "location_unrecoverable": "the analysed location could not be recovered",
}
_FALLBACK_PROSE = "no further structural detail was recorded"

# Exclusion classes. An exclusion is decided by rule and worded as prose for
# the owner to read; the log needs the rule that decided it, not the sentence.
# Keyed on the distinguishing phrase of each reason rather than the whole
# string, so rewording the prose for the owner does not silently reclassify
# every event already in the log.
_EXCLUSION_BY_PHRASE = (
    ("empty file", "empty_file"),
    ("production project file", "production_project_file"),
    ("camera metadata or generated editor index", "camera_or_editor_index"),
    ("presentation document", "document_text_extraction_deferred"),
    ("cache, autosave, or sidecar", "generated_artifact"),
)
_UNCLASSIFIED_EXCLUSION = "unclassified_rule"

ERROR_FIELD_LIMIT = 2000


def redact(text: object) -> str:
    """Return ``text`` with every path-shaped token replaced.

    The guarantee is absolute rather than best-effort: the result contains no
    path separator and no drive-letter prefix, whatever went in. Exception
    messages are composed by the operating system and by the local model, so
    nothing upstream of here can be relied on to have left paths out.
    """
    cleaned = _PATH_TOKEN.sub(REDACTED, str(text))
    cleaned = _DRIVE_LETTER.sub(REDACTED, cleaned)
    cleaned = cleaned.translate(_SEPARATORS)
    return " ".join(cleaned.split())


def size_class(size_bytes: object) -> str:
    """Bucket a byte count. ``unknown`` when there is nothing to bucket."""
    try:
        size = int(size_bytes)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return UNKNOWN
    if size < 0:
        return UNKNOWN
    for ceiling, name in _SIZE_CLASSES:
        if size < ceiling:
            return name
    return _LARGEST_SIZE_CLASS


def extension_label(source: object) -> str:
    """The lowercased suffix of a path, and nothing else from that path.

    Takes the path because every call site has one and none of them should be
    deriving this itself. Returns ``none`` for a file without a suffix, so the
    field is always present and a reader never has to decide whether a
    missing value means no extension or no answer.
    """
    text = str(source or "")
    tail = re.split(r"[\\/]", text)[-1]
    if "." not in tail.lstrip("."):
        return "none"
    suffix = "." + tail.rsplit(".", 1)[1].lower()
    if not re.fullmatch(r"\.[A-Za-z0-9]{1,16}", suffix):
        return UNKNOWN
    return suffix


def reason_class(error: object) -> str:
    """Classify a failure. Always a class name, never an occurrence."""
    if isinstance(error, FileNotFoundError):
        return "source_missing"
    if isinstance(error, TimeoutError):
        return "model_timeout"
    if isinstance(error, json.JSONDecodeError):
        return "model_output_invalid"
    if isinstance(error, ConnectionError):
        return "model_endpoint_unavailable"
    message = str(error).casefold()
    for phrase, name in _REASON_BY_PHRASE:
        if phrase in message:
            return name
    if isinstance(error, BaseException):
        name = type(error).__name__
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).casefold()
    return UNKNOWN


def exclusion_class(reason: object) -> str:
    """Classify an exclusion reason. The rule, not the owner-facing sentence."""
    message = str(reason or "").casefold()
    for phrase, name in _EXCLUSION_BY_PHRASE:
        if phrase in message:
            return name
    return _UNCLASSIFIED_EXCLUSION


def structural_error(
    error: object,
    *,
    source: object = None,
    size_bytes: object = None,
    prefix: str | None = None,
) -> str:
    """The text an item's ``error`` field is allowed to hold.

    Reason class first, because that is what the field is read for. Then the
    exception's own prose, redacted, because "Unterminated string starting at
    line 1 column 1114" is the detail that made one diagnosis possible and
    carries no instance data. Then extension and size class, which are the
    only two things about the file itself that may be recorded.

    This is called on the path that records a failure, so it may not have one
    of its own. Everything it reads was composed elsewhere -- by the operating
    system, by the catalog, by the local model -- and an exception while
    describing a failure would lose the failure. It therefore always returns a
    string, and the worst case is a less informative one.
    """
    classified = UNKNOWN
    try:
        classified = reason_class(error)
        detail = redact(error)
        if not detail or detail == REDACTED:
            detail = _REASON_PROSE.get(classified, _FALLBACK_PROSE)
        facts = (
            f"extension {extension_label(source)}, "
            f"size class {size_class(size_bytes)}"
        )
        head = f"{redact(prefix)} " if prefix else ""
        return f"{head}{classified}: {detail} ({facts})"[:ERROR_FIELD_LIMIT]
    except Exception:  # noqa: BLE001
        LOGGER.debug("a failure could not be described", exc_info=True)
        return (
            f"{classified}: {_FALLBACK_PROSE} "
            f"(extension {UNKNOWN}, size class {UNKNOWN})"
        )


def _render(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, int):
        return str(value)
    # One field per token, so a reader and a grep agree on where a value
    # ends. Redaction first; whitespace collapse second.
    return redact(value).replace(" ", "_") or UNKNOWN


def _emit(event: str, **fields: Any) -> None:
    rendered = " ".join(
        f"{key}={_render(value)}"
        for key, value in fields.items()
        if value is not None
    )
    # The event name is the whole of the message's first token and the logger
    # name is ``beacon.analysis``, so one grep finds a class of event and the
    # configured format already says where it came from.
    LOGGER.info("%s%s", event, f" {rendered}" if rendered else "")


_Emitter = TypeVar("_Emitter", bound=Callable[..., None])


def _never_raises(emitter: _Emitter) -> _Emitter:
    """Guard a whole emitter, not just its final write.

    The guard has to sit outside the field derivation, because classifying a
    reason and labelling an extension are themselves operations on values
    composed elsewhere -- an exception message, a catalog row, a model
    response. A log call that threw while describing a failure would turn one
    item's problem into the batch's, which is the incident AGENTS.md section
    10 says has already happened three times.
    """

    @functools.wraps(emitter)
    def guarded(*args: Any, **kwargs: Any) -> None:
        try:
            emitter(*args, **kwargs)
        except Exception:  # noqa: BLE001
            LOGGER.debug(
                "an analysis event could not be logged", exc_info=True
            )

    return guarded  # type: ignore[return-value]


@_never_raises
def job_created(
    job_id: str,
    *,
    total_items: int,
    scope_kind: str,
    scoped_to_folder: bool,
) -> None:
    """A job exists. ``scoped_to_folder`` is the no-prefix guard's answer."""
    _emit(
        JOB_CREATED,
        job=job_id,
        items=total_items,
        scope=scope_kind,
        scoped_to_folder=scoped_to_folder,
    )


@_never_raises
def job_started(job_id: str, *, pending: int, total_items: int) -> None:
    _emit(JOB_STARTED, job=job_id, pending=pending, items=total_items)


@_never_raises
def job_resumed(job_id: str, *, pending: int, total_items: int) -> None:
    """Distinct from started. Eight hours of the stall were paused time, and
    nothing in the log said when the job came back."""
    _emit(JOB_RESUMED, job=job_id, pending=pending, items=total_items)


@_never_raises
def job_paused(job_id: str, *, pending: int, reason: str) -> None:
    _emit(JOB_PAUSED, job=job_id, pending=pending, reason=reason)


@_never_raises
def job_finished(
    job_id: str,
    *,
    state: str,
    complete: int,
    failed: int,
    excluded: int,
    pending: int,
    duration_seconds: float | None = None,
) -> None:
    _emit(
        JOB_FINISHED,
        job=job_id,
        state=state,
        complete=complete,
        failed=failed,
        excluded=excluded,
        pending=pending,
        seconds=duration_seconds,
    )


@_never_raises
def item_complete(
    job_id: str,
    *,
    source: object,
    size_bytes: object = None,
    duration_seconds: float | None = None,
) -> None:
    _emit(
        ITEM_COMPLETE,
        job=job_id,
        extension=extension_label(source),
        size=size_class(size_bytes),
        seconds=duration_seconds,
    )


@_never_raises
def item_excluded(
    job_id: str,
    *,
    source: object,
    reason: str,
    size_bytes: object = None,
    duration_seconds: float | None = None,
) -> None:
    """An exclusion is an outcome, not a non-event: 71 of the stalled job's 73
    items were exclusions and the log recorded none of them."""
    _emit(
        ITEM_EXCLUDED,
        job=job_id,
        extension=extension_label(source),
        size=size_class(size_bytes),
        reason_class=exclusion_class(reason),
        seconds=duration_seconds,
    )


@_never_raises
def item_failed(
    job_id: str,
    *,
    error: object,
    source: object,
    size_bytes: object = None,
    duration_seconds: float | None = None,
) -> None:
    _emit(
        ITEM_FAILED,
        job=job_id,
        extension=extension_label(source),
        size=size_class(size_bytes),
        reason_class=reason_class(error),
        seconds=duration_seconds,
    )


@_never_raises
def model_attempt(
    job_id: object,
    *,
    attempt: int,
    attempts_allowed: int,
    source: object = None,
    failure: object = None,
    repaired: bool = False,
    duration_seconds: float | None = None,
) -> None:
    """One line per pass over a model response, whatever its outcome.

    ``failure`` omitted means the response was accepted. This is the line
    whose absence made an eight-hour stall unreadable: a job that is waiting
    on a model looks identical in the log to a job that is doing nothing.

    ``repaired`` marks a pass that validated a response Beacon repaired after
    the generation budget cut it off. Repairing costs no generation, so such a
    pass carries the attempt number of the generation it came from; without
    this field two lines would share one number and read as one attempt
    logged twice.

    ``failure`` may be the string ``local_analysis._cut_off_reason`` returns
    rather than an exception, which is how a cut-off gets its own class
    instead of the class of the decoder error it surfaced as.
    """
    _emit(
        MODEL_ATTEMPT,
        job=job_id or UNKNOWN,
        attempt=attempt,
        of=attempts_allowed,
        extension=extension_label(source) if source is not None else None,
        repaired=repaired or None,
        outcome="accepted" if failure is None else "rejected",
        failure_class=None if failure is None else reason_class(failure),
        seconds=duration_seconds,
    )
