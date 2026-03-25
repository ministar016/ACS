"""
Field3DView — pyqtgraph OpenGL viewport for the 200 × 200 m tactical field.

Static scene items (rendered once):
  • Terrain mesh  — GLSurfacePlotItem, colour-mapped by elevation
  • Reference grid — GLGridItem, XY plane at z = 0

Dynamic items (refreshed on every SimBus snapshot):
  • LiDAR point cloud  — GLScatterPlotItem (accumulated scan returns)
  • Entity markers     — GLScatterPlotItem, one item per entity category
  • Sensor scan beams  — GLLinePlotItem, one per sensor node
"""
from __future__ import annotations
import math

import numpy as np
import pyqtgraph.opengl as gl
from PyQt6.QtGui import QVector3D

from sim.terrain  import TerrainMap
from sim.scenario import ScenarioSnapshot
from sim.entities import EntityType, EntityStatus
from .palette import GL_BG, GL_ROVER, GL_SENSOR, GL_SENSOR_ALERT, GL_INTRUDER

# ── constants ─────────────────────────────────────────────────────────────────
_ENTITY_SIZE = {
    EntityType.ROVER:    14,
    EntityType.SENSOR:   10,
    EntityType.INTRUDER: 22,
}
_BEAM_COLOR_IDLE  = (0.20, 0.85, 1.00, 0.50)
_BEAM_COLOR_ALERT = (1.00, 0.30, 0.25, 0.85)
_CLOUD_POINT_SIZE = 3.5
_N_SENSORS        = 1   # one sensor node in the scenario


def _entity_rgba(ent) -> tuple:
    """Per-entity RGBA colour — ALERT state overrides type colour."""
    if ent.status == EntityStatus.ALERT:
        return GL_SENSOR_ALERT
    return {
        EntityType.ROVER:    GL_ROVER,
        EntityType.SENSOR:   GL_SENSOR,
        EntityType.INTRUDER: GL_INTRUDER,
    }.get(ent.etype, (1.0, 1.0, 1.0, 1.0))


class Field3DView(gl.GLViewWidget):
    """Interactive 3-D field view – drag to rotate, scroll to zoom."""

    def __init__(self, terrain: TerrainMap, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(560, 480)
        self.setBackgroundColor(GL_BG)
        self._terrain = terrain

        # Initial camera: elevated south-west view of the 100 m square
        self.opts['center']    = QVector3D(50.0, 50.0, 3.0)
        self.opts['distance']  = 180.0
        self.opts['elevation'] = 32.0
        self.opts['azimuth']   = 225.0

        self._build_static()
        self._build_dynamic()

    # ── scene construction ────────────────────────────────────────────────────

    def _build_static(self) -> None:
        """Add terrain mesh + reference grid (rendered once)."""
        # Single grid BELOW terrain (z = -0.05) so it never z-fights the surface
        grid = gl.GLGridItem()
        grid.setSize(100, 100)
        grid.setSpacing(10, 10)
        grid.translate(50, 50, -0.05)
        grid.setColor((0.22, 0.50, 0.70, 0.18))
        self.addItem(grid)

        # Terrain surface — smooth shading, no wireframe edges
        xs, ys, Z_surf, C_surf = self._terrain.surface_data()
        surf = gl.GLSurfacePlotItem(
            x=xs, y=ys, z=Z_surf,
            colors=C_surf,
            smooth=True,
            drawEdges=False,
        )
        self.addItem(surf)

    def _build_dynamic(self) -> None:
        """Create empty placeholders for animated items."""
        _empty3 = np.zeros((1, 3), dtype=np.float32)
        _empty4 = np.zeros((1, 4), dtype=np.float32)

        # LiDAR point cloud
        self._cloud = gl.GLScatterPlotItem(
            pos=_empty3.copy(), color=_empty4.copy(),
            size=_CLOUD_POINT_SIZE, pxMode=True,
            glOptions='additive',   # additive blend → bright overlap looks great
        )
        self.addItem(self._cloud)

        # Entity markers (rovers, sensors, intruder combined)
        self._markers = gl.GLScatterPlotItem(
            pos=_empty3.copy(), color=_empty4.copy(),
            size=15.0, pxMode=True,
        )
        self.addItem(self._markers)

        # Sensor scan beams (one GLLinePlotItem per sensor)
        _beam2 = np.zeros((2, 3), dtype=np.float32)
        self._beams: list[gl.GLLinePlotItem] = []
        for _ in range(_N_SENSORS):
            b = gl.GLLinePlotItem(
                pos=_beam2.copy(),
                color=_BEAM_COLOR_IDLE,
                width=2.0, antialias=True,
            )
            self.addItem(b)
            self._beams.append(b)

    # ── per-frame update ──────────────────────────────────────────────────────

    def update_snapshot(self, snap: ScenarioSnapshot) -> None:
        """Refresh all dynamic items from snapshot data."""
        self._update_cloud(snap)
        self._update_entities(snap)

    def _update_cloud(self, snap: ScenarioSnapshot) -> None:
        if snap.scan_pts.shape[0] > 0:
            self._cloud.setData(
                pos=snap.scan_pts,
                color=snap.scan_cols,
                size=_CLOUD_POINT_SIZE,
                pxMode=True,
            )

    def _update_entities(self, snap: ScenarioSnapshot) -> None:
        positions: list[list[float]] = []
        colors:    list[tuple]       = []
        sizes:     list[float]       = []
        beam_idx = 0

        for ent in snap.entities:
            ground = self._terrain.z_at(ent.x, ent.y)
            z      = ground + ent.z
            positions.append([ent.x, ent.y, z])
            colors.append(_entity_rgba(ent))
            sizes.append(float(_ENTITY_SIZE.get(ent.etype, 10)))

            # Update matching scan beam
            if ent.etype == EntityType.SENSOR and beam_idx < len(self._beams):
                self._update_beam(ent, ground, beam_idx)
                beam_idx += 1

        if positions:
            self._markers.setData(
                pos   = np.array(positions, dtype=np.float32),
                color = np.array(colors,    dtype=np.float32),
                size  = np.array(sizes,     dtype=np.float32),
                pxMode=True,
            )

    def _update_beam(self, sensor_ent, base_z: float, idx: int) -> None:
        angle_rad = math.radians(sensor_ent.extra.get("scan_angle", 0.0))
        det_r     = sensor_ent.extra.get("detect_range", 65.0)
        ex = max(0.0, min(200.0, sensor_ent.x + math.cos(angle_rad) * det_r))
        ey = max(0.0, min(200.0, sensor_ent.y + math.sin(angle_rad) * det_r))
        ez = self._terrain.z_at(ex, ey) + 0.4
        pts = np.array(
            [[sensor_ent.x, sensor_ent.y, base_z + 0.4], [ex, ey, ez]],
            dtype=np.float32,
        )
        bc = _BEAM_COLOR_ALERT if sensor_ent.extra.get("detected") else _BEAM_COLOR_IDLE
        self._beams[idx].setData(pos=pts, color=bc)
