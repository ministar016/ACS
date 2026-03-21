"""
UAV — PVO intercept drone.

Normal mode  : holds holding orbit over the corridor centre at 150 m altitude.
Intercept mode: activated via start_intercept() — flies straight toward the
                hostile drone (smooth turn rate 30°/s), status → ACTIVE.
Carries RadarSensor + CameraSensor.
"""
from __future__ import annotations
import math
import random
from ..models import GeoCoord, DeviceStatus, UAVTelemetry
from ..target import FakeTarget, _move, _bearing_deg
from ..sensors.radar  import RadarSensor
from ..sensors.camera import CameraSensor


_ORBIT_CENTER_LAT = 42.832
_ORBIT_CENTER_LON = 20.358
_ORBIT_RADIUS_M   = 200.0    # tight holding circle
_ORBIT_PERIOD_S   = 240.0    # 4-minute orbit
_ALTITUDE_M       = 150.0
_SPEED_MS         = 18.0     # ~65 km/h
_BATTERY_DRAIN    = 0.002    # % per second
_MAX_TURN_RATE    = 30.0     # deg/s when intercepting


class UAV:
    DEVICE_ID = "UAV-ALPHA-001"

    def __init__(self, dt: float = 0.1, seed: int = 10) -> None:
        self._dt             = dt
        self._rng            = random.Random(seed)
        self._t              = 0.0
        self._battery        = 78.5
        self.status          = DeviceStatus.DEPLOYED
        self._intercept_mode = False

        # Sensors
        self.radar  = RadarSensor("RAD-UAV-ALPHA-01", range_m=5_000, seed=seed+1)
        self.camera = CameraSensor("CAM-UAV-ALPHA-01", night_vision=True, seed=seed+2)

        self._update_position()

    # ── public interface ──────────────────────────────────────────────────

    @property
    def position(self) -> GeoCoord:
        return GeoCoord(self._lat, self._lon, _ALTITUDE_M)

    @property
    def heading_deg(self) -> float:
        return self._heading

    def start_intercept(self) -> None:
        """Switch from holding orbit to active intercept."""
        self._intercept_mode = True
        self.status = DeviceStatus.ACTIVE

    def step(self, target: FakeTarget, timestamp: float) -> UAVTelemetry:
        self._t += self._dt
        if self._intercept_mode:
            self._update_intercept(target.position.lat, target.position.lon)
        else:
            self._update_position()
        self._battery = max(0.0, self._battery - _BATTERY_DRAIN * self._dt)

        # Feed platform pose to sensors
        self.radar .update_platform(self._lat, self._lon, self._heading)
        self.camera.update_platform(self._lat, self._lon, self._heading)

        radar_ret  = self.radar .sample(target, timestamp)
        camera_det = self.camera.sample(target, timestamp)

        return UAVTelemetry(
            device_id   = self.DEVICE_ID,
            timestamp   = timestamp,
            position    = self.position,
            altitude_m  = _ALTITUDE_M + self._rng.gauss(0.0, 0.5),
            speed_ms    = _SPEED_MS   + self._rng.gauss(0.0, 0.3),
            heading_deg = round(self._heading, 1),
            battery_pct = round(self._battery, 2),
            status      = self.status,
            radar       = radar_ret,
            camera      = camera_det,
        )

    # ── private ───────────────────────────────────────────────────────────

    def _update_position(self) -> None:
        """Compute position on circular orbit."""
        angle = 2 * math.pi * (self._t / _ORBIT_PERIOD_S)
        dlat = math.degrees(_ORBIT_RADIUS_M / 6_371_000.0 * math.cos(angle))
        dlon = math.degrees(
            _ORBIT_RADIUS_M / 6_371_000.0 * math.sin(angle) /
            math.cos(math.radians(_ORBIT_CENTER_LAT))
        )
        self._lat     = _ORBIT_CENTER_LAT + dlat
        self._lon     = _ORBIT_CENTER_LON + dlon
        self._heading = (math.degrees(angle) + 90.0) % 360.0

    def _update_intercept(self, target_lat: float, target_lon: float) -> None:
        """Fly toward target with smooth turn rate."""
        desired_hdg = _bearing_deg(self._lat, self._lon, target_lat, target_lon)
        hdg_err     = (desired_hdg - self._heading + 180) % 360 - 180
        max_turn    = _MAX_TURN_RATE * self._dt
        self._heading = (self._heading + max(-max_turn, min(max_turn, hdg_err))) % 360
        self._lat, self._lon = _move(
            self._lat, self._lon, self._heading, _SPEED_MS * self._dt
        )
