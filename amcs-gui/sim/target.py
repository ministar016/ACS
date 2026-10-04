"""
Ground-truth targets: drones and enemy ground vehicles.

Each target is ground truth: sensors sample it, the tracker never sees it
directly.

AerialTarget — drone, 60–120 km/h
  • TRANSIT  — holds a straight course with small random-walk noise
  • HOMING   — steers toward an aim point (the protected asset) and strikes
               it when it gets within IMPACT_RADIUS_M
EscortDrone  — flies a formation slot on the convoy's flank (parallel to its
               axis of advance) until released, then strikes the asset
AttackHelicopter — escort aviation: holds its slot exactly (can hover); when
               released it flies to a stand-off point and fires missiles at
               the asset, then egresses.  Manned: cannot be jammed
GroundTarget — enemy (unmanned) vehicle following a road route delivered by
               the route provider; speed from the drivability model

Life cycle
──────────
  drone:   PENDING ─▶ FLYING ─┬─ leaves area ─▶ EXITED
                              ├─ reaches asset ─▶ IMPACT (base hit)
                              ├─ jam()     ─▶ JAMMED (descends) ─▶ LANDED
                              └─ destroy() ─▶ DESTROYED
  vehicle: PENDING ─▶ MOVING ─┬─ end of route ─▶ ARRIVED (assaulting)
                              ├─ jam()     ─▶ DISABLED (control link lost)
                              └─ destroy() ─▶ DESTROYED

`alive`      — still physically present and observable (FLYING, JAMMED,
               MOVING, ARRIVED)
`engageable` — still a threat worth shooting at (FLYING, MOVING, ARRIVED)
"""
from __future__ import annotations
import math
import random
from enum import Enum, auto
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


class TargetState(Enum):
    PENDING   = auto()   # not yet spawned
    FLYING    = auto()
    JAMMED    = auto()   # drone control link jammed — descending
    LANDED    = auto()   # forced down by jamming (soft kill complete)
    DESTROYED = auto()   # hard kill
    EXITED    = auto()   # left the operating area
    IMPACT    = auto()   # drone reached the protected asset (base hit)
    MOVING    = auto()   # ground vehicle driving its route
    ARRIVED   = auto()   # ground vehicle at its objective (assaulting)
    DISABLED  = auto()   # ground vehicle control link jammed — stopped


_ALIVE      = (TargetState.FLYING, TargetState.JAMMED, TargetState.MOVING, TargetState.ARRIVED)
_ENGAGEABLE = (TargetState.FLYING, TargetState.MOVING, TargetState.ARRIVED)


class _TargetBase:
    """Sensor-facing interface shared by drones and vehicles."""

    domain       = "AIR"
    acoustic_db  = 127.0          # effective source level for acoustic arrays (drone → ~10 km)
    jammable     = True           # remote-controlled platforms lose their link when jammed

    @property
    def alive(self) -> bool:
        return self.state in _ALIVE

    @property
    def engageable(self) -> bool:
        return self.state in _ENGAGEABLE

    @property
    def velocity(self) -> Velocity:
        return Velocity(self._speed, self._heading)

    @property
    def elapsed_s(self) -> float:
        return self._t

    def distance_to_m(self, lat: float, lon: float) -> float:
        """Straight-line (horizontal) distance from target to a point."""
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


