"""
TopBar — top status bar with simulation KPIs and time-scale controls.

Shows:
  • Live wall-clock time & date
  • Simulation time (T+ seconds)
  • Entity counts (ROVERS / SENSORS / contacts)
  • Time-scale selector (×1 … ×20 push-buttons)
  • Field identifier label
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore    import Qt, QTimer
from typing          import Callable

from sim.terrain  import TerrainMap
from sim.terrain_real import CENTER_LAT, CENTER_LON
from .palette     import (
    BORDER, DIM, TEXT, ACCENT, ACTIVE, ALERT_COL, WARN,
    ROVER_COL, SENSOR_COL, INTRUDER,
)

from sim.scenario import ScenarioSnapshot
from sim.entities import EntityType, EntityStatus

_TIMESCALES = (1, 2, 5, 10, 20)


class _Chip(QFrame):
    """A small label|value pair."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: #091420; border: 1px solid {BORDER};"
            f" border-radius: 3px; padding: 0 6px; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 1, 4, 1)
        lay.setSpacing(5)

        self._key = QLabel(label)
        self._key.setStyleSheet(f"color: {DIM}; font-size: 10px; font-weight: bold;")
        lay.addWidget(self._key)

        self._val = QLabel("—")
        self._val.setStyleSheet(f"color: {TEXT}; font-size: 11px;")
        lay.addWidget(self._val)

    def setValue(self, txt: str, color: str = TEXT) -> None:
        self._val.setText(txt)
        self._val.setStyleSheet(f"color: {color}; font-size: 11px;")


class TopBar(QWidget):
    """Full-width top bar (~52 px tall)."""

    def __init__(self, on_scale_change: Callable[[int], None],
                 terrain=None, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet(
            f"background: #070D16; border-bottom: 1px solid {BORDER};"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        # Left: title block
        title = QLabel("FIELD-3D")
        title.setStyleSheet(
            f"color: {ACCENT}; font-size: 18px; font-weight: bold;"
            f" font-family: 'Liberation Sans', sans-serif;"
        )
        lay.addWidget(title)

        sub = QLabel(f"{CENTER_LAT:.4f}°N  {CENTER_LON:.4f}°E  ·  100×100 m")
        sub.setStyleSheet(f"color: {DIM}; font-size: 10px;")
        lay.addWidget(sub)

        lay.addStretch(1)

        # KPI chips
        self._chip_t   = _Chip("T+")
        self._chip_ent = _Chip("ENTITIES")
        self._chip_det = _Chip("CONTACTS")
        for c in (self._chip_t, self._chip_ent, self._chip_det):
            lay.addWidget(c)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {BORDER};")
        lay.addWidget(sep)

        # Time-scale buttons
        spd_lbl = QLabel("SPEED")
        spd_lbl.setStyleSheet(f"color: {DIM}; font-size: 10px;")
        lay.addWidget(spd_lbl)

        self._scale_btns: dict[int, QPushButton] = {}
        self._current_scale = 1
        for ts in _TIMESCALES:
            btn = QPushButton(f"{ts}×")
            btn.setFixedSize(34, 24)
            btn.setCheckable(True)
            btn.setStyleSheet(self._btn_style(active=(ts == 1)))
            btn.clicked.connect(lambda _, s=ts: self._on_scale(s, on_scale_change))
            self._scale_btns[ts] = btn
            lay.addWidget(btn)

        self._scale_btns[1].setChecked(True)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet(f"color: {BORDER};")
        lay.addWidget(sep2)

        # Clock
        self._clock = QLabel("--:--:--")
        self._clock.setStyleSheet(
            f"color: #FFFFFF; font-size: 16px; font-weight: bold;"
            f" font-family: 'Liberation Mono', monospace;"
        )
        lay.addWidget(self._clock)

        # Wall-clock refresh
        self._wtimer = QTimer(self)
        self._wtimer.setInterval(1000)
        self._wtimer.timeout.connect(self._tick_clock)
        self._wtimer.start()
        self._tick_clock()

    # ── public ────────────────────────────────────────────────────────────────

    def update_snapshot(self, snap: ScenarioSnapshot) -> None:
        self._chip_t.setValue(f"{snap.t:.1f} s", WARN)

        n_total   = len(snap.entities)
        n_alerts  = sum(1 for e in snap.entities if e.status == EntityStatus.ALERT)
        self._chip_ent.setValue(str(n_total))
        self._chip_det.setValue(
            str(n_alerts),
            ALERT_COL if n_alerts > 0 else DIM,
        )

    # ── private ───────────────────────────────────────────────────────────────

    def _tick_clock(self) -> None:
        from datetime import datetime
        self._clock.setText(datetime.now().strftime("%H:%M:%S"))

    def _on_scale(self, scale: int, callback: Callable[[int], None]) -> None:
        self._current_scale = scale
        for ts, btn in self._scale_btns.items():
            btn.setChecked(ts == scale)
            btn.setStyleSheet(self._btn_style(active=(ts == scale)))
        callback(scale)

    @staticmethod
    def _btn_style(active: bool) -> str:
        if active:
            return (f"QPushButton {{ background: {ACCENT}; color: #FFFFFF;"
                    f" border: 1px solid #64C8F0; border-radius: 3px; font-weight: bold; }}")
        return (f"QPushButton {{ background: #0D1B2A; color: {DIM};"
                f" border: 1px solid {BORDER}; border-radius: 3px; }}"
                f"QPushButton:hover {{ background: #1A3A55; border-color: {ACCENT}; }}")
