"""
SimBus — Qt signal bridge between Scenario and FieldWindow.

A QTimer fires every dt seconds (100 ms → 10 Hz physics); on each timeout
the scenario is stepped _time_scale times, the latest snapshot is stored, and
a snapshotReady signal is emitted every emit_every ticks (~3 Hz GUI rate).

The window reads self.last_snapshot on the signal callback instead of
receiving the full NumPy arrays through Qt signals, which avoids the
overhead of marshalling large arrays through the Qt type system.
"""
from __future__ import annotations
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from .scenario import Scenario, ScenarioSnapshot


class SimBus(QObject):
    snapshotReady = pyqtSignal()   # fires when a new snapshot is ready

    def __init__(self, dt: float = 0.1, emit_every: int = 3,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dt          = dt
        self._scenario    = Scenario(dt=dt)
        self._timer       = QTimer(self)
        self._timer.setInterval(int(dt * 1000))   # ms
        self._timer.timeout.connect(self._tick)
        self._emit_every  = emit_every
        self._tick_n      = 0
        self._time_scale  = 1
        self._last_snap: ScenarioSnapshot | None = None

    # ── public API ────────────────────────────────────────────────────────

    @property
    def last_snapshot(self) -> ScenarioSnapshot | None:
        return self._last_snap

    @pyqtSlot()
    def start(self) -> None:
        self._timer.start()

    @pyqtSlot()
    def stop(self) -> None:
        self._timer.stop()

    @pyqtSlot()
    def reset(self) -> None:
        self._timer.stop()
        self._scenario  = Scenario(dt=self._dt)
        self._tick_n    = 0
        self._last_snap = None
        self._timer.start()

    @pyqtSlot(int)
    def setTimeScale(self, scale: int) -> None:
        self._time_scale = max(1, min(50, scale))

    # ── private ───────────────────────────────────────────────────────────

    def _tick(self) -> None:
        # Run _time_scale scenario steps per timer fire
        snap: ScenarioSnapshot | None = None
        for _ in range(self._time_scale):
            snap = self._scenario.step()
        self._last_snap = snap
        self._tick_n   += 1
        if self._tick_n % self._emit_every == 0:
            self.snapshotReady.emit()
