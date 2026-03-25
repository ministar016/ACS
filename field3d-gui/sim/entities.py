"""
Entity models for the 200×200 m tactical field simulation.

Three actor types:
  Rover     — autonomous ground robot following a patrol polygon.
  SensorNode— fixed position; rotates a virtual acoustic/seismic scan beam
              and reports amplitude + detection status.
  Intruder  — hostile ground element that wanders across the field with a
              random-walk heading; bounces off the perimeter.

All step() methods advance one physics tick (dt seconds) and return an
EntitySnapshot dict-like dataclass consumed by the GUI.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from enum import Enum


# ── enums ─────────────────────────────────────────────────────────────────────

class EntityType(Enum):
    ROVER    = "ROVER"
    SENSOR   = "SENSOR"
    INTRUDER = "INTRUDER"


class EntityStatus(Enum):
    ACTIVE   = "ACTIVE"
    STANDBY  = "STANDBY"
    OFFLINE  = "OFFLINE"
    ALERT    = "ALERT"


# ── snapshot ──────────────────────────────────────────────────────────────────

@dataclass
class EntitySnapshot:
    eid:    str
    etype:  EntityType
    x:      float
    y:      float
    z:      float
    status: EntityStatus
    extra:  dict = field(default_factory=dict)


# ── Rover ─────────────────────────────────────────────────────────────────────

class Rover:
    """Patrol robot.  Follows a closed polygon at constant speed."""

    SPEED_MS = 2.5   # nominal cruise speed

    def __init__(self, eid: str, patrol: list[tuple[float, float]],
                 dt: float = 0.1, seed: int = 0) -> None:
        self.eid       = eid
        self.x, self.y = float(patrol[0][0]), float(patrol[0][1])
        self._patrol   = patrol
        self._pt_idx   = 1 % len(patrol)
        self._dt       = dt
        self._battery  = 100.0
        self._speed    = self.SPEED_MS
        self._status   = EntityStatus.ACTIVE
        self._rng      = random.Random(seed)

    def step(self) -> EntitySnapshot:
        tx, ty = self._patrol[self._pt_idx]
        dx, dy = tx - self.x, ty - self.y
        dist   = math.hypot(dx, dy)
        if dist < 0.5:
            self._pt_idx = (self._pt_idx + 1) % len(self._patrol)
        else:
            mv      = min(self._speed * self._dt, dist)
            self.x += (dx / dist) * mv + self._rng.gauss(0.0, 0.03)
            self.y += (dy / dist) * mv + self._rng.gauss(0.0, 0.03)

        self._battery = max(0.0, self._battery - 0.001 * self._dt)

        return EntitySnapshot(
            eid    = self.eid,
            etype  = EntityType.ROVER,
            x      = self.x,
            y      = self.y,
            z      = 0.4,
            status = self._status,
            extra  = {
                "battery":   round(self._battery, 1),
                "speed_ms":  round(self._speed, 1),
                "target_wp": self._pt_idx,
            },
        )


# ── SensorNode ────────────────────────────────────────────────────────────────

class SensorNode:
    """Fixed acoustic sensor with a rotating scan beam."""

    DETECT_RANGE_M = 40.0   # detection radius (m)
    SCAN_RATE_DPS  = 90.0   # beam rotation speed (degrees / second)

    def __init__(self, eid: str, x: float, y: float) -> None:
        self.eid          = eid
        self.x, self.y    = x, y
        self._scan_angle  = 0.0
        self._amplitude   = 30.0   # dB (ambient background)
        self._rng         = random.Random(hash(eid) & 0xFFFF)

    def step(self, intruder_x: float, intruder_y: float, dt: float) -> EntitySnapshot:
        # Rotate scan beam
        self._scan_angle = (self._scan_angle + self.SCAN_RATE_DPS * dt) % 360.0

        # Acoustic amplitude driven by intruder proximity
        dist = math.hypot(intruder_x - self.x, intruder_y - self.y)
        if dist <= self.DETECT_RANGE_M:
            proximity  = 1.0 - dist / self.DETECT_RANGE_M
            self._amplitude = 80.0 + 30.0 * proximity + self._rng.gauss(0.0, 1.5)
            detected   = True
        else:
            self._amplitude = 30.0 + self._rng.gauss(0.0, 2.0)
            detected   = False

        return EntitySnapshot(
            eid    = self.eid,
            etype  = EntityType.SENSOR,
            x      = self.x,
            y      = self.y,
            z      = 0.0,
            status = EntityStatus.ALERT if detected else EntityStatus.ACTIVE,
            extra  = {
                "amplitude_db":  round(self._amplitude, 1),
                "scan_angle":    round(self._scan_angle, 1),
                "detect_range":  self.DETECT_RANGE_M,
                "detected":      detected,
                "dist_to_intruder": round(dist, 1),
            },
        )


# ── Intruder ─────────────────────────────────────────────────────────────────

class Intruder:
    """
    Hostile ground element.

    Starts at the SW corner (10, 10) and moves generally NE with a slow
    random-walk heading change.  Reflects off all four field boundaries.
    """

    SPEED_MS       = 1.8    # m/s  (~6.5 km/h — jogging pace)
    HEADING_NOISE  = 1.2    # deg σ per second

    def __init__(self, dt: float = 0.1, seed: int = 99) -> None:
        self.x        = 10.0
        self.y        = 10.0
        self._heading = 48.0   # deg (0 = +X, 90 = +Y)
        self._dt      = dt
        self._rng     = random.Random(seed)
        self.alive    = True

    def step(self) -> EntitySnapshot:
        # Add slow heading drift
        self._heading += self._rng.gauss(0.0, self.HEADING_NOISE)

        rad = math.radians(self._heading)
        nx  = self.x + math.cos(rad) * self.SPEED_MS * self._dt
        ny  = self.y + math.sin(rad) * self.SPEED_MS * self._dt

        # Reflect off walls (100 m field)
        if not (2.0 < nx < 98.0):
            self._heading = 180.0 - self._heading
        if not (2.0 < ny < 98.0):
            self._heading = -self._heading

        self.x = max(2.0, min(98.0, nx))
        self.y = max(2.0, min(98.0, ny))

        return EntitySnapshot(
            eid    = "INTRUDER-01",
            etype  = EntityType.INTRUDER,
            x      = self.x,
            y      = self.y,
            z      = 0.6,
            status = EntityStatus.ACTIVE,
            extra  = {
                "heading_deg": round(self._heading % 360, 1),
                "speed_ms":    self.SPEED_MS,
            },
        )
