from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QObject,
    Property,
    QRunnable,
    QThreadPool,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication

from . import __version__
from .database import (
    BackupResult,
    connect,
    create_backup,
    database_integrity,
    list_backups,
    migrate,
)
from .desk import (
    create_human_thread,
    desk_summary,
    list_threads,
    reply_to_thread,
    resolve_thread,
    thread_detail,
)
from .desktop_models import DictListModel
from .managed_moves import MoveResult, move_cataloged_file
from .metadata import empty_metadata, save_asset_metadata
from .intake import (
    IntakeRunResult,
    create_intake_job,
    intake_job_detail,
    list_intake_jobs,
    pause_intake_job,
    recover_intake_jobs,
    request_intake_cancel,
    retry_intake_failures,
    run_intake_job,
)
from .local_analysis import (
    LocalAnalysisRunResult,
    analysis_scope_preview,
    create_local_analysis_job,
    list_local_analysis_jobs,
    local_runtime_status,
    recover_local_analysis_jobs,
    request_local_analysis_cancel,
    run_local_analysis_job,
)
from .repository import (
    RAW_PHOTO_EXTENSIONS,
    asset_detail,
    catalog_summary,
    library_folders,
    recent_events,
    search_assets,
)
from .text_preview import read_text_preview
from .thumbnails import ensure_thumbnail

LOGGER = logging.getLogger("beacon.desktop")


@dataclass(frozen=True)
class DesktopSettings:
    db_path: Path
    backup_dir: Path
    catalog_label: str = "Custom catalog"
    allowed_intake_roots: tuple[Path, ...] = (Path(r"J:\Inbox"),)


def format_bytes(value: int | None) -> str:
    size = float(value or 0)
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            precision = 0 if unit == "B" else 1
            return f"{size:.{precision}f} {unit}"
        size /= 1024
    return "0 B"


def format_timestamp(value: str | None) -> str:
    if not value:
        return "No activity yet"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        local = parsed.astimezone()
        return local.strftime("%b %d, %Y · %I:%M %p")
    except (TypeError, ValueError):
        return value


class _BackupSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)


class _BackupWorker(QRunnable):
    def __init__(self, db_path: Path, backup_dir: Path) -> None:
        super().__init__()
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.signals = _BackupSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.succeeded.emit(create_backup(self.db_path, self.backup_dir))
        except Exception as error:  # Qt worker boundary; surfaced in the UI and log.
            LOGGER.exception("verified backup failed")
            self.signals.failed.emit(str(error))


class _MoveSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)


class _MoveWorker(QRunnable):
    def __init__(
        self,
        db_path: Path,
        asset_id: str,
        source_path: Path,
        destination_directory: Path,
    ) -> None:
        super().__init__()
        self.db_path = db_path
        self.asset_id = asset_id
        self.source_path = source_path
        self.destination_directory = destination_directory
        self.signals = _MoveSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.succeeded.emit(
                move_cataloged_file(
                    self.db_path,
                    asset_id=self.asset_id,
                    source_path=self.source_path,
                    destination_directory=self.destination_directory,
                    requested_by="human",
                    authorization=(
                        "Native app confirmation under the managed-moves policy "
                        "approved 2026-07-23"
                    ),
                )
            )
        except Exception as error:
            LOGGER.exception("managed move failed")
            self.signals.failed.emit(str(error))


class _IntakeCreateSignals(QObject):
    succeeded = Signal(str)
    failed = Signal(str)


class _IntakeCreateWorker(QRunnable):
    def __init__(
        self,
        db_path: Path,
        source_root: Path,
        allowed_roots: tuple[Path, ...],
        item_limit: int | None,
    ) -> None:
        super().__init__()
        self.db_path = db_path
        self.source_root = source_root
        self.allowed_roots = allowed_roots
        self.item_limit = item_limit
        self.signals = _IntakeCreateSignals()

    @Slot()
    def run(self) -> None:
        try:
            job_id = create_intake_job(
                self.db_path,
                source_root=self.source_root,
                allowed_roots=self.allowed_roots,
                item_limit=self.item_limit,
                requested_by="human",
            )
            self.signals.succeeded.emit(job_id)
        except Exception as error:
            LOGGER.exception("could not create intake job")
            self.signals.failed.emit(str(error))


class _IntakeRunSignals(QObject):
    progressed = Signal()
    succeeded = Signal(object)
    failed = Signal(str)


class _IntakeRunWorker(QRunnable):
    def __init__(self, db_path: Path, job_id: str) -> None:
        super().__init__()
        self.db_path = db_path
        self.job_id = job_id
        self.signals = _IntakeRunSignals()
        self._last_progress_at = 0.0

    def _progress(self) -> None:
        now = time.monotonic()
        if now - self._last_progress_at >= 0.25:
            self._last_progress_at = now
            self.signals.progressed.emit()

    @Slot()
    def run(self) -> None:
        try:
            result = run_intake_job(
                self.db_path,
                self.job_id,
                progress_callback=self._progress,
            )
            self.signals.succeeded.emit(result)
        except Exception as error:
            LOGGER.exception("intake job failed")
            self.signals.failed.emit(str(error))


class _LocalAnalysisSignals(QObject):
    progressed = Signal()
    succeeded = Signal(object)
    failed = Signal(str)


class _LocalAnalysisWorker(QRunnable):
    def __init__(self, db_path: Path, job_id: str) -> None:
        super().__init__()
        self.db_path = db_path
        self.job_id = job_id
        self.signals = _LocalAnalysisSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.succeeded.emit(
                run_local_analysis_job(
                    self.db_path,
                    self.job_id,
                    progress_callback=self.signals.progressed.emit,
                )
            )
        except Exception as error:
            LOGGER.exception("local analysis job failed")
            self.signals.failed.emit(str(error))


