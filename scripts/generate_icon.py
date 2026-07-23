from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    source = script_dir.parent / "beacon" / "qml" / "assets" / "beacon.svg"
    destination = script_dir / "beacon.ico"

    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise SystemExit(f"Could not load application icon: {source}")
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, 256, 256))
    painter.end()
    if not image.save(str(destination), "ICO"):
        raise SystemExit(f"Could not generate Windows icon: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
