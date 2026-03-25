"""
Scenario — wires together terrain, sensors, rovers, and the intruder for the
200×200 m tactical field.

Each call to step() advances the simulation by one dt tick and returns a
ScenarioSnapshot that the GUI consumes.

LiDAR simulation
────────────────
Three fixed sensor nodes carry virtual 2-D LiDAR heads rotating at
90 deg/s.  Each tick the active beam sweeps SCAN_STEP_DEG degrees.
For every degree in the sweep a cluster of PTS_PER_BEAM point returns is
cast outward at a random range within SCAN_RANGE_M, the return height is
read from the TerrainMap plus a small Gaussian noise, and the point is
pushed into a rolling circular buffer.  The resulting cloud forms the
classic accumulated scan pattern seen on real autonomous systems.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import List

import numpy as np

from .terrain  import TerrainMap
from .entities import (
    Rover, SensorNode, Intruder,
    EntitySnapshot, EntityStatus, EntityType,
)

# ── layout ────────────────────────────────────────────────────────────────────

_ROVER_PATROLS: dict[str, list[tuple[float, float]]] = {
    "ROVER-01": [(20.0, 20.0), (80.0, 20.0), (80.0, 80.0), (20.0, 80.0)],
}

_SENSOR_LAYOUT: list[tuple[str, float, float]] = [
    ("SENSOR-A", 50.0, 50.0),
]

# ── LiDAR parameters ─────────────────────────────────────────────────────────

_SCAN_RANGE_M  = 42.0    # maximum range of each LiDAR beam (m)
_SCAN_STEP_DPS = 90.0    # degrees swept per second per sensor
_PTS_PER_DEG   = 3       # point returns emitted per degree of sweep
_MAX_BUF_PTS   = 4000    # top-of-buffer; older points are discarded first

# Scan-return colours: bright cyan fading with range
_SCAN_R, _SCAN_G, _SCAN_B = 0.05, 0.85, 0.90


# ── snapshot ──────────────────────────────────────────────────────────────────

@dataclass
class ScenarioSnapshot:
    t:           float
    entities:    List[EntitySnapshot]
    scan_pts:    np.ndarray   # (K, 3) float32  X Y Z
    scan_cols:   np.ndarray   # (K, 4) float32  RGBA
    alerts:      List[str]    # new alert strings generated this tick


# ── Scenario ──────────────────────────────────────────────────────────────────

class Scenario:
    def __init__(self, dt: float = 0.1, seed: int = 42) -> None:
        self._dt  = dt
        self._t   = 0.0
        self._rng = random.Random(seed)

        self.terrain  = TerrainMap(seed=seed)
        self.rovers   = [
            Rover(eid, patrol, dt=dt, seed=seed + i)
            for i, (eid, patrol) in enumerate(_ROVER_PATROLS.items())
        ]
        self.sensors  = [
            SensorNode(eid, x, y)
            for eid, x, y in _SENSOR_LAYOUT
        ]
        self.intruder = Intruder(dt=dt, seed=seed + 99)

        # Per-sensor scan angles (degrees, wraps at 360)
        self._angles: list[float] = [0.0] * len(self.sensors)

        # Rolling point cloud buffer: list of (x, y, z, r, g, b, a) tuples
        self._scan_buf: list[tuple[float, ...]] = []

        # Alert history (last 60 messages)
        self._alert_history: list[str] = []

    # ── public ────────────────────────────────────────────────────────────

    def step(self) -> ScenarioSnapshot:
        self._t += self._dt
        new_alerts: list[str] = []

        # ── advance intruder
        int_snap = self.intruder.step()

        # ── advance sensors + LiDAR
        sensor_snaps: list[EntitySnapshot] = []
        for i, sensor in enumerate(self.sensors):
            sn = sensor.step(int_snap.x, int_snap.y, self._dt)
            sensor_snaps.append(sn)

            # Alert on new detection (de-bounce: not in last 5 messages)
            if sn.extra.get("detected"):
                msg = (f"T+{self._t:6.1f}s  {sensor.eid} — CONTACT at "
                       f"({int_snap.x:.0f},{int_snap.y:.0f}) m  "
                       f"AMP {sn.extra['amplitude_db']:.0f} dB")
                if not any(sensor.eid in a for a in self._alert_history[-5:]):
                    new_alerts.append(msg)

            # ── LiDAR: sweep SCAN_STEP_DPS*dt degrees this tick
            sweep = _SCAN_STEP_DPS * self._dt
            start = self._angles[i]
            self._angles[i] = (start + sweep) % 360.0
            new_pts = self._lidar_sweep(sensor, start, sweep)
            self._scan_buf.extend(new_pts)

        # ── advance rovers
        rover_snaps = [r.step() for r in self.rovers]

        # ── trim point buffer
        excess = len(self._scan_buf) - _MAX_BUF_PTS
        if excess > 0:
            del self._scan_buf[:excess]

        # ── record alerts
        self._alert_history.extend(new_alerts)
        if len(self._alert_history) > 60:
            self._alert_history = self._alert_history[-60:]

        # ── build output arrays
        if self._scan_buf:
            arr       = np.array(self._scan_buf, dtype=np.float32)
            scan_pts  = arr[:, :3]
            scan_cols = arr[:, 3:]
        else:
            scan_pts  = np.zeros((0, 3), dtype=np.float32)
            scan_cols = np.zeros((0, 4), dtype=np.float32)

        return ScenarioSnapshot(
            t        = self._t,
            entities = rover_snaps + sensor_snaps + [int_snap],
            scan_pts = scan_pts,
            scan_cols= scan_cols,
            alerts   = new_alerts,
        )

    # ── private ───────────────────────────────────────────────────────────

    def _lidar_sweep(
        self, sensor: SensorNode, start_deg: float, sweep_deg: float,
    ) -> list[tuple[float, ...]]:
        """
        Emit LiDAR returns for a beam sweeping from start_deg by sweep_deg.
        Returns a list of (x, y, z, r, g, b, a) tuples.
        """
        points: list[tuple[float, ...]] = []
        sx, sy = sensor.x, sensor.y
        n_steps = max(1, int(sweep_deg))

        for step in range(n_steps):
            beam_deg = start_deg + step + self._rng.uniform(0.0, 1.0)
            beam_rad = math.radians(beam_deg)

            for _ in range(_PTS_PER_DEG):
                r = self._rng.uniform(3.0, _SCAN_RANGE_M)
                px = sx + math.cos(beam_rad) * r
                py = sy + math.sin(beam_rad) * r
                if not (0.0 <= px <= 100.0 and 0.0 <= py <= 100.0):
                    continue
                pz = self.terrain.z_at(px, py) + self._rng.gauss(0.0, 0.12)

                # Intensity falls off with range; alpha follows
                intensity = max(0.25, 1.0 - r / _SCAN_RANGE_M)
                alpha     = min(0.90, intensity * 1.15)
                points.append((
                    float(px), float(py), float(pz),
                    _SCAN_R,
                    _SCAN_G * intensity,
                    _SCAN_B * intensity,
                    alpha,
                ))

        return points