class AerialTarget(_TargetBase):
    """
    Simulated drone.

    Attributes
    ----------
    target_id   : ground-truth id (never exposed to the tracker)
    position    : current GeoCoord (includes altitude AGL)
    velocity    : current Velocity
    state       : TargetState
    hostile     : scenario truth, used only for scoring / tests
    """

    _BEARING_NOISE_STD = 0.05     # deg σ per tick — stable autopilot
    _SPEED_NOISE_STD   = 0.2      # m/s σ per tick
    MIN_SPEED_MS       = 60.0 / 3.6   # drone speed envelope 60–120 km/h
    MAX_SPEED_MS       = 120.0 / 3.6
    _MAX_TURN_RATE     = 6.0      # deg/s for HOMING profile
    _JAM_DESCENT_MS    = 4.0      # descent rate once jammed
    _JAM_SPEED_DECAY   = 0.97     # per-tick horizontal speed decay once jammed
    IMPACT_RADIUS_M    = 60.0

    def __init__(
        self,
        target_id:  str,
        start_lat:  float,
        start_lon:  float,
        heading:    float,
        speed_ms:   float,
        altitude_m: float,
        dt:         float = 0.1,
        seed:       int   = 0,
        spawn_time: float = 0.0,
        aim_point:  tuple[float, float] | None = None,
        bounds:     tuple[float, float, float, float] = (42.78, 42.90, 20.10, 20.60),
        hostile:    bool  = True,
        rcs_dbsm:   float = -15.0,
        drone_class: str  = "UAV_FIXED_WING",
    ) -> None:
        self.target_id   = target_id
        self._start      = (start_lat, start_lon, heading, speed_ms, altitude_m)
        self._dt         = dt
        self._rng        = random.Random(seed)
        self.spawn_time  = spawn_time
        self.aim_point   = aim_point
        self._bounds     = bounds         # lat_min, lat_max, lon_min, lon_max
        self.hostile     = hostile
        self.rcs_dbsm    = rcs_dbsm
        self.drone_class = drone_class
        self.reset()

    def reset(self) -> None:
        lat, lon, hdg, spd, alt = self._start
        self._lat, self._lon = lat, lon
        self._heading  = hdg
        self._speed    = spd
        self._alt      = alt
        self._t        = 0.0
        self.state     = TargetState.PENDING if self.spawn_time > 0 else TargetState.FLYING

    # ── public interface ──────────────────────────────────────────────────

    @property
    def position(self) -> GeoCoord:
        return GeoCoord(self._lat, self._lon, self._alt)

    def jam(self) -> None:
        """Soft kill: control/GNSS link jammed — drone descends and lands."""
        if self.state == TargetState.FLYING:
            self.state = TargetState.JAMMED

    def destroy(self) -> None:
        """Hard kill."""
        if self.alive:
            self.state = TargetState.DESTROYED

    def _desired_heading(self) -> float | None:
        """Steering hook: heading to fly, or None to hold course."""
        if self.aim_point is not None:
            return _bearing_deg(self._lat, self._lon, *self.aim_point)
        return None

    def _turn_rate(self) -> float:
        return self._MAX_TURN_RATE

    def _speed_cmd(self) -> float | None:
        """Speed hook: commanded speed, or None for the free random walk."""
        return None

    _ACCEL_MS2 = 5.0

    def step(self) -> None:
        """Advance target one time-step."""
        self._t += self._dt
        if self.state == TargetState.PENDING:
            if self._t >= self.spawn_time:
                self.state = TargetState.FLYING
            return
        if not self.alive:
            return

        if self.state == TargetState.JAMMED:
            self._speed *= self._JAM_SPEED_DECAY
            self._alt = max(0.0, self._alt - self._JAM_DESCENT_MS * self._dt)
            if self._alt <= 0.0:
                self.state = TargetState.LANDED
                self._speed = 0.0
                return
        else:
            desired = self._desired_heading()
            if desired is not None:
                err = (desired - self._heading + 180) % 360 - 180
                max_turn = self._turn_rate() * self._dt
                self._heading = (self._heading + max(-max_turn, min(max_turn, err))) % 360
            h_noise = self._rng.gauss(0.0, self._BEARING_NOISE_STD)
            self._heading = (self._heading + h_noise) % 360
            cmd = self._speed_cmd()
            if cmd is None:
                s_noise = self._rng.gauss(0.0, self._SPEED_NOISE_STD)
                self._speed = self._speed + s_noise
            else:
                dv = self._ACCEL_MS2 * self._dt
                self._speed += max(-dv, min(dv, cmd - self._speed))
            self._speed = max(self.MIN_SPEED_MS, min(self.MAX_SPEED_MS, self._speed))

        dist_m = self._speed * self._dt
        self._lat, self._lon = _move(self._lat, self._lon, self._heading, dist_m)

        if (self.state == TargetState.FLYING and self.aim_point is not None and
                _haversine_m(self._lat, self._lon, *self.aim_point) <= self.IMPACT_RADIUS_M):
            self.state = TargetState.IMPACT
            return

        lat_min, lat_max, lon_min, lon_max = self._bounds
        if not (lat_min <= self._lat <= lat_max and lon_min <= self._lon <= lon_max):
            self.state = TargetState.EXITED


