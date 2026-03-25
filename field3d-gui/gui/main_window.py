"""
MainWindow — assembles all panels into a single QMainWindow.

Layout
──────
┌───────────────────────────────────────────────────────────────┐
│                        TOP BAR  (52 px)                       │
├─────────────────┬─────────────────────────┬───────────────────┤
│  EntityPanel    │   Field3DView           │  AlertLog         │
│  (248 px fixed) │   (fills remaining)     │  (264 px fixed)   │
│                 │                         │                   │
└─────────────────┴─────────────────────────┴───────────────────┘
"""
from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout
from PyQt6.QtCore    import Qt

from sim.bus          import SimBus
from sim.terrain      import TerrainMap
from .top_bar         import TopBar
from .entity_panel    import EntityPanel
from .field3d_view    import Field3DView
from .alert_log       import AlertLog
from .minimap         import MiniMap
from .palette         import BG, BASE_SS


class MainWindow(QMainWindow):
    def __init__(self, bus: SimBus, terrain: TerrainMap) -> None:
        super().__init__()
        self._bus     = bus
        self._terrain = terrain

        self.setWindowTitle("Field-3D — Haar, Munich  48.2320°N 11.6088°E  ·  100×100 m")
        self.resize(1280, 820)
        self.setMinimumSize(960, 640)

        # Apply global stylesheet
        self.setStyleSheet(BASE_SS)

        # ── panel widgets ──────────────────────────────────────────────────
        self._view    = Field3DView(terrain)
        self._ent_p   = EntityPanel()
        self._alerts  = AlertLog()
        self._topbar  = TopBar(on_scale_change=bus.setTimeScale,
                               terrain=terrain)
        self._minimap = MiniMap()

        # ── assemble: left col = entity panel + minimap ───────────────────
        left_col = QWidget()
        left_lay = QVBoxLayout(left_col)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)
        left_lay.addWidget(self._ent_p, stretch=1)
        left_lay.addWidget(self._minimap)

        centre = QWidget()
        centre.setObjectName("centreWidget")
        h_lay = QHBoxLayout(centre)
        h_lay.setContentsMargins(0, 0, 0, 0)
        h_lay.setSpacing(1)
        h_lay.addWidget(left_col)
        h_lay.addWidget(self._view, stretch=1)
        h_lay.addWidget(self._alerts)

        root = QWidget()
        v_lay = QVBoxLayout(root)
        v_lay.setContentsMargins(0, 0, 0, 0)
        v_lay.setSpacing(0)
        v_lay.addWidget(self._topbar)
        v_lay.addWidget(centre, stretch=1)

        self.setCentralWidget(root)

        # ── connect simulation ─────────────────────────────────────────────
        bus.snapshotReady.connect(self._on_snapshot)

    # ── slot ──────────────────────────────────────────────────────────────────

    def _on_snapshot(self) -> None:
        snap = self._bus.last_snapshot
        if snap is None:
            return
        self._topbar.update_snapshot(snap)
        self._ent_p.update_snapshot(snap)
        self._alerts.update_snapshot(snap)
        self._view.update_snapshot(snap)
