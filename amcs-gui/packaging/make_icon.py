"""
Render the AMCS app icon (1024×1024 PNG) with Qt — no external artwork.

    python packaging/make_icon.py packaging/amcs.png

On macOS the build script turns the PNG into AMCS.icns with sips + iconutil.
"""
import math
import sys

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QPainter, QPainterPath,
                         QPen, QPolygonF, QRadialGradient)


def render(path: str, size: int = 1024) -> None:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 1024.0

    # Rounded-square plate (macOS icon grid: ~824 px body with margin)
    body = QRectF(100 * s, 100 * s, 824 * s, 824 * s)
    grad = QRadialGradient(QPointF(512 * s, 440 * s), 560 * s)
    grad.setColorAt(0.0, QColor("#1A2F45"))
    grad.setColorAt(1.0, QColor("#0A1622"))
    plate = QPainterPath()
    plate.addRoundedRect(body, 185 * s, 185 * s)
    p.fillPath(plate, QBrush(grad))
    p.setPen(QPen(QColor("#2471A3"), 10 * s))
    p.drawPath(plate)

    c = QPointF(512 * s, 512 * s)
    # Radar range rings
    for r, a in ((330, 90), (230, 70), (130, 60)):
        p.setPen(QPen(QColor(128, 203, 196, a), 6 * s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, r * s, r * s)

    # Restricted zone hexagon
    hexa = QPolygonF([QPointF(c.x() + 190 * s * math.sin(math.radians(30 + 60 * k)),
                              c.y() - 190 * s * math.cos(math.radians(30 + 60 * k))) for k in range(6)])
    p.setBrush(QColor(239, 83, 80, 55))
    p.setPen(QPen(QColor("#EF5350"), 12 * s))
    p.drawPolygon(hexa)

    # Radar sweep wedge
    sweep = QPainterPath(c)
    sweep.arcTo(QRectF(c.x() - 330 * s, c.y() - 330 * s, 660 * s, 660 * s), 20, 40)
    sweep.closeSubpath()
    p.fillPath(sweep, QColor(76, 175, 80, 90))

    # Protected asset diamond
    d = 48 * s
    p.setBrush(QColor("#FFD54F"))
    p.setPen(QPen(QColor("#000000"), 5 * s))
    p.drawPolygon(QPolygonF([QPointF(c.x(), c.y() - d), QPointF(c.x() + d * 0.85, c.y()),
                             QPointF(c.x(), c.y() + d), QPointF(c.x() - d * 0.85, c.y())]))

    # Hostile drone track (red diamond) with velocity leader toward the zone
    t = QPointF(c.x() + 250 * s, c.y() - 235 * s)
    p.setPen(QPen(QColor("#F44336"), 12 * s))
    p.drawLine(t, QPointF(t.x() - 110 * s, t.y() + 100 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    k = 40 * s
    p.drawPolygon(QPolygonF([QPointF(t.x(), t.y() - k), QPointF(t.x() + k, t.y()),
                             QPointF(t.x(), t.y() + k), QPointF(t.x() - k, t.y())]))
    p.end()
    if not img.save(path):
        raise SystemExit(f"could not write {path}")


if __name__ == "__main__":
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1] + ["-platform", "offscreen"])
    render(sys.argv[1] if len(sys.argv) > 1 else "amcs.png")
