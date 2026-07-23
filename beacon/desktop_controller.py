from __future__ import annotations

import logging
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
from .desktop_models import DictListModel
from .repository import asset_detail, catalog_summary, recent_events, search_assets

LOGGER = logging.getLogger("beacon.desktop")


@dataclass(frozen=True)
class DesktopSettings:
    db_path: Path
    backup_dir: Path


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


class DesktopController(QObject):
    summaryChanged = Signal()
    databaseHealthChanged = Signal()
    selectedAssetChanged = Signal()
    currentViewChanged = Signal()
    searchQueryChanged = Signal()
    busyChanged = Signal()
    statusChanged = Signal()
    lastRefreshChanged = Signal()

    def __init__(self, settings: DesktopSettings) -> None:
        super().__init__()
        self.settings = settings
        self._summary: dict[str, Any] = {}
        self._database_health: dict[str, Any] = {}
        self._selected_asset: dict[str, Any] = {}
        self._current_view = "overview"
        self._search_query = ""
        self._busy = False
        self._status_message = ""
        self._status_kind = "neutral"
        self._last_refresh = ""
        self._workers: list[_BackupWorker] = []
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)

        self._assets = DictListModel(
            (
                "assetId",
                "filename",
                "path",
                "atlasUri",
                "kind",
                "kindLabel",
                "sizeLabel",
                "timeLabel",
                "metaLine",
                "locationCount",
                "thumbnailUrl",
            )
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

        self.settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.backup_dir.mkdir(parents=True, exist_ok=True)
        with connect(self.settings.db_path) as connection:
            migrate(connection)
        self.refresh()

    @Property(QObject, constant=True)
    def assets(self) -> QObject:
        return self._assets

    @Property(QObject, constant=True)
    def events(self) -> QObject:
        return self._events

    @Property(QObject, constant=True)
    def backups(self) -> QObject:
        return self._backups

    @Property("QVariantMap", notify=summaryChanged)
    def summary(self) -> dict[str, Any]:
        return self._summary

    @Property("QVariantMap", notify=databaseHealthChanged)
    def databaseHealth(self) -> dict[str, Any]:
        return self._database_health

    @Property("QVariantMap", notify=selectedAssetChanged)
    def selectedAsset(self) -> dict[str, Any]:
        return self._selected_asset

    @Property(str, notify=currentViewChanged)
    def currentView(self) -> str:
        return self._current_view

    @Property(str, notify=searchQueryChanged)
    def searchQuery(self) -> str:
        return self._search_query

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
    def applicationVersion(self) -> str:
        return __version__

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
            self._last_refresh = datetime.now().astimezone().strftime("%I:%M:%S %p")
            self.lastRefreshChanged.emit()
        except Exception as error:
            LOGGER.exception("desktop refresh failed")
            self._set_status(f"Could not refresh Beacon: {error}", "error")

    def _load_assets(self, *, preserve_selection: bool) -> None:
        current_id = self._selected_asset.get("id") if preserve_selection else None
        result = search_assets(
            self.settings.db_path,
            query=self._search_query,
            limit=100,
        )
        rows = [self._asset_row(item) for item in result["items"]]
        self._assets.replace(rows)
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
            if preview_kind not in {"image", "video", "audio"}:
                preview_kind = "file"
            detail["previewKind"] = preview_kind
            detail["previewUrl"] = self._local_file_url(
                detail.get("primary_path")
            )
            detail["previewAvailable"] = bool(detail["previewUrl"])
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
            self._selected_asset = detail
        self.selectedAssetChanged.emit()

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

    def _finish_worker(self, worker: _BackupWorker) -> None:
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
        """Let an in-flight verified backup finish before the process exits."""
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
