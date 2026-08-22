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

from . import __version__, config
from .desktop_controller import DesktopController, DesktopSettings

DEFAULT_RUNTIME = (
    config.runtime_root()
)


def _catalog_label(path: Path) -> str:
    resolved = path.resolve()
    configured = config.resolve_catalog_path()
    if configured is not None and resolved == Path(configured).resolve():
        return "Live catalog"
    if "use-tests" in {part.lower() for part in resolved.parts}:
        return "Isolated use test"
    return "Custom catalog"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="beacon-desktop")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--initialize",
        action="store_true",
        help=(
            "create a new empty catalog when none exists at the resolved "
            "location; without this Beacon refuses and asks"
        ),
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=config.runtime_log_dir() / "beacon-desktop.log",
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


def _resolve_catalog(args, logger) -> tuple[Path, Path] | None:
    """Resolve the catalog, or return None after showing the ask state.

    Beacon never invents a catalog. If no location is configured, or the
    configured location holds no catalog and the operator did not explicitly
    ask to create one, this reports what is missing and refuses to continue.
    Silently creating an empty database makes a broken configuration look
    healthy, which is the failure this gate exists to prevent.
    """
    explicit = args.db is not None
    db = Path(args.db) if explicit else config.resolve_catalog_path()
    if db is None:
        logger.error("no catalog configured")
        _ask(config.catalog_advice(), args.smoke_test)
        return None
    db = Path(db)
    # An explicit --db is the operator naming a location, so creating it there
    # is their intent; that is how isolated and use-test catalogs have always
    # worked. The gate guards the CONFIGURED default, which is where a silently
    # created empty catalog would masquerade as the live one.
    if not db.is_file() and not explicit and not args.initialize:
        message = (
            "Beacon found no catalog at the configured location:"
            + chr(10) + chr(10)
            + f"    {db}"
            + chr(10) + chr(10)
            + "Beacon will not create an empty catalog here, because an empty "
            "catalog looks healthy and hides the real problem."
            + chr(10) + chr(10)
            + "Check that the archive volume is connected and that "
            f"{config.ARCHIVE_ROOT_SETTING} in"
            + chr(10)
            + f"    {config.settings_path()}"
            + chr(10)
            + "names the right location."
            + chr(10) + chr(10)
            + "To create a new catalog here deliberately, start Beacon with "
            "--initialize."
        )
        logger.error("catalog missing at %s", db)
        _ask(message, args.smoke_test)
        return None
    backup_dir = Path(args.backup_dir) if args.backup_dir else config.backups_dir()
    return db, backup_dir


def _ask(message: str, headless: bool = False) -> None:
    """Blocking, non-dismissable state: the only way on is to quit."""
    if headless:
        print(message, file=sys.stderr, flush=True)
        return
    box = QMessageBox()
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle("ATLAS Beacon - catalog not found")
    box.setText("Beacon cannot open its catalog.")
    box.setInformativeText(message)
    box.setStandardButtons(QMessageBox.Close)
    box.setDefaultButton(QMessageBox.Close)
    box.exec()


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

    resolved = _resolve_catalog(args, logger)
    if resolved is None:
        return 2
    db_path, backup_dir = resolved
    controller = DesktopController(
        DesktopSettings(
            db_path=db_path.resolve(),
            backup_dir=backup_dir.resolve(),
            catalog_label=_catalog_label(db_path),
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
