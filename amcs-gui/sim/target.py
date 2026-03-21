"""
FakeTarget — simulates a hostile drone flying through the corridor.

Trajectory:
  Start  : (42.848°N, 20.170°E)  heading 100° (nearly due east)  altitude 100 m  speed 120 km/h

  At heading 115° (previous) the drone exited the southern boundary in ~245 s while UAV
  radar range was not entered until ~384 s — never detected, button always disabled.

  At heading 100° the southward component drops to 5.8 m/s:
    ~600 s corridor lifetime (vs 245 s)
    ~5 min : UAV radar locks (856 m perpendicular pass, range 5 km)
    ~7 min : ACO-FIELD-02 acoustic detects (855 m pass, range ~1200 m) → bearing line
    → trackData populated → ACCEPT MISSION button activates

The drone holds a roughly straight course with small random-walk noise;
heading is more stable than a ground vehicle (no road constraint).
"""
from __future__ import annotations
import math
import random
from .models import GeoCoord, Velocity

# Earth radius
_R_M = 6_371_000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * _R_M * math.asin(math.sqrt(min(a, 1.0)))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from (lat1,lon1) → (lat2,lon2), degrees 0=N."""
    dlon = math.radians(lon2 - lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


def _move(lat: float, lon: float, heading_deg: float, distance_m: float) -> tuple[float, float]:
    """
    Move (lat, lon) by distance_m in heading_deg direction.
    Returns new (lat, lon).
    """
    d = distance_m / _R_M
    h = math.radians(heading_deg)
    phi1, lam1 = math.radians(lat), math.radians(lon)
    phi2 = math.asin(math.sin(phi1) * math.cos(d) +
                     math.cos(phi1) * math.sin(d) * math.cos(h))
    lam2 = lam1 + math.atan2(
        math.sin(h) * math.sin(d) * math.cos(phi1),
        math.cos(d) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), math.degrees(lam2)


class FakeTarget:
    """
    Simulated hostile drone.

    Attributes
    ----------
    position    : current GeoCoord (ground truth, includes altitude)
    velocity    : current Velocity
    alive       : False once the target exits the corridor
    """

    # Initial state
    _START_LAT  =  42.848          # near northern boundary — northwest entry
    _START_LON  =  20.170          # ~8 km west of acoustic cluster
    _ALTITUDE_M =  100.0           # AGL cruise altitude
    _SPEED_MS   =  120.0 / 3.6    # 120 km/h → 33.3 m/s
    _HEADING    =  100.0           # nearly due east — hugs northern corridor edge,
                                   # passes within ~860 m of UAV orbit (z=5km radar)
                                   # and ~855 m of ACO-FIELD-02 (well within 1200 m range)

    # Corridor bounds
    _LAT_MIN, _LAT_MAX = 42.817, 42.855
    _LON_MIN, _LON_MAX = 20.160, 20.540

    # Random-walk jitter — military drone autopilot is highly stable
    # 0.05°/tick → σ ≈ 3° over 300 s (vs 55° with the old 1.0°/tick value)
    _BEARING_NOISE_STD  = 0.05      # deg σ per tick
    _SPEED_NOISE_STD    = 0.2       # m/s σ per tick

    def __init__(self, dt: float = 0.1, seed: int = 42) -> None:
        self._dt  = dt
        self._rng = random.Random(seed)
        self.reset()

    def reset(self) -> None:
        self._lat     = self._START_LAT
        self._lon     = self._START_LON
        self._heading = self._HEADING
        self._speed   = self._SPEED_MS
        self.alive    = True
        self._t       = 0.0

    # ── public interface ──────────────────────────────────────────────────

    @property
    def position(self) -> GeoCoord:
        return GeoCoord(self._lat, self._lon, self._ALTITUDE_M)

    @property
    def velocity(self) -> Velocity:
        return Velocity(self._speed, self._heading)

    @property
    def elapsed_s(self) -> float:
        return self._t

    def step(self) -> None:
        """Advance target one time-step."""
        if not self.alive:
            return

        # Random-walk on heading (vehicle follows rough road)
        h_noise = self._rng.gauss(0.0, self._BEARING_NOISE_STD)
        self._heading = (self._heading + h_noise) % 360

        # Slight speed variation (stays within realistic drone envelope)
        s_noise = self._rng.gauss(0.0, self._SPEED_NOISE_STD)
        self._speed = max(20.0, min(50.0, self._speed + s_noise))

        # Move
        dist_m = self._speed * self._dt
        self._lat, self._lon = _move(self._lat, self._lon, self._heading, dist_m)
        self._t += self._dt

        # Check exit
        if not (self._LAT_MIN <= self._lat <= self._LAT_MAX and
                self._LON_MIN <= self._lon <= self._LON_MAX):
            self.alive = False

    # ── helpers used by sensors ───────────────────────────────────────────

    def distance_to_m(self, lat: float, lon: float) -> float:
        """Straight-line distance from target to a point."""
        return _haversine_m(self._lat, self._lon, lat, lon)

    def bearing_from_m(self, lat: float, lon: float) -> float:
        """Bearing FROM a sensor at (lat,lon) TOWARDS the target."""
        return _bearing_deg(lat, lon, self._lat, self._lon)

    def radial_velocity_ms(self, lat: float, lon: float) -> float:
        """
        Radial (closing) velocity as seen from a sensor at (lat, lon).
        Positive = target approaching.
        """
        bearing_to_target = _bearing_deg(lat, lon, self._lat, self._lon)
        angle = math.radians(self._heading - bearing_to_target)
        # Component of target velocity towards the sensor = –cos(angle)
        return -self._speed * math.cos(angle)
