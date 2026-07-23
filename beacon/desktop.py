from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QMetaObject, QTimer, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer  # noqa: F401
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .desktop_controller import DesktopController, DesktopSettings

DEFAULT_RUNTIME = (
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "ATLAS" / "Beacon"
)


def _catalog_label(path: Path) -> str:
    resolved = path.resolve()
    if resolved == (DEFAULT_RUNTIME / "beacon.db").resolve():
        return "Live catalog"
    if "use-tests" in {part.lower() for part in resolved.parts}:
        return "Isolated use test"
    return "Custom catalog"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="beacon-desktop")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("BEACON_DB", DEFAULT_RUNTIME / "beacon.db")),
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path(
            os.environ.get("BEACON_BACKUP_DIR", DEFAULT_RUNTIME / "backups")
        ),
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_RUNTIME / "logs" / "beacon-desktop.log",
    )
    parser.add_argument(
        "--view",
        choices=("overview", "library", "operations", "system"),
        default="overview",
    )
    parser.add_argument(
        "--asset-id",
        help="select an asset before showing the interface",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="open the selected asset in the temporary preview",
    )
    parser.add_argument(
        "--mute-preview",
        action="store_true",
        help="mute preview playback (useful for automated visual checks)",
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="capture the rendered desktop window, then exit",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="load the native interface, then exit",
    )
    return parser


def _configure_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.FileHandler(path, encoding="utf-8"),
    ]
    if not getattr(sys, "frozen", False):
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"ATLAS.Beacon.{__version__}"
        )
    except (AttributeError, OSError):
        logging.getLogger("beacon.desktop").debug(
            "Windows application ID was unavailable", exc_info=True
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _configure_logging(args.log_file)
    _set_windows_app_id()
    logger = logging.getLogger("beacon.desktop")
    logger.info("starting ATLAS Beacon %s", __version__)

    QQuickStyle.setStyle("Fusion")
    app = QApplication([sys.argv[0]])
    app.setApplicationName("ATLAS Beacon")
    app.setApplicationDisplayName("ATLAS Beacon")
    app.setOrganizationName("ATLAS")
    app.setApplicationVersion(__version__)

    qml_dir = Path(__file__).resolve().parent / "qml"
    icon_path = qml_dir / "assets" / "beacon.svg"
    app.setWindowIcon(QIcon(str(icon_path)))

    controller = DesktopController(
        DesktopSettings(
            db_path=args.db.resolve(),
            backup_dir=args.backup_dir.resolve(),
            catalog_label=_catalog_label(args.db),
        )
    )
    app.aboutToQuit.connect(controller.shutdown)
    controller.setCurrentView(args.view)
    if args.asset_id:
        controller.selectAsset(args.asset_id)

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", controller)
    engine.rootContext().setContextProperty("previewMuted", args.mute_preview)
    qml_path = qml_dir / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        message = f"The Beacon interface could not be loaded:\n{qml_path}"
        logger.error(message)
        QMessageBox.critical(None, "ATLAS Beacon", message)
        return 2

    root = engine.rootObjects()[0]
    if args.preview:
        QTimer.singleShot(
            300,
            lambda: QMetaObject.invokeMethod(root, "openSelectedPreview"),
        )

    if args.screenshot:
        destination = args.screenshot.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        def capture() -> None:
            image = root.grabWindow()
            if image.isNull() or not image.save(str(destination)):
                logger.error("could not capture native window to %s", destination)
                app.exit(3)
                return
            logger.info("captured native window to %s", destination)
            app.exit(0)

        QTimer.singleShot(2200 if args.preview else 1500, capture)
    elif args.smoke_test:
        QTimer.singleShot(350, lambda: app.exit(0))

    result = app.exec()
    logger.info("ATLAS Beacon stopped with exit code %s", result)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
