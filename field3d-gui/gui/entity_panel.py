"""
EntityPanel — left sidebar showing live entity telemetry.

Displays a QTreeWidget with three top-level groups:
  ROVERS   — one row per rover (ID, status, position, battery)
  SENSORS  — one row per sensor (ID, status, amplitude, detection)
  INTRUDER — single row when the intruder is in the field

Refreshed on every SimBus snapshot via update_snapshot().
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QColor

from sim.scenario import ScenarioSnapshot
from sim.entities import EntityType, EntityStatus
from .palette     import (
    PANEL, BORDER, TEXT, DIM, ACCENT,
    ACTIVE, ALERT_COL, WARN, ROVER_COL, SENSOR_COL, INTRUDER,
)

_COL_HEADERS = ["ID", "STATUS", "X / Y", "DETAIL"]
_COL_W       = [100, 68, 80, 90]

_STATUS_COLORS = {
    EntityStatus.ACTIVE:  ACTIVE,
    EntityStatus.ALERT:   ALERT_COL,
    EntityStatus.STANDBY: WARN,
    EntityStatus.OFFLINE: DIM,
}

_TYPE_COLORS = {
    EntityType.ROVER:    ROVER_COL,
    EntityType.SENSOR:   SENSOR_COL,
    EntityType.INTRUDER: INTRUDER,
}


class EntityPanel(QWidget):
    """Styled entity telemetry panel (~240 px wide)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(248)
        self.setStyleSheet(f"background: {PANEL};")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Header
        hdr = QLabel("  FIELD ENTITIES")
        hdr.setStyleSheet(
            f"background: #091420; color: {DIM}; padding: 6px 8px;"
            f" font-size: 10px; letter-spacing: 1px;"
            f" border-bottom: 1px solid {BORDER};"
        )
        root_layout.addWidget(hdr)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(_COL_HEADERS))
        self._tree.setHeaderLabels(_COL_HEADERS)
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setExpandsOnDoubleClick(False)
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background: #091420; color: {TEXT}; border: none;"
            f"  font-size: 11px; alternate-background-color: #0D1B2A; }}"
            f"QTreeWidget::item:selected {{ background: {ACCENT}; color: #FFF; }}"
            f"QHeaderView::section {{ background: #0D1B2A; color: {DIM};"
            f"  border: none; border-bottom: 1px solid {BORDER};"
            f"  padding: 3px 4px; font-size: 10px; }}"
        )
        for i, w in enumerate(_COL_W):
            self._tree.setColumnWidth(i, w)
        root_layout.addWidget(self._tree)

        # Create group items
        self._grp = {
            EntityType.ROVER:    QTreeWidgetItem(self._tree, ["ROVERS",   "", "", ""]),
            EntityType.SENSOR:   QTreeWidgetItem(self._tree, ["SENSORS",  "", "", ""]),
            EntityType.INTRUDER: QTreeWidgetItem(self._tree, ["INTRUDER", "", "", ""]),
        }
        for etype, grp in self._grp.items():
            grp.setForeground(0, QColor(_TYPE_COLORS[etype]))
            grp.setExpanded(True)

        # Per-entity child rows (keyed by eid)
        self._rows: dict[str, QTreeWidgetItem] = {}

    # ── public ────────────────────────────────────────────────────────────────

    def update_snapshot(self, snap: ScenarioSnapshot) -> None:
        for ent in snap.entities:
            row = self._rows.get(ent.eid)
            if row is None:
                row = QTreeWidgetItem(self._grp[ent.etype])
                self._rows[ent.eid] = row

            status_str = ent.status.value
            pos_str    = f"{ent.x:.1f},{ent.y:.1f}"
            detail     = _detail_str(ent)

            row.setText(0, ent.eid)
            row.setText(1, status_str)
            row.setText(2, pos_str)
            row.setText(3, detail)

            sc = QColor(_STATUS_COLORS.get(ent.status, DIM))
            row.setForeground(1, sc)

        self._tree.viewport().update()


# ── helpers ───────────────────────────────────────────────────────────────────

def _detail_str(ent) -> str:
    ex = ent.extra
    if ent.etype == EntityType.ROVER:
        return f"BAT {ex.get('battery', 0):.0f}%"
    if ent.etype == EntityType.SENSOR:
        amp  = ex.get("amplitude_db", 0)
        det  = "⚡ CONTACT" if ex.get("detected") else f"{amp:.0f} dB"
        return det
    if ent.etype == EntityType.INTRUDER:
        return f"HDG {ex.get('heading_deg', 0):.0f}°"
    return ""