class EscortDrone(AerialTarget):
    """
    Air escort flying in parallel with a ground convoy.

    `axis_fn()` → (lead_lat, lead_lon, axis_deg, lead_speed_ms) or None: the
    convoy lead and its (smoothed) direction of advance.  The escort holds the
    formation slot `slot` = (along_m, cross_m) relative to the lead — ahead /
    behind along the axis, right (+) / left (−) across it.  A drone cannot fly
    as slowly as a truck, so it weaves a small racetrack around its slot.
    When `release_fn()` says go it strikes `strike_point` (the asset).
    """

    _ESCORT_TURN_RATE = 25.0
    _WEAVE_RADIUS_M   = 180.0
    _WEAVE_LEAD_DEG   = 60.0

    def __init__(self, *args, axis_fn=None, release_fn=None,
                 strike_point: tuple[float, float] | None = None,
                 slot: tuple[float, float] = (0.0, 500.0), **kw) -> None:
        self._axis_fn = axis_fn
        self._release_fn = release_fn
        self.strike_point = strike_point
        self.slot = slot
        self.released = False
        super().__init__(*args, **kw)

    def slot_position(self) -> tuple[float, float] | None:
        ax = self._axis_fn() if self._axis_fn else None
        if ax is None:
            return None
        lat, lon, axis, _ = ax
        along, cross = self.slot
        lat, lon = _move(lat, lon, axis, along) if along >= 0 else _move(lat, lon, (axis + 180) % 360, -along)
        return _move(lat, lon, (axis + 90) % 360, cross) if cross >= 0 else _move(lat, lon, (axis + 270) % 360, -cross)

    def _check_release(self) -> None:
        if not self.released and self._release_fn is not None and self._release_fn():
            self.released = True
            self._on_release()

    def _on_release(self) -> None:
        self.aim_point = self.strike_point

    def _desired_heading(self) -> float | None:
        self._check_release()
        if self.released:
            return super()._desired_heading()
        slot = self.slot_position()
        if slot is None:
            return None
        d = _haversine_m(self._lat, self._lon, *slot)
        if d > 2 * self._WEAVE_RADIUS_M:
            return _bearing_deg(self._lat, self._lon, *slot)
        # On station: weave a small racetrack around the slot (it moves with the convoy)
        here = _bearing_deg(slot[0], slot[1], self._lat, self._lon)
        tlat, tlon = _move(slot[0], slot[1], (here + self._WEAVE_LEAD_DEG) % 360, self._WEAVE_RADIUS_M)
        return _bearing_deg(self._lat, self._lon, tlat, tlon)

    def _turn_rate(self) -> float:
        return self._ESCORT_TURN_RATE


