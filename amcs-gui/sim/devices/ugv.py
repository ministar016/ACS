"""
UGV — ground intercept vehicle.

Drives from staging area toward the predicted intercept point (42.827°N, 20.355°E).
Speed: 25 km/h (6.94 m/s).  Carries RadarSensor + CameraSensor.
"""
from __future__ import annotations
import math
import random
from ..models import GeoCoord, DeviceStatus, UGVTelemetry
from ..target import FakeTarget, _move, _bearing_deg, _haversine_m
from ..sensors.radar  import RadarSensor
from ..sensors.camera import CameraSensor


_START_LAT     = 42.826
_START_LON     = 20.342
_INTERCEPT_LAT = 42.827
_INTERCEPT_LON = 20.355
_SPEED_MS      = 25.0 / 3.6    # 25 km/h → m/s
_BATTERY_DRAIN = 0.0015         # % per second
_ARRIVE_THRESH = 50.0           # stop when within 50 m of intercept


class UGV:
    DEVICE_ID = "UGV-BRAVO-002"

    def __init__(self, dt: float = 0.1, seed: int = 20) -> None:
        self._dt      = dt
        self._rng     = random.Random(seed)
        self._lat     = _START_LAT
        self._lon     = _START_LON
        self._battery = 92.3
        self._heading = 0.0
        self._speed   = 0.0
        self.status   = DeviceStatus.DEPLOYING

        # Sensors
        self.radar  = RadarSensor("RAD-UGV-BRAVO-01", range_m=5_000, seed=seed+1)
        self.camera = CameraSensor("CAM-UGV-BRAVO-01", night_vision=True, seed=seed+2)

    # ── public interface ──────────────────────────────────────────────────

    @property
    def position(self) -> GeoCoord:
        return GeoCoord(self._lat, self._lon, 0.0)

    @property
    def heading_deg(self) -> float:
        return self._heading

    def step(self, target: FakeTarget, timestamp: float) -> UGVTelemetry:
        self._drive()
        self._battery = max(0.0, self._battery - _BATTERY_DRAIN * self._dt)

        self.radar .update_platform(self._lat, self._lon, self._heading)
        self.camera.update_platform(self._lat, self._lon, self._heading)

        radar_ret  = self.radar .sample(target, timestamp)
        camera_det = self.camera.sample(target, timestamp)

        return UGVTelemetry(
            device_id   = self.DEVICE_ID,
            timestamp   = timestamp,
            position    = self.position,
            speed_ms    = round(self._speed + self._rng.gauss(0.0, 0.1), 2),
            heading_deg = round(self._heading, 1),
            battery_pct = round(self._battery, 2),
            status      = self.status,
            terrain_mode= "RUGGED",
            radar       = radar_ret,
            camera      = camera_det,
        )

    # ── private ───────────────────────────────────────────────────────────

    def _drive(self) -> None:
        dist = _haversine_m(self._lat, self._lon, _INTERCEPT_LAT, _INTERCEPT_LON)
        if dist < _ARRIVE_THRESH:
            self._speed  = 0.0
            self.status  = DeviceStatus.DEPLOYED
            return

        self.status   = DeviceStatus.DEPLOYING
        self._heading = _bearing_deg(self._lat, self._lon, _INTERCEPT_LAT, _INTERCEPT_LON)
        self._speed   = _SPEED_MS + self._rng.gauss(0.0, 0.2)

        dist_step = self._speed * self._dt
        self._lat, self._lon = _move(self._lat, self._lon, self._heading, dist_step)