class DesktopController(QObject):
    summaryChanged = Signal()
    databaseHealthChanged = Signal()
    selectedAssetChanged = Signal()
    currentViewChanged = Signal()
    searchQueryChanged = Signal()
    libraryChanged = Signal()
    busyChanged = Signal()
    statusChanged = Signal()
    lastRefreshChanged = Signal()
    beaconDeskChanged = Signal()
    selectedBeaconThreadChanged = Signal()
    intakeChanged = Signal()
    selectedIntakeJobChanged = Signal()
    analysisReadinessChanged = Signal()
    localAnalysisRunningChanged = Signal()

    def __init__(self, settings: DesktopSettings) -> None:
        super().__init__()
        self.settings = settings
        self._summary: dict[str, Any] = {}
        self._database_health: dict[str, Any] = {}
        self._selected_asset: dict[str, Any] = {}
        self._current_view = "overview"
        self._search_query = ""
        self._library_mode = "recents"
        self._library_path = "J:\\"
        self._library_file_type = "all"
        self._busy = False
        self._status_message = ""
        self._status_kind = "neutral"
        self._last_refresh = ""
        self._beacon_desk_summary: dict[str, Any] = {}
        self._selected_beacon_thread: dict[str, Any] = {}
        self._intake_summary: dict[str, Any] = {}
        self._selected_intake_job: dict[str, Any] = {}
        self._analysis_readiness: dict[str, Any] = {}
        self._active_local_analysis_job_id = ""
        self._last_catalog_signature: tuple[int, int, int, int] | None = None
        self._workers: list[QRunnable] = []
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)

        self._assets = DictListModel(
            (
                "assetId",
                "filename",
                "displayTitle",
                "path",
                "atlasUri",
                "kind",
                "kindLabel",
                "sizeLabel",
                "timeLabel",
                "metaLine",
                "locationCount",
                "thumbnailUrl",
                "analyzed",
                "statusLabel",
            )
        )
        self._library_folders = DictListModel(
            ("folderName", "folderPath", "assetCount", "countLabel")
        )
        self._events = DictListModel(
            (
                "eventId",
                "kind",
                "state",
                "message",
                "timeLabel",
                "location",
                "assetId",
            )
        )
        self._backups = DictListModel(
            ("name", "path", "sizeLabel", "timeLabel")
        )
        self._beacon_threads = DictListModel(
            (
                "threadId",
                "subject",
                "kind",
                "kindLabel",
                "priority",
                "state",
                "stateLabel",
                "preview",
                "updatedLabel",
                "requiresApproval",
                "messageCount",
            )
        )
        self._beacon_messages = DictListModel(
            (
                "messageId",
                "author",
                "authorLabel",
                "body",
                "timeLabel",
            )
        )
        self._intake_jobs = DictListModel(
            (
                "jobId",
                "sourceRoot",
                "state",
                "stateLabel",
                "progress",
                "progressLabel",
                "countLabel",
                "sizeLabel",
                "updatedLabel",
                "currentPath",
                "failedCount",
                "pendingCount",
            )
        )

        self.settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.backup_dir.mkdir(parents=True, exist_ok=True)
        with connect(self.settings.db_path) as connection:
            migrate(connection)
        recovered = recover_intake_jobs(self.settings.db_path)
        recovered_analysis = recover_local_analysis_jobs(self.settings.db_path)
        self.refresh()
        if recovered:
            self._set_status(
                f"Recovered {recovered} interrupted intake job"
                + ("s" if recovered != 1 else "")
                + "; ready to resume.",
                "working",
            )
        elif recovered_analysis:
            self._set_status(
                f"Recovered {recovered_analysis} interrupted local analysis job"
                + ("s" if recovered_analysis != 1 else "")
                + "; prepare analysis to resume.",
                "working",
            )

    @Property(QObject, constant=True)
    def assets(self) -> QObject:
        return self._assets

    @Property(QObject, constant=True)
    def libraryFolders(self) -> QObject:
        return self._library_folders

    @Property(QObject, constant=True)
    def events(self) -> QObject:
        return self._events

    @Property(QObject, constant=True)
    def backups(self) -> QObject:
        return self._backups

    @Property(QObject, constant=True)
    def beaconThreads(self) -> QObject:
        return self._beacon_threads

    @Property(QObject, constant=True)
    def beaconMessages(self) -> QObject:
        return self._beacon_messages

    @Property(QObject, constant=True)
    def intakeJobs(self) -> QObject:
        return self._intake_jobs

    @Property("QVariantMap", notify=summaryChanged)
    def summary(self) -> dict[str, Any]:
        return self._summary

    @Property("QVariantMap", notify=databaseHealthChanged)
    def databaseHealth(self) -> dict[str, Any]:
        return self._database_health

    @Property("QVariantMap", notify=selectedAssetChanged)
    def selectedAsset(self) -> dict[str, Any]:
        return self._selected_asset

    @Property("QVariantMap", notify=beaconDeskChanged)
    def beaconDeskSummary(self) -> dict[str, Any]:
        return self._beacon_desk_summary

    @Property("QVariantMap", notify=selectedBeaconThreadChanged)
    def selectedBeaconThread(self) -> dict[str, Any]:
        return self._selected_beacon_thread

    @Property("QVariantMap", notify=intakeChanged)
    def intakeSummary(self) -> dict[str, Any]:
        return self._intake_summary

    @Property("QVariantMap", notify=selectedIntakeJobChanged)
    def selectedIntakeJob(self) -> dict[str, Any]:
        return self._selected_intake_job

    @Property("QVariantMap", notify=analysisReadinessChanged)
    def analysisReadiness(self) -> dict[str, Any]:
        return self._analysis_readiness

    @Property(bool, notify=localAnalysisRunningChanged)
    def localAnalysisRunning(self) -> bool:
        return bool(self._active_local_analysis_job_id)

    @Property(str, notify=currentViewChanged)
    def currentView(self) -> str:
        return self._current_view

    @Property(str, notify=searchQueryChanged)
    def searchQuery(self) -> str:
        return self._search_query

    @Property(str, notify=libraryChanged)
    def libraryMode(self) -> str:
        return self._library_mode

    @Property(str, notify=libraryChanged)
    def libraryPath(self) -> str:
        return self._library_path

    @Property(str, notify=libraryChanged)
    def libraryFileType(self) -> str:
        return self._library_file_type

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=statusChanged)
    def statusMessage(self) -> str:
        return self._status_message

    @Property(str, notify=statusChanged)
    def statusKind(self) -> str:
        return self._status_kind

    @Property(str, notify=lastRefreshChanged)
    def lastRefresh(self) -> str:
        return self._last_refresh

    @Property(str, constant=True)
    def databasePath(self) -> str:
        return str(self.settings.db_path)

    @Property(str, constant=True)
    def backupDirectory(self) -> str:
        return str(self.settings.backup_dir)

    @Property(str, constant=True)
    def catalogLabel(self) -> str:
        return self.settings.catalog_label

    @Property(str, constant=True)
    def applicationVersion(self) -> str:
        return __version__

    @Property(str, constant=True)
    def defaultIntakeRoot(self) -> str:
        if not self.settings.allowed_intake_roots:
            return ""
        return str(self.settings.allowed_intake_roots[0])

    @Slot(str)
    def setCurrentView(self, view: str) -> None:
        if view not in {"overview", "library", "operations", "system"}:
            return
        if self._current_view != view:
            self._current_view = view
            self.currentViewChanged.emit()

    @Slot(str)
    def setSearchQuery(self, query: str) -> None:
        query = query.strip()[:200]
        if self._search_query == query:
            return
        self._search_query = query
        self.searchQueryChanged.emit()
        self._load_assets(preserve_selection=True)

    @Slot(str)
    def setLibraryMode(self, mode: str) -> None:
        if mode not in {"recents", "explorer"} or mode == self._library_mode:
            return
        self._library_mode = mode
        self.libraryChanged.emit()
        self._load_assets(preserve_selection=True)

    @Slot(str)
    def setLibraryFileType(self, file_type: str) -> None:
        normalized = file_type.strip().lower()
        if normalized not in {"all", "photo", "raw", "video", "audio", "other"}:
            normalized = "all"
        if normalized == self._library_file_type:
            return
        self._library_file_type = normalized
        self.libraryChanged.emit()
        self._load_assets(preserve_selection=True)

    @Slot(str)
    def openLibraryFolder(self, path: str) -> None:
        candidate = Path(path)
        try:
            resolved = str(candidate.resolve())
        except OSError:
            return
        if not resolved.lower().startswith("j:\\"):
            return
        self._library_mode = "explorer"
        self._library_path = resolved
        self.libraryChanged.emit()
        self._load_assets(preserve_selection=False)

    @Slot()
    def libraryFolderUp(self) -> None:
        current = Path(self._library_path)
        parent = current.parent
        target = "J:\\" if str(current).lower() == "j:\\" else str(parent)
        if not target.lower().startswith("j:\\"):
            target = "J:\\"
        self.openLibraryFolder(target)

    @Slot()
    def refresh(self) -> None:
        try:
            summary = catalog_summary(self.settings.db_path)
            self._summary = {
                **summary,
                "assetsLabel": f"{summary['assets']:,}",
                "locationsLabel": f"{summary['locations']:,}",
                "duplicatesLabel": f"{summary['duplicate_groups']:,}",
                "storageLabel": format_bytes(summary["total_bytes"]),
                "failuresLabel": f"{summary['failures']:,}",
                "lastActivityLabel": format_timestamp(summary["last_activity_at"]),
            }
            self.summaryChanged.emit()

            health = database_integrity(self.settings.db_path)
            self._database_health = {
                **health,
                "stateLabel": (
                    "Verified healthy"
                    if health["state"] == "healthy"
                    else "Needs attention"
                ),
                "sizeLabel": format_bytes(int(health.get("size_bytes") or 0)),
                "schemaLabel": f"Schema {health.get('schema_version') or '—'}",
                "journalLabel": str(health.get("journal_mode") or "unknown").upper(),
            }
            self.databaseHealthChanged.emit()
            self._load_assets(preserve_selection=True)
            self._load_events()
            self._load_backups()
            self._load_intake_jobs(preserve_selection=True)
            self.refreshAnalysisReadiness()
            self._sync_local_analysis_state()
            self._load_beacon_threads(preserve_selection=True)
            self._last_refresh = datetime.now().astimezone().strftime("%I:%M:%S %p")
            self._last_catalog_signature = self._catalog_signature()
            self.lastRefreshChanged.emit()
        except Exception as error:
            LOGGER.exception("desktop refresh failed")
            self._set_status(f"Could not refresh Beacon: {error}", "error")

    def _sync_local_analysis_state(self) -> None:
        jobs = list_local_analysis_jobs(self.settings.db_path, limit=1)
        latest = jobs[0] if jobs else None
        running = latest if latest and latest["state"] == "running" else None
        previous_id = self._active_local_analysis_job_id
        previous_busy = self._busy
        if running:
            self._active_local_analysis_job_id = str(running["id"])
            self._busy = True
            completed = int(running.get("completed_count") or 0)
            total = int(running.get("total_items") or 0)
            self._set_status(
                f"Local analysis running: {completed:,} of {total:,} complete.",
                "working",
            )
        elif previous_id:
            self._active_local_analysis_job_id = ""
            self._busy = False
            if latest:
                completed = int(latest.get("completed_count") or 0)
                failed = int(latest.get("failed_count") or 0)
                self._set_status(
                    f"Local analysis {latest['state']}: "
                    f"{completed:,} complete, {failed:,} failed.",
                    "success" if latest["state"] == "complete" else "working",
                )
        if previous_id != self._active_local_analysis_job_id:
            self.localAnalysisRunningChanged.emit()
        if previous_busy != self._busy:
            self.busyChanged.emit()

    def _catalog_signature(self) -> tuple[int, int, int, int]:
        database = self.settings.db_path
        wal = Path(f"{database}-wal")
        database_stat = database.stat() if database.exists() else None
        wal_stat = wal.stat() if wal.exists() else None
        return (
            database_stat.st_mtime_ns if database_stat else 0,
            database_stat.st_size if database_stat else 0,
            wal_stat.st_mtime_ns if wal_stat else 0,
            wal_stat.st_size if wal_stat else 0,
        )

    @Slot()
    def refreshIfChanged(self) -> None:
        if self._catalog_signature() != self._last_catalog_signature:
            self.refresh()

    def _load_assets(self, *, preserve_selection: bool) -> None:
        current_id = self._selected_asset.get("id") if preserve_selection else None
        result = search_assets(
            self.settings.db_path,
            query=self._search_query,
            path_prefix=self._library_path if self._library_mode == "explorer" else "",
            file_type=self._library_file_type,
            limit=500 if self._library_mode == "explorer" else 100,
        )
        rows = [self._asset_row(item) for item in result["items"]]
        self._assets.replace(rows)
        folders = (
            library_folders(self.settings.db_path, self._library_path)
            if self._library_mode == "explorer"
            else []
        )
        self._library_folders.replace(
            {
                "folderName": item["name"],
                "folderPath": item["path"],
                "assetCount": item["asset_count"],
                "countLabel": f"{item['asset_count']:,}",
            }
            for item in folders
        )
        available_ids = {row["assetId"] for row in rows}
        if current_id in available_ids:
            self._select_asset(str(current_id))
        elif rows:
            self._select_asset(rows[0]["assetId"])
        else:
            self._selected_asset = {}
            self.selectedAssetChanged.emit()

    def _load_events(self) -> None:
        rows = []
        for event in recent_events(self.settings.db_path, 100):
            rows.append(
                {
                    "eventId": event["id"],
                    "kind": event["kind"],
                    "state": event["state"],
                    "message": event["message"],
                    "timeLabel": format_timestamp(event["created_at"]),
                    "location": event.get("location_path") or "",
                    "assetId": event.get("asset_id") or "",
                }
            )
        self._events.replace(rows)

    def _load_backups(self) -> None:
        self._backups.replace(
            {
                "name": backup["name"],
                "path": backup["path"],
                "sizeLabel": format_bytes(int(backup["size_bytes"])),
                "timeLabel": format_timestamp(str(backup["modified_at"])),
            }
            for backup in list_backups(self.settings.backup_dir)
        )

    def _load_intake_jobs(self, *, preserve_selection: bool) -> None:
        current_id = (
            self._selected_intake_job.get("id") if preserve_selection else None
        )
        jobs = list_intake_jobs(self.settings.db_path)
        rows = [self._intake_job_row(job) for job in jobs]
        self._intake_jobs.replace(rows)
        active = sum(
            1
            for job in jobs
            if job["state"] in {"queued", "running", "paused"}
            and (
                int(job.get("pending_count") or 0)
                + int(job.get("running_count") or 0)
            )
        )
        failed = sum(int(job.get("failed_count") or 0) for job in jobs)
        self._intake_summary = {
            "jobs": len(jobs),
            "active": active,
            "failed": failed,
            "jobsLabel": f"{len(jobs):,}",
            "activeLabel": f"{active:,}",
            "failedLabel": f"{failed:,}",
        }
        available_ids = {row["jobId"] for row in rows}
        if current_id in available_ids:
            self._select_intake_job(str(current_id))
        elif rows:
            self._select_intake_job(rows[0]["jobId"])
        else:
            self._selected_intake_job = {}
            self.selectedIntakeJobChanged.emit()
        self.intakeChanged.emit()

    @staticmethod
    def _intake_job_row(job: dict[str, Any]) -> dict[str, Any]:
        state = str(job.get("state") or "queued")
        state_labels = {
            "queued": "Ready",
            "running": "Running",
            "paused": "Paused",
            "complete": "Complete",
            "partial": "Needs retry",
            "failed": "Failed",
            "cancelled": "Cancelled",
        }
        total = int(job.get("total_items") or 0)
        complete = int(job.get("completed_count") or 0)
        failed = int(job.get("failed_count") or 0)
        pending = int(job.get("pending_count") or 0)
        processed = complete + failed
        progress = 1.0 if total == 0 else min(1.0, processed / total)
        return {
            "jobId": job["id"],
            "sourceRoot": job["source_root"],
            "state": state,
            "stateLabel": state_labels.get(state, state.title()),
            "progress": progress,
            "progressLabel": f"{progress:.0%}",
            "countLabel": f"{complete:,} complete / {total:,} files",
            "sizeLabel": (
                f"{format_bytes(int(job.get('completed_bytes') or 0))} / "
                f"{format_bytes(int(job.get('total_bytes') or 0))}"
            ),
            "updatedLabel": format_timestamp(job.get("updated_at")),
            "currentPath": str(job.get("current_path") or ""),
            "failedCount": failed,
            "pendingCount": pending,
        }

    @Slot(str)
    def selectIntakeJob(self, job_id: str) -> None:
        self._select_intake_job(job_id)

    def _select_intake_job(self, job_id: str) -> None:
        detail = intake_job_detail(self.settings.db_path, job_id)
        if detail is None:
            self._selected_intake_job = {}
        else:
            row = self._intake_job_row(detail)
            failures = detail.get("failures") or []
            state = str(detail.get("state") or "")
            row.update(
                {
                    "id": detail["id"],
                    "snapshotSha256": detail["snapshot_sha256"],
                    "modeLabel": "CATALOG ONLY",
                    "createdLabel": format_timestamp(detail.get("created_at")),
                    "itemLimitLabel": (
                        f"First {int(detail['item_limit']):,} files"
                        if detail.get("item_limit")
                        else "All discovered files"
                    ),
                    "failureSummary": "\n".join(
                        f"{failure['relative_path']}: {failure['error']}"
                        for failure in failures
                    ),
                    "canStart": (
                        state in {"queued", "paused", "cancelled", "partial"}
                        and int(detail.get("pending_count") or 0) > 0
                    ),
                    "canCancel": state in {"queued", "running", "paused"},
                    "canRetry": (
                        state != "running"
                        and int(detail.get("failed_count") or 0) > 0
                    ),
                }
            )
            self._selected_intake_job = row
        self.selectedIntakeJobChanged.emit()

    @Slot(str, str)
    def createIntakeJob(self, source_root: str, limit_text: str) -> None:
        if self._busy:
            return
        try:
            stripped = limit_text.strip()
            item_limit = int(stripped) if stripped else None
            if item_limit is not None and not 1 <= item_limit <= 100_000:
                raise ValueError("file limit must be between 1 and 100,000")
            if not source_root.strip():
                raise ValueError("choose an approved intake folder")
        except ValueError as error:
            self._set_status(str(error), "error")
            return
        self._busy = True
        self.busyChanged.emit()
        self._set_status("Building a recursive intake snapshot…", "working")
        worker = _IntakeCreateWorker(
            self.settings.db_path,
            Path(source_root.strip()),
            self.settings.allowed_intake_roots,
            item_limit,
        )
        self._workers.append(worker)
        worker.signals.succeeded.connect(
            lambda job_id, current=worker: self._intake_created(current, job_id)
        )
        worker.signals.failed.connect(
            lambda message, current=worker: self._intake_failed(current, message)
        )
        self._thread_pool.start(worker)

    def _intake_created(
        self, worker: _IntakeCreateWorker, job_id: str
    ) -> None:
        self._finish_worker(worker)
        self._selected_intake_job = {"id": job_id}
        self._load_events()
        self._load_intake_jobs(preserve_selection=True)
        self._set_status(
            "Intake snapshot created. Review it, then choose Start.", "success"
        )

    @Slot()
    def startSelectedIntakeJob(self) -> None:
        if self._busy:
            return
        job_id = str(self._selected_intake_job.get("id") or "")
        if not job_id:
            self._set_status("Select an intake job first.", "error")
            return
        self._busy = True
        self.busyChanged.emit()
        self._set_status("Beacon is cataloging the intake snapshot…", "working")
        worker = _IntakeRunWorker(self.settings.db_path, job_id)
        self._workers.append(worker)
        worker.signals.progressed.connect(self._intake_progressed)
        worker.signals.succeeded.connect(
            lambda result, current=worker: self._intake_succeeded(current, result)
        )
        worker.signals.failed.connect(
            lambda message, current=worker: self._intake_failed(current, message)
        )
        self._thread_pool.start(worker)

    @Slot()
    def cancelSelectedIntakeJob(self) -> None:
        job_id = str(self._selected_intake_job.get("id") or "")
        if not job_id:
            return
        try:
            request_intake_cancel(self.settings.db_path, job_id)
            self._load_intake_jobs(preserve_selection=True)
            self._set_status(
                "Cancellation requested; Beacon will stop between files.",
                "working",
            )
        except (LookupError, ValueError) as error:
            self._set_status(str(error), "error")

    @Slot()
    def retrySelectedIntakeJob(self) -> None:
        if self._busy:
            return
        job_id = str(self._selected_intake_job.get("id") or "")
        if not job_id:
            return
        try:
            count = retry_intake_failures(self.settings.db_path, job_id)
            self._load_intake_jobs(preserve_selection=True)
            self._set_status(
                f"Queued {count:,} failed file"
                + ("s" if count != 1 else "")
                + " for retry.",
                "working",
            )
            self.startSelectedIntakeJob()
        except (LookupError, ValueError) as error:
            self._set_status(str(error), "error")

    def _intake_progressed(self) -> None:
        self._load_intake_jobs(preserve_selection=True)

    def _intake_succeeded(
        self,
        worker: _IntakeRunWorker,
        result: IntakeRunResult,
    ) -> None:
        self._finish_worker(worker)
        self.refresh()
        messages = {
            "complete": (
                f"Intake complete: {result.completed:,} files cataloged."
            ),
            "cancelled": (
                f"Intake cancelled after {result.completed:,} completed files."
            ),
            "paused": "Intake paused and ready to resume.",
            "partial": (
                f"Intake finished with {result.failed:,} retryable failures."
            ),
            "failed": (
                f"Intake failed for {result.failed:,} files; review and retry."
            ),
        }
        self._set_status(
            messages.get(result.state, f"Intake state: {result.state}"),
            "success" if result.state == "complete" else "working",
        )

    def _intake_failed(self, worker: QRunnable, message: str) -> None:
        self._finish_worker(worker)
        recover_intake_jobs(self.settings.db_path)
        self._load_intake_jobs(preserve_selection=True)
        self._set_status(f"Intake operation failed: {message}", "error")

    @Slot()
    def refreshAnalysisReadiness(self) -> None:
        runtime = local_runtime_status()
        scope = analysis_scope_preview(self.settings.db_path)
        full_scope = analysis_scope_preview(
            self.settings.db_path, include_analyzed=True
        )
        jobs = list_local_analysis_jobs(self.settings.db_path, limit=1)
        latest_job = jobs[0] if jobs else None
        analysis_total = int(
            latest_job.get("total_items") or 0
        ) if latest_job else 0
        analysis_complete = int(
            latest_job.get("completed_count") or 0
        ) if latest_job else 0
        analysis_failed = int(
            latest_job.get("failed_count") or 0
        ) if latest_job else 0
        analysis_processed = analysis_complete + analysis_failed
        analysis_progress = (
            min(1.0, analysis_processed / analysis_total)
            if analysis_total else 0.0
        )
        models = list(runtime.models)
        self._analysis_readiness = {
            **scope,
            "assetsLabel": f"{scope['assets']:,}",
            "bytesLabel": format_bytes(int(scope["bytes"])),
            "visualLabel": f"{scope['visual']:,}",
            "audioLabel": f"{scope['audio']:,}",
            "otherLabel": f"{scope['other']:,}",
            "allAssetsLabel": f"{full_scope['assets']:,}",
            "allBytesLabel": format_bytes(int(full_scope["bytes"])),
            "allVisualLabel": f"{full_scope['visual']:,}",
            "allAudioLabel": f"{full_scope['audio']:,}",
            "allOtherLabel": f"{full_scope['other']:,}",
            "analysisHasJob": bool(latest_job),
            "analysisJobState": (
                str(latest_job.get("state") or "") if latest_job else ""
            ),
            "analysisStateLabel": (
                str(latest_job.get("state") or "").replace("_", " ").title()
                if latest_job else "Not started"
            ),
            "analysisProgress": analysis_progress,
            "analysisProgressLabel": f"{analysis_progress:.0%}",
            "analysisCountLabel": (
                f"{analysis_complete:,} complete / {analysis_total:,} assets"
            ),
            "analysisFailedLabel": f"{analysis_failed:,} failed",
            "runtimeAvailable": runtime.available,
            "runtimeLabel": (
                f"Local runtime {runtime.version}"
                if runtime.available
                else "Local runtime not detected"
            ),
            "runtimeDetail": (
                f"{len(models):,} installed model"
                + ("s" if len(models) != 1 else "")
                if runtime.available
                else "Start an OpenAI-compatible local Ollama endpoint at 127.0.0.1:11434."
            ),
            "models": models,
            "defaultModel": models[0] if models else "",
            "canStart": runtime.available and bool(models)
            and scope["assets"] > 0,
            "canReanalyze": runtime.available and bool(models)
            and full_scope["assets"] > 0,
        }
        self.analysisReadinessChanged.emit()

    @Slot(str, bool)
    def startLocalCatalogAnalysis(
        self, model: str, include_analyzed: bool
    ) -> None:
        if self._busy:
            return
        runtime = local_runtime_status()
        if not runtime.available:
            self._set_status(
                "Local model runtime is unavailable. No media was sent anywhere.",
                "error",
            )
            self.refreshAnalysisReadiness()
            return
        if model.strip() not in runtime.models:
            self._set_status("Choose an installed local model.", "error")
            self.refreshAnalysisReadiness()
            return
        try:
            job_id = create_local_analysis_job(
                self.settings.db_path,
                model=model,
                include_analyzed=include_analyzed,
                requested_by="human",
            )
        except ValueError as error:
            self._set_status(str(error), "error")
            return
        self._busy = True
        self._active_local_analysis_job_id = job_id
        self.localAnalysisRunningChanged.emit()
        self.busyChanged.emit()
        self._set_status(
            "Beacon is running local-only contextual analysis…", "working"
        )
        worker = _LocalAnalysisWorker(self.settings.db_path, job_id)
        self._workers.append(worker)
        worker.signals.progressed.connect(self.refresh)
        worker.signals.succeeded.connect(
            lambda result, current=worker: self._local_analysis_succeeded(
                current, result
            )
        )
        worker.signals.failed.connect(
            lambda message, current=worker: self._local_analysis_failed(
                current, message
            )
        )
        self._thread_pool.start(worker)

    def _local_analysis_succeeded(
        self, worker: _LocalAnalysisWorker, result: LocalAnalysisRunResult
    ) -> None:
        self._active_local_analysis_job_id = ""
        self.localAnalysisRunningChanged.emit()
        self._finish_worker(worker)
        self.refresh()
        self._set_status(
            f"Local analysis {result.state}: {result.completed:,} candidate"
            + ("s" if result.completed != 1 else "")
            + f", {result.failed:,} failed.",
            "success" if result.state == "complete" else "working",
        )

    def _local_analysis_failed(
        self, worker: _LocalAnalysisWorker, message: str
    ) -> None:
        self._active_local_analysis_job_id = ""
        self.localAnalysisRunningChanged.emit()
        self._finish_worker(worker)
        recover_local_analysis_jobs(self.settings.db_path)
        self.refresh()
        self._set_status(f"Local analysis failed: {message}", "error")

    @Slot()
    def cancelLocalCatalogAnalysis(self) -> None:
        if not self._active_local_analysis_job_id:
            return
        request_local_analysis_cancel(
            self.settings.db_path, self._active_local_analysis_job_id
        )
        self._set_status(
            "Local analysis cancellation requested; Beacon will stop between assets.",
            "working",
        )

    def _load_beacon_threads(self, *, preserve_selection: bool) -> None:
        current_id = (
            self._selected_beacon_thread.get("id") if preserve_selection else None
        )
        summary = desk_summary(self.settings.db_path)
        self._beacon_desk_summary = {
            **summary,
            "openLabel": f"{summary['open']:,}",
            "awaitingLabel": f"{summary['awaiting_human']:,}",
            "queuedLabel": f"{summary['queued_for_beacon']:,}",
            "connectionLabel": "SAVED LOCALLY",
        }
        rows = [self._beacon_thread_row(thread) for thread in list_threads(
            self.settings.db_path
        )]
        self._beacon_threads.replace(rows)
        available_ids = {row["threadId"] for row in rows}
        if current_id in available_ids:
            self._select_beacon_thread(str(current_id))
        elif rows:
            self._select_beacon_thread(rows[0]["threadId"])
        else:
            self._selected_beacon_thread = {}
            self._beacon_messages.replace(())
            self.selectedBeaconThreadChanged.emit()
        self.beaconDeskChanged.emit()

    @staticmethod
    def _beacon_thread_row(thread: dict[str, Any]) -> dict[str, Any]:
        state = str(thread.get("state") or "")
        state_labels = {
            "awaiting_human": "Waiting for you",
            "queued_for_beacon": "Queued for Beacon",
            "resolved": "Resolved",
            "closed": "Closed",
        }
        kind = str(thread.get("kind") or "question")
        preview = " ".join(str(thread.get("latest_message") or "").split())
        return {
            "threadId": thread["id"],
            "subject": thread["subject"],
            "kind": kind,
            "kindLabel": kind.replace("_", " ").title(),
            "priority": thread.get("priority") or "normal",
            "state": state,
            "stateLabel": state_labels.get(state, state.replace("_", " ").title()),
            "preview": preview,
            "updatedLabel": format_timestamp(thread.get("updated_at")),
            "requiresApproval": bool(thread.get("requires_approval")),
            "messageCount": int(thread.get("message_count") or 0),
        }

    @Slot(str)
    def selectBeaconThread(self, thread_id: str) -> None:
        self._select_beacon_thread(thread_id)

    def _select_beacon_thread(self, thread_id: str) -> None:
        detail = thread_detail(self.settings.db_path, thread_id)
        if detail is None:
            self._selected_beacon_thread = {}
            self._beacon_messages.replace(())
        else:
            state = str(detail.get("state") or "")
            state_labels = {
                "awaiting_human": "WAITING FOR YOU",
                "queued_for_beacon": "QUEUED FOR BEACON",
                "resolved": "RESOLVED",
                "closed": "CLOSED",
            }
            detail["kindLabel"] = str(
                detail.get("kind") or "question"
            ).replace("_", " ").title()
            detail["stateLabel"] = state_labels.get(
                state, state.replace("_", " ").upper()
            )
            detail["updatedLabel"] = format_timestamp(detail.get("updated_at"))
            detail["requiresApproval"] = bool(
                detail.get("requires_approval")
            )
            messages = detail.pop("messages", [])
            self._selected_beacon_thread = detail
            self._beacon_messages.replace(
                {
                    "messageId": message["id"],
                    "author": message["author"],
                    "authorLabel": (
                        "YOU"
                        if message["author"] == "human"
                        else str(message["author"]).upper()
                    ),
                    "body": message["body"],
                    "timeLabel": format_timestamp(message.get("created_at")),
                }
                for message in messages
            )
        self.selectedBeaconThreadChanged.emit()

    @Slot(str, str)
    def createBeaconThread(self, subject: str, body: str) -> None:
        try:
            thread_id = create_human_thread(
                self.settings.db_path,
                subject=subject,
                body=body,
            )
            self._selected_beacon_thread = {"id": thread_id}
            self._load_events()
            self._load_beacon_threads(preserve_selection=True)
            self._set_status(
                "Request saved locally and queued for Beacon.", "success"
            )
        except (LookupError, ValueError) as error:
            self._set_status(str(error), "error")
        except Exception as error:
            LOGGER.exception("could not create Beacon thread")
            self._set_status(f"Could not save request: {error}", "error")

    @Slot(str)
    def replyToBeaconThread(self, body: str) -> None:
        thread_id = str(self._selected_beacon_thread.get("id") or "")
        if not thread_id:
            self._set_status("Select a Beacon conversation first.", "error")
            return
        try:
            reply_to_thread(self.settings.db_path, thread_id, body)
            self._load_events()
            self._load_beacon_threads(preserve_selection=True)
            self._set_status(
                "Reply saved locally and queued for Beacon. No file action was taken.",
                "success",
            )
        except (LookupError, ValueError) as error:
            self._set_status(str(error), "error")
        except Exception as error:
            LOGGER.exception("could not reply to Beacon thread")
            self._set_status(f"Could not save reply: {error}", "error")

    @Slot()
    def resolveBeaconThread(self) -> None:
        thread_id = str(self._selected_beacon_thread.get("id") or "")
        if not thread_id:
            self._set_status("Select a Beacon conversation first.", "error")
            return
        try:
            resolve_thread(self.settings.db_path, thread_id)
            self._load_events()
            self._load_beacon_threads(preserve_selection=False)
            self._set_status("Beacon conversation marked resolved.", "success")
        except (LookupError, ValueError) as error:
            self._set_status(str(error), "error")
        except Exception as error:
            LOGGER.exception("could not resolve Beacon thread")
            self._set_status(f"Could not resolve conversation: {error}", "error")

    @staticmethod
    def _asset_row(asset: dict[str, Any]) -> dict[str, Any]:
        kind = str(asset.get("kind") or "file")
        detail_bits = [
            bit
            for bit in (
                asset.get("codec"),
                asset.get("dimensions"),
                (
                    f"{asset['duration_seconds']:.1f}s"
                    if asset.get("duration_seconds") is not None
                    else None
                ),
            )
            if bit
        ]
        return {
            "assetId": asset["id"],
            "filename": asset["filename"],
            "displayTitle": (
                (asset.get("editable_metadata") or {}).get("display_title")
                or asset["filename"]
            ),
            "path": asset.get("primary_path") or "Location unavailable",
            "atlasUri": asset["atlas_uri"],
            "kind": kind,
            "kindLabel": kind.replace("_", " ").title(),
            "sizeLabel": format_bytes(asset.get("size_bytes")),
            "timeLabel": format_timestamp(asset.get("last_seen_at")),
            "metaLine": " · ".join(detail_bits) or "Ordinary file",
            "locationCount": int(asset.get("location_count") or 0),
            "thumbnailUrl": DesktopController._local_file_url(
                asset.get("thumbnail_path")
            ),
            "analyzed": bool(asset.get("analyzed")),
            "statusLabel": "Analyzed" if asset.get("analyzed") else "Cataloged",
        }

    @staticmethod
    def _local_file_url(value: object) -> str:
        if not value:
            return ""
        path = Path(str(value))
        if not path.is_file():
            return ""
        return QUrl.fromLocalFile(str(path)).toString()

    @Slot(str)
    def selectAsset(self, asset_id: str) -> None:
        self._select_asset(asset_id)

    def _select_asset(self, asset_id: str) -> None:
        detail = asset_detail(self.settings.db_path, asset_id)
        if detail is None:
            self._selected_asset = {}
        else:
            primary_path = Path(str(detail.get("primary_path") or ""))
            is_raw_photo = primary_path.suffix.lower() in RAW_PHOTO_EXTENSIONS
            if (
                is_raw_photo
                and primary_path.is_file()
                and not detail.get("thumbnail_path")
            ):
                try:
                    generated = ensure_thumbnail(
                        primary_path,
                        self.settings.db_path,
                        asset_id=str(detail["id"]),
                        source_sha256=str(detail["sha256"]),
                        media_metadata=detail.get("media_metadata"),
                    )
                    if generated is not None:
                        detail["thumbnail_path"] = generated.path
                except Exception:
                    LOGGER.exception(
                        "could not prepare RAW preview asset_id=%s",
                        asset_id,
                    )
            detail["sizeLabel"] = format_bytes(detail.get("size_bytes"))
            detail["lastSeenLabel"] = format_timestamp(detail.get("last_seen_at"))
            detail["createdLabel"] = format_timestamp(detail.get("created_at"))
            detail["kindLabel"] = str(detail.get("kind") or "file").title()
            detail["durationLabel"] = (
                f"{detail['duration_seconds']:.1f} seconds"
                if detail.get("duration_seconds") is not None
                else "Not reported"
            )
            detail["codecLabel"] = detail.get("codec") or "Not reported"
            detail["dimensionsLabel"] = detail.get("dimensions") or "Not reported"
            detail["thumbnailUrl"] = self._local_file_url(
                detail.get("thumbnail_path")
            )
            preview_kind = str(detail.get("kind") or "file")
            if is_raw_photo and detail.get("thumbnailUrl"):
                preview_kind = "image"
            if preview_kind not in {"image", "video", "audio"}:
                preview_kind = "file"
                text_preview = read_text_preview(primary_path)
                if text_preview is not None:
                    preview_kind = "text"
                    detail["textPreview"] = text_preview.text
                    detail["textEncoding"] = text_preview.encoding
                    detail["textPreviewTruncated"] = text_preview.truncated
                    detail["textPreviewLabel"] = (
                        f"{text_preview.encoding} · "
                        f"{format_bytes(text_preview.size_bytes)}"
                        + (
                            " · Showing first 512 KB"
                            if text_preview.truncated
                            else " · Complete file"
                        )
                    )
            detail["previewKind"] = preview_kind
            suffix = Path(str(detail.get("primary_path") or "")).suffix
            detail["extensionLabel"] = (
                suffix.removeprefix(".")[:8].upper()
                or preview_kind[:4].upper()
                or "FILE"
            )
            detail["previewUrl"] = self._local_file_url(
                detail.get("primary_path")
            )
            if is_raw_photo and detail.get("thumbnailUrl"):
                detail["previewUrl"] = detail["thumbnailUrl"]
            detail["previewAvailable"] = bool(detail["previewUrl"])
            transcript = detail.get("transcript") or {}
            detail["transcript"] = {
                **transcript,
                "text": str(transcript.get("text") or ""),
                "languageLabel": str(
                    transcript.get("language") or "Unknown language"
                ).upper(),
                "generatorLabel": str(transcript.get("generator") or ""),
                "verifiedLabel": (
                    format_timestamp(transcript.get("verified_at"))
                    if transcript.get("verified_at") else ""
                ),
            }
            music = detail.get("music_analysis") or {}
            detail["musicAnalysis"] = (
                {
                    **music,
                    "confidenceLabel": (
                        f"{float(music.get('music_confidence') or 0):.0%}"
                    ),
                    "keyLabel": (
                        f"{music.get('key') or 'Unknown'} "
                        f"({float(music.get('key_confidence') or 0):.0%})"
                    ),
                    "bpmLabel": (
                        f"{float(music['bpm']):.1f} BPM"
                        if music.get("bpm") is not None
                        else "Unknown"
                    ),
                    "notesLabel": " Â· ".join(
                        (music.get("notes") or {}).get("prominent_notes") or []
                    ),
                    "pitchRangeLabel": (
                        (music.get("notes") or {}).get("pitch_range") or ""
                    ),
                    "chordsLabel": "  â†’  ".join(
                        item.get("chord") or ""
                        for item in (music.get("chords") or [])[:24]
                        if item.get("chord")
                    ),
                    "stemsLabel": " Â· ".join(
                        str(item.get("kind") or "").replace("music_stem_", "")
                        for item in music.get("stems") or []
                    ),
                    "verifiedLabel": format_timestamp(
                        music.get("verified_at")
                    ),
                }
                if music
                else {}
            )
            editable = empty_metadata()
            editable.update(detail.get("editable_metadata") or {})
            detail["catalogMetadata"] = {
                **editable,
                "tagsText": "\n".join(editable.get("tags") or []),
                "peopleText": "\n".join(editable.get("people") or []),
                "revision": int(detail.get("metadata_revision") or 0),
                "updatedBy": detail.get("metadata_updated_by") or "",
                "updatedLabel": format_timestamp(
                    detail.get("metadata_updated_at")
                )
                if detail.get("metadata_updated_at")
                else "Not edited yet",
            }
            detail["displayTitle"] = (
                editable.get("display_title") or detail.get("filename") or ""
            )
            detail["locations"] = [
                {
                    **location,
                    "observedLabel": format_timestamp(location.get("observed_at")),
                }
                for location in detail.get("locations", [])
            ]
            detail["events"] = [
                {
                    **event,
                    "timeLabel": format_timestamp(event.get("created_at")),
                }
                for event in detail.get("events", [])
            ]
            detail["moves"] = [
                {
                    **move,
                    "createdLabel": format_timestamp(move.get("created_at")),
                    "completedLabel": format_timestamp(move.get("completed_at"))
                    if move.get("completed_at")
                    else "",
                }
                for move in detail.get("moves", [])
            ]
            analysis = detail.get("analysis") or []
            if analysis:
                candidate = analysis[0]
                payload = candidate.get("payload") or {}
                provenance = candidate.get("provenance") or {}
                detail["analysisCandidate"] = {
                    "id": candidate.get("id") or "",
                    "title": payload.get("title") or "Untitled analysis",
                    "description": payload.get("description") or "",
                    "mediaCategory": payload.get("media_category") or "",
                    "tagsLabel": " · ".join(payload.get("tags") or []),
                    "privacyLabel": " · ".join(
                        payload.get("privacy_flags") or []
                    )
                    or "No privacy flag reported",
                    "organizationSuggestion": (
                        payload.get("organization_suggestion") or ""
                    ),
                    "verifiedFactsLabel": " · ".join(
                        provenance.get("verified_facts") or []
                    ),
                    "inferencesLabel": " · ".join(
                        provenance.get("inferences") or []
                    ),
                    "confidenceLabel": (
                        f"{float(candidate.get('confidence') or 0):.0%}"
                    ),
                    "reviewStateLabel": str(
                        candidate.get("review_state") or "candidate"
                    ).upper(),
                    "analyzerLabel": (
                        f"{candidate.get('analyzer') or 'Beacon'} · "
                        f"{candidate.get('analyzer_version') or 'unversioned'}"
                    ),
                    "policyLabel": candidate.get("policy_version") or "",
                    "executionLabel": (
                        f"{candidate.get('execution_location') or 'Unknown'}"
                        + (
                            " · EXTERNAL INFERENCE"
                            if candidate.get("external_inference")
                            else " · LOCAL INFERENCE"
                        )
                    ),
                    "createdLabel": format_timestamp(
                        candidate.get("created_at")
                    ),
                }
            else:
                detail["analysisCandidate"] = {}
            self._selected_asset = detail
        self.selectedAssetChanged.emit()

    @Slot("QVariantMap")
    def saveSelectedAssetMetadata(self, value: dict[str, Any]) -> None:
        asset_id = str(self._selected_asset.get("id") or "")
        if not asset_id:
            self._set_status("Select an asset before editing metadata.", "error")
            return
        try:
            payload = dict(value)
            payload["tags"] = str(payload.pop("tagsText", "")).splitlines()
            payload["people"] = str(payload.pop("peopleText", "")).splitlines()
            saved = save_asset_metadata(
                self.settings.db_path,
                asset_id,
                payload,
                updated_by="human",
                source="native_editor",
            )
            self._load_events()
            self._load_assets(preserve_selection=True)
            self._set_status(
                (
                    "Metadata was already current."
                    if saved["unchanged"]
                    else f"Editable metadata saved as revision {saved['revision']}."
                ),
                "success",
            )
        except (LookupError, ValueError) as error:
            self._set_status(str(error), "error")
        except Exception as error:
            LOGGER.exception("could not save editable metadata")
            self._set_status(f"Could not save metadata: {error}", "error")

    @Slot(str, str)
    def moveSelectedAsset(
        self,
        source_path: str,
        destination_directory: str,
    ) -> None:
        if self._busy:
            return
        asset_id = str(self._selected_asset.get("id") or "")
        if not asset_id:
            self._set_status("Select an asset before moving a file.", "error")
            return
        self._busy = True
        self.busyChanged.emit()
        self._set_status(
            "Verifying source checksum before the managed move…",
            "working",
        )
        worker = _MoveWorker(
            self.settings.db_path,
            asset_id,
            Path(source_path),
            Path(destination_directory),
        )
        self._workers.append(worker)
        worker.signals.succeeded.connect(
            lambda result, current=worker: self._move_succeeded(current, result)
        )
        worker.signals.failed.connect(
            lambda message, current=worker: self._move_failed(current, message)
        )
        self._thread_pool.start(worker)

    def _move_succeeded(
        self,
        worker: _MoveWorker,
        result: MoveResult,
    ) -> None:
        self._finish_worker(worker)
        self._set_status(
            f"Verified managed move complete · {Path(result.destination_path).name}",
            "success",
        )
        self.refresh()

    def _move_failed(self, worker: _MoveWorker, message: str) -> None:
        self._finish_worker(worker)
        self._set_status(f"Managed move failed: {message}", "error")

    @Slot()
    def createBackup(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.busyChanged.emit()
        self._set_status("Creating and verifying a recovery copy…", "working")
        worker = _BackupWorker(self.settings.db_path, self.settings.backup_dir)
        self._workers.append(worker)
        worker.signals.succeeded.connect(
            lambda result, current=worker: self._backup_succeeded(current, result)
        )
        worker.signals.failed.connect(
            lambda message, current=worker: self._backup_failed(current, message)
        )
        self._thread_pool.start(worker)

    def _backup_succeeded(
        self, worker: _BackupWorker, result: BackupResult
    ) -> None:
        self._finish_worker(worker)
        self._set_status(
            f"Verified backup created · {Path(result.path).name}",
            "success",
        )
        LOGGER.info("verified backup created %s", asdict(result))
        self.refresh()

    def _backup_failed(self, worker: _BackupWorker, message: str) -> None:
        self._finish_worker(worker)
        self._set_status(f"Backup failed: {message}", "error")

    def _finish_worker(self, worker: QRunnable) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        self._busy = False
        self.busyChanged.emit()

    def _set_status(self, message: str, kind: str) -> None:
        self._status_message = message
        self._status_kind = kind
        self.statusChanged.emit()

    @Slot()
    def clearStatus(self) -> None:
        self._set_status("", "neutral")

    @Slot()
    def shutdown(self) -> None:
        """Pause intake work and let the current verified file operation finish."""
        for worker in tuple(self._workers):
            if isinstance(worker, _IntakeRunWorker):
                try:
                    pause_intake_job(self.settings.db_path, worker.job_id)
                except Exception:
                    LOGGER.exception("could not pause intake during shutdown")
            elif isinstance(worker, _LocalAnalysisWorker):
                try:
                    request_local_analysis_cancel(
                        self.settings.db_path, worker.job_id
                    )
                except Exception:
                    LOGGER.exception(
                        "could not cancel local analysis during shutdown"
                    )
        if self._thread_pool.activeThreadCount():
            LOGGER.info("waiting for in-flight desktop work before shutdown")
            self._thread_pool.waitForDone()

    @Slot(str)
    def copyText(self, value: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(value)
            self._set_status("Copied to clipboard.", "success")

    @Slot(str)
    def openFolder(self, value: str) -> None:
        path = Path(value)
        target = path if path.is_dir() else path.parent
        if not target.exists():
            self._set_status(f"Folder is unavailable: {target}", "error")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            self._set_status(f"Windows could not open: {target}", "error")