class AttackHelicopter(EscortDrone):
    """
    Escort aviation.  Holds its formation slot exactly (it can hover and fly
    at convoy speed).  On release it flies to a stand-off point STANDOFF_M
    from the asset, hovers and fires one missile every FIRE_INTERVAL_S until
    its MISSILES are spent, then egresses.  The scenario turns each launch
    into a hit / miss on the asset.
    """

    domain      = "AIR"
    acoustic_db = 132.0          # rotor noise carries further than a drone
    jammable    = False          # manned
    STANDOFF_M       = 1_500.0
    FIRE_INTERVAL_S  = 20.0
    MISSILES         = 4
    _DASH_MS         = 250.0 / 3.6
    _ACCEL_MS2       = 4.0

    def __init__(self, *args, **kw) -> None:
        self.MIN_SPEED_MS = 0.0
        self.MAX_SPEED_MS = self._DASH_MS
        self.missiles = self.MISSILES
        self.pending_shots = 0
        self._fire_t = 0.0
        self._phase_tag = "ESCORT"          # ESCORT → INBOUND → FIRING → EGRESS
        super().__init__(*args, **kw)

    def _on_release(self) -> None:
        self._phase_tag = "INBOUND"

    def _standoff_point(self) -> tuple[float, float]:
        brg = _bearing_deg(*self.strike_point, self._lat, self._lon)
        return _move(*self.strike_point, brg, self.STANDOFF_M)

    def _desired_heading(self) -> float | None:
        self._check_release()
        if self._phase_tag == "ESCORT":
            slot = self.slot_position()
            return None if slot is None else _bearing_deg(self._lat, self._lon, *slot)
        if self._phase_tag == "EGRESS":
            return (_bearing_deg(*self.strike_point, self._lat, self._lon)) % 360
        return _bearing_deg(self._lat, self._lon, *self._standoff_point())

    def _speed_cmd(self) -> float | None:
        if self._phase_tag == "ESCORT":
            slot = self.slot_position()
            ax = self._axis_fn() if self._axis_fn else None
            if slot is None or ax is None:
                return 0.0
            d = _haversine_m(self._lat, self._lon, *slot)
            return min(self._DASH_MS, ax[3] + 0.2 * d)
        if self._phase_tag == "INBOUND":
            d = _haversine_m(self._lat, self._lon, *self._standoff_point())
            if d < 60.0:
                self._phase_tag = "FIRING"
                self._fire_t = self.FIRE_INTERVAL_S          # first shot right away
                return 0.0
            return min(self._DASH_MS, 0.25 * d + 5.0)
        if self._phase_tag == "FIRING":
            self._fire_t += self._dt
            if self._fire_t >= self.FIRE_INTERVAL_S and self.missiles > 0:
                self._fire_t = 0.0
                self.missiles -= 1
                self.pending_shots += 1
            if self.missiles == 0:
                self._phase_tag = "EGRESS"
            return 0.0
        return self._DASH_MS                                   # EGRESS

    def pop_shots(self) -> int:
        n, self.pending_shots = self.pending_shots, 0
        return n


class GroundTarget(_TargetBase):
    """Enemy unmanned ground vehicle following a road route."""

    domain      = "GROUND"
    acoustic_db = 113.0           # engine noise → ~2.5 km acoustic detection (ground attenuation)
    DEFAULT_SPEED_KMH = 40.0

    def __init__(self, target_id: str, start_lat: float, start_lon: float,
                 dt: float = 0.1, seed: int = 0, spawn_time: float = 0.0,
                 speed_fn=None, hostile: bool = True, rcs_dbsm: float = 10.0,
                 drone_class: str = "UGV_TRACKED") -> None:
        self.target_id   = target_id
        self._dt         = dt
        self._rng        = random.Random(seed)
        self.spawn_time  = spawn_time
        self.hostile     = hostile
        self.rcs_dbsm    = rcs_dbsm
        self.drone_class = drone_class
        self._speed_fn   = speed_fn or (lambda lat, lon: self.DEFAULT_SPEED_KMH / 3.6)
        self._lat, self._lon = start_lat, start_lon
        self._heading    = 90.0
        self._speed      = 0.0
        self._t          = 0.0
        self.route: list[tuple[float, float]] | None = None    # None = not yet routed
        self.state       = TargetState.PENDING

    @property
    def position(self) -> GeoCoord:
        return GeoCoord(self._lat, self._lon, 0.0)

    def set_route(self, waypoints: list[tuple[float, float]]) -> None:
        self.route = list(waypoints)

    def jam(self) -> None:
        if self.state in (TargetState.MOVING, TargetState.ARRIVED):
            self.state = TargetState.DISABLED
            self._speed = 0.0

    def destroy(self) -> None:
        if self.alive:
            self.state = TargetState.DESTROYED
            self._speed = 0.0

    def step(self) -> None:
        self._t += self._dt
        if self.state == TargetState.PENDING:
            if self._t >= self.spawn_time and self.route is not None:
                self.state = TargetState.MOVING
            return
        if self.state != TargetState.MOVING:
            return
        while self.route and _haversine_m(self._lat, self._lon, *self.route[0]) < 10.0:
            self.route.pop(0)
        if not self.route:
            self.state = TargetState.ARRIVED
            self._speed = 0.0
            return
        wlat, wlon = self.route[0]
        self._heading = _bearing_deg(self._lat, self._lon, wlat, wlon)
        self._speed = self._speed_fn(self._lat, self._lon)
        step = min(self._speed * self._dt, _haversine_m(self._lat, self._lon, wlat, wlon))
        self._lat, self._lon = _move(self._lat, self._lon, self._heading, step)
