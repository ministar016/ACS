"""
MiniMap — shows the real OpenStreetMap tile for the tactical field location.

The tile is fetched (or loaded from cache) in a background QThread so it
never blocks the UI.  A crosshair is drawn over the scene centre.

© OpenStreetMap contributors — ODbL licence.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore    import Qt, QThread, QObject, pyqtSignal
from PyQt6.QtGui     import QPixmap, QPainter, QPen, QColor, QFont

from sim.terrain_real import CENTER_LAT, CENTER_LON
from .palette         import PANEL, BORDER, DIM, ACCENT

_MAP_W = 248
_MAP_H = 200


class _TileFetcher(QObject):
    done   = pyqtSignal(bytes)
    failed = pyqtSignal()

    def run(self) -> None:
        from sim.terrain_real import get_osm_tile_bytes
        data = get_osm_tile_bytes()
        if data:
            self.done.emit(data)
        else:
            self.failed.emit()


class MiniMap(QWidget):
    """Fixed-width OSM minimap panel (248 × ~236 px)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(_MAP_W)
        self.setStyleSheet(f"background: {PANEL};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        hdr = QLabel("  LOCATION  ·  OSM")
        hdr.setStyleSheet(
            f"background: #091420; color: {DIM}; padding: 5px 8px;"
            f" font-size: 10px; letter-spacing: 1px;"
            f" border-top: 1px solid {BORDER}; border-bottom: 1px solid {BORDER};"
        )
        lay.addWidget(hdr)

        # Map image label
        self._img = QLabel("Loading map…")
        self._img.setFixedSize(_MAP_W, _MAP_H)
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setStyleSheet(f"color: {DIM}; font-size: 10px; background: #060D18;")
        lay.addWidget(self._img)

        # Coordinate footer
        foot = QLabel(f"  {CENTER_LAT:.5f} °N    {CENTER_LON:.5f} °E")
        foot.setStyleSheet(
            f"background: #091420; color: {ACCENT}; padding: 4px 8px;"
            f" font-size: 10px; font-family: 'Liberation Mono', monospace;"
            f" border-top: 1px solid {BORDER};"
        )
        lay.addWidget(foot)

        # Attribution
        attr = QLabel("  © OpenStreetMap contributors")
        attr.setStyleSheet(
            f"background: #060D18; color: {DIM}; padding: 2px 6px;"
            f" font-size: 9px;"
        )
        lay.addWidget(attr)

        # Async tile fetch
        self._thread = QThread()
        self._worker = _TileFetcher()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_loaded)
        self._worker.failed.connect(self._on_failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_loaded(self, data: bytes) -> None:
        pm = QPixmap()
        pm.loadFromData(data)

        # Scale to fill _MAP_W × _MAP_H, then crop centre
        pm = pm.scaled(
            _MAP_W, _MAP_H,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        ox = max(0, (pm.width()  - _MAP_W) // 2)
        oy = max(0, (pm.height() - _MAP_H) // 2)
        pm = pm.copy(ox, oy, _MAP_W, _MAP_H)

        # Draw crosshair at field centre
        cx, cy = _MAP_W // 2, _MAP_H // 2
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Halo
        pen_halo = QPen(QColor(0, 0, 0, 140))
        pen_halo.setWidth(3)
        p.setPen(pen_halo)
        p.drawLine(cx - 14, cy, cx + 14, cy)
        p.drawLine(cx, cy - 14, cx, cy + 14)

        # Bright accent lines
        pen = QPen(QColor(ACCENT))
        pen.setWidth(1)
        p.setPen(pen)
        p.drawLine(cx - 14, cy, cx + 14, cy)
        p.drawLine(cx, cy - 14, cx, cy + 14)
        p.drawEllipse(cx - 5, cy - 5, 10, 10)

        # "100 m" scale box
        scale_px = int(_MAP_W * 0.15)   # approximate pixel width for 100 m at zoom 16
        p.drawLine(10, _MAP_H - 8, 10 + scale_px, _MAP_H - 8)
        font = QFont("Liberation Mono", 7)
        p.setFont(font)
        p.drawText(10, _MAP_H - 10, "100 m")

        p.end()
        self._img.setPixmap(pm)
        self._img.setStyleSheet("background: #060D18;")

    def _on_failed(self) -> None:
        self._img.setText("Map unavailable\n(network error or offline)")
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
