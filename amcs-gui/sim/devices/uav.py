"""
UAV — interceptor drone (hard-kill effector), kept on the ground at the base.

Life cycle
──────────
  IDLE ──launch (engagement or operator call)──▶ LAUNCHING ──▶ INTERCEPT / PATROL
    ▲                                                              │
    └──── LANDING ◀──── RTB ◀──── released / recalled ◀────────────┘

IDLE      : on the ground at the base, charging, sensors off — not shown on
            the map and not visible to our own radars
LAUNCHING : vertical take-off to LAUNCH_ALT_M (LAUNCH_TIME_S)
PATROL    : holding orbit over the base at 150 m, radar on watch (operator call)
INTERCEPT : dash at 55 m/s (~200 km/h) on a predicted-intercept-point course
            computed from the *tracker's estimate* of the assigned track;
            altitude slews to the track altitude
RTB       : fly back to the base, then LANDING → IDLE
EXPENDED  : loitering munition (kamikaze): it detonates on the target —
            destroying it with P_KILL — and is lost either way

Effect model
────────────
Net/kinetic kill when the closest approach during a tick is inside
KILL_RADIUS_M (3-D).  Each pass rolls against P_KILL once; after a miss the
interceptor must open beyond REARM_DIST_M before the next pass counts.

Carries RadarSensor + CameraSensor.
"""
from __future__ import annotations
import dataclasses
import math
import random
from enum import Enum, auto
from ..models import GeoCoord, DeviceStatus, UAVTelemetry
from ..target import AerialTarget, _move, _bearing_deg, _haversine_m
from ..sensors.radar  import RadarSensor
from ..sensors.camera import CameraSensor
from ..guidance import solve_intercept, turn_toward, heading_to, InterceptSolution
from ..zone import LocalFrame


_ORBIT_RADIUS_M   = 300.0
_ORBIT_PERIOD_S   = 240.0
_ALTITUDE_M       = 150.0
_SPEED_MS         = 18.0     # ~65 km/h patrol
DASH_SPEED_MS     = 55.0     # ~200 km/h intercept dash — faster than any 60–120 km/h threat
_RTB_SPEED_MS     = 30.0
_CLIMB_RATE_MS    = 10.0
_LAND_RATE_MS     = 5.0
_BATTERY_DRAIN    = 0.002    # % per second on patrol
_DASH_DRAIN       = 0.02     # % per second at dash speed
_CHARGE_RATE      = 0.05     # % per second on the ground
_MAX_TURN_RATE    = 45.0     # deg/s
_LANDED_RADIUS_M  = 40.0

LAUNCH_TIME_S = 5.0          # from "go" to leaving the pad
LAUNCH_ALT_M  = 50.0
KILL_RADIUS_M = 12.0
P_KILL        = 0.85
REARM_DIST_M  = 150.0


class UAVMode(Enum):
    IDLE      = auto()
    LAUNCHING = auto()
    PATROL    = auto()
    INTERCEPT = auto()
    RTB       = auto()
    LANDING   = auto()
    EXPENDED  = auto()      # detonated on a target (kamikaze) — lost


class UAV:
    def __init__(self, dt: float = 0.1, seed: int = 10,
                 frame: LocalFrame | None = None,
                 base: tuple[float, float] = (42.27442, 21.606345),
                 device_id: str = "UAV-ALPHA-001") -> None:
        self.DEVICE_ID       = device_id
        self._base_lat, self._base_lon = base
        self._dt             = dt
        self._rng            = random.Random(seed)
        self._t              = 0.0
        self._orbit_t        = 0.0
        self._battery        = 100.0
        self.status          = DeviceStatus.ONLINE
        self.mode            = UAVMode.IDLE
        self._after_launch   = UAVMode.PATROL
        self._launch_t       = 0.0
        self._frame          = frame or LocalFrame(*base)
        self._lat, self._lon = base
        self._alt            = 0.0
        self._speed          = 0.0
        self._heading        = 0.0

        # Patrol station: orbit centre on an interception line (None = over the base)
        self.station: tuple[float, float] | None = None

        # Guidance input: latest track estimate (x, y, vx, vy, alt) in ENU
        self._track_est: tuple[float, float, float, float, float] | None = None
        self.assigned_track: str | None = None
        self.solution: InterceptSolution | None = None

        # Effect bookkeeping
        self._armed: dict[str, bool] = {}                  # per target: next pass counts
        self._prev_rel: dict[str, tuple[float, float, float]] = {}

        # Sensors
        self.radar  = RadarSensor(f"RAD-{device_id}", range_m=5_000, seed=seed+1)
        self.camera = CameraSensor(f"CAM-{device_id}", night_vision=True, seed=seed+2)

    # ── public interface ──────────────────────────────────────────────────

    @property
    def position(self) -> GeoCoord:
        return GeoCoord(self._lat, self._lon, self._alt)

    @property
    def heading_deg(self) -> float:
        return self._heading

    @property
    def airborne(self) -> bool:
        return self.mode not in (UAVMode.IDLE, UAVMode.EXPENDED)

    @property
    def expended(self) -> bool:
        return self.mode == UAVMode.EXPENDED

    @property
    def available(self) -> bool:
        return self.assigned_track is None and self._battery > 20.0 and not self.expended

    @property
    def xy(self) -> tuple[float, float]:
        return self._frame.to_xy(self._lat, self._lon)

    def time_to_launch(self) -> float:
        """Seconds before this drone can start flying a mission."""
        if self.mode == UAVMode.IDLE:
            return LAUNCH_TIME_S
        if self.mode == UAVMode.LAUNCHING:
            return max(0.0, LAUNCH_TIME_S - self._launch_t)
        return 0.0

    def launch_patrol(self, station: tuple[float, float] | None = None) -> None:
        """Take off (if needed) and hold an orbit over `station`, or over the base."""
        if self.expended:
            return
        if station is not None:
            self.station = station
        if self.mode == UAVMode.IDLE:
            self._start_launch(UAVMode.PATROL)
        elif self.mode in (UAVMode.RTB, UAVMode.LANDING):
            self.mode = UAVMode.PATROL

    def resume_station(self) -> None:
        """After an engagement: back to the patrol station if one is set, else home."""
        if self.expended:
            return
        if self.station is None or self._battery < 30.0:
            self.station = None
            self.return_to_base()
            return
        self.assigned_track = None
        self._track_est = None
        self.solution = None
        if self.mode not in (UAVMode.IDLE, UAVMode.LANDING):
            self.mode = UAVMode.PATROL
            self.status = DeviceStatus.DEPLOYING

    def start_intercept(self, track_id: str | None = None) -> None:
        self.assigned_track = track_id
        self._armed.clear()
        self._prev_rel.clear()
        if self.mode == UAVMode.IDLE:
            self._start_launch(UAVMode.INTERCEPT)
        elif self.mode == UAVMode.LAUNCHING:
            self._after_launch = UAVMode.INTERCEPT
        else:
            self.mode = UAVMode.INTERCEPT
        self.status = DeviceStatus.DEPLOYING

    def update_track_estimate(self, x: float, y: float, vx: float, vy: float,
                              alt: float) -> None:
        self._track_est = (x, y, vx, vy, alt)

    def return_to_base(self) -> None:
        self.assigned_track = None
        self._track_est = None
        self.solution = None
        if self.mode in (UAVMode.IDLE, UAVMode.LANDING):
            return
        self.mode = UAVMode.RTB
        self.status = DeviceStatus.DEPLOYING

    def step(self, target: AerialTarget | None, timestamp: float) -> UAVTelemetry:
        self._t += self._dt
        m = self.mode
        if m == UAVMode.IDLE:
            self._battery = min(100.0, self._battery + _CHARGE_RATE * self._dt)
        elif m == UAVMode.LAUNCHING:
            self._fly_launch()
        elif m == UAVMode.PATROL:
            self._fly_patrol()
        elif m == UAVMode.INTERCEPT:
            self._fly_intercept()
        elif m == UAVMode.RTB:
            self._fly_rtb()
        elif m == UAVMode.LANDING:
            self._fly_landing()
        if self.airborne:
            drain = _DASH_DRAIN if self.mode == UAVMode.INTERCEPT else _BATTERY_DRAIN
            self._battery = max(0.0, self._battery - drain * self._dt)

        # Feed platform pose to sensors
        self.radar .update_platform(self._lat, self._lon, self._heading, self._alt)
        self.camera.update_platform(self._lat, self._lon, self._heading)

        radar_ret = camera_det = None
        if target is not None:
            radar_ret  = self.radar .sample(target, timestamp)
            camera_det = self.camera.sample(target, timestamp)
        if target is not None and not self.sensing:
            radar_ret  = dataclasses.replace(radar_ret, target_detected=False, detection_confidence=0.0)
            camera_det = dataclasses.replace(camera_det, target_detected=False, confidence=0.0)

        return UAVTelemetry(
            device_id   = self.DEVICE_ID,
            timestamp   = timestamp,
            position    = self.position,
            altitude_m  = self._alt + (self._rng.gauss(0.0, 0.5) if self.airborne else 0.0),
            speed_ms    = self._speed + (self._rng.gauss(0.0, 0.3) if self._speed > 0 else 0.0),
            heading_deg = round(self._heading, 1),
            battery_pct = round(self._battery, 2),
            status      = self.status,
            radar       = radar_ret,
            camera      = camera_det,
        )

    @property
    def sensing(self) -> bool:
        """Onboard radar/camera only work in flight, above the pad."""
        return self.airborne and self._alt >= LAUNCH_ALT_M * 0.8

    def evaluate_effect(self, targets: list[AerialTarget]) -> list[tuple[AerialTarget, bool]]:
        """
        Kill assessment for this tick.  Returns (target, destroyed) for every
        pass through the kill radius — destroyed=False is a miss.
        Uses closest-approach over the tick so a fast pass cannot tunnel
        through the kill radius between samples.
        """
        passes: list[tuple[AerialTarget, bool]] = []
        if self.mode != UAVMode.INTERCEPT:
            return passes
        ux, uy = self.xy
        for tgt in targets:
            if tgt.state.name != "FLYING":
                continue
            tx, ty = self._frame.to_xy(tgt.position.lat, tgt.position.lon)
            rel = (tx - ux, ty - uy, tgt.position.alt - self._alt)
            prev = self._prev_rel.get(tgt.target_id, rel)
            self._prev_rel[tgt.target_id] = rel
            miss = _segment_min_norm(prev, rel)
            armed = self._armed.get(tgt.target_id, True)
            if not armed:
                if math.sqrt(sum(c * c for c in rel)) > REARM_DIST_M:
                    self._armed[tgt.target_id] = True
                continue
            if miss <= KILL_RADIUS_M:
                # Kamikaze: the warhead goes off — the target dies with P_KILL, the interceptor always
                hit = self._rng.random() < P_KILL
                if hit:
                    tgt.destroy()
                passes.append((tgt, hit))
                self._expend()
                break
        return passes

    def _expend(self) -> None:
        self.mode = UAVMode.EXPENDED
        self.status = DeviceStatus.OFFLINE
        self._speed = 0.0
        self._alt = 0.0
        self.station = None
        self.assigned_track = None
        self._track_est = None
        self.solution = None

    # ── private ───────────────────────────────────────────────────────────

    def _start_launch(self, then: UAVMode) -> None:
        self.mode = UAVMode.LAUNCHING
        self._after_launch = then
        self._launch_t = 0.0
        self.status = DeviceStatus.DEPLOYING

    def _fly_launch(self) -> None:
        self._launch_t += self._dt
        self._speed = 0.0
        self._alt = min(LAUNCH_ALT_M, LAUNCH_ALT_M * self._launch_t / LAUNCH_TIME_S)
        if self._launch_t >= LAUNCH_TIME_S:
            self.mode = self._after_launch
            if self.mode == UAVMode.PATROL:
                self._orbit_t = 0.0
                self.status = DeviceStatus.DEPLOYED

    def _fly_patrol(self) -> None:
        """Join and hold a circular orbit over the station (or the base)."""
        clat, clon = self.station or (self._base_lat, self._base_lon)
        dist = _haversine_m(self._lat, self._lon, clat, clon)
        if abs(dist - _ORBIT_RADIUS_M) > 30.0:
            # Fly to the orbit ring first — at transit speed when the station is far
            brg_out = _bearing_deg(clat, clon, self._lat, self._lon) if dist > 1 else 0.0
            tlat, tlon = _move(clat, clon, brg_out, _ORBIT_RADIUS_M)
            hdg = turn_toward(self._heading, _bearing_deg(self._lat, self._lon, tlat, tlon),
                              _MAX_TURN_RATE, self._dt)
            self._advance(hdg, _RTB_SPEED_MS if dist > 1_000 else _SPEED_MS, _ALTITUDE_M)
            return
        # On the ring: fly tangentially (clockwise)
        brg_out = _bearing_deg(clat, clon, self._lat, self._lon)
        hdg = turn_toward(self._heading, (brg_out + 90.0) % 360, _MAX_TURN_RATE, self._dt)
        self._advance(hdg, _SPEED_MS, _ALTITUDE_M)
        self.status = DeviceStatus.DEPLOYED

    def _fly_intercept(self) -> None:
        if self._track_est is None:
            self._advance(self._heading, DASH_SPEED_MS, self._alt)
            return
        x, y, vx, vy, alt = self._track_est
        ux, uy = self.xy
        self.solution = solve_intercept(x, y, vx, vy, ux, uy, DASH_SPEED_MS)
        desired = heading_to(ux, uy, self.solution.aim_x, self.solution.aim_y)
        hdg = turn_toward(self._heading, desired, _MAX_TURN_RATE, self._dt)
        self._advance(hdg, DASH_SPEED_MS, alt)

    def _fly_rtb(self) -> None:
        dist = _haversine_m(self._lat, self._lon, self._base_lat, self._base_lon)
        if dist <= _LANDED_RADIUS_M:
            self.mode = UAVMode.LANDING
            return
        desired = _bearing_deg(self._lat, self._lon, self._base_lat, self._base_lon)
        hdg = turn_toward(self._heading, desired, _MAX_TURN_RATE, self._dt)
        self._advance(hdg, min(_RTB_SPEED_MS, dist / self._dt), _ALTITUDE_M)

    def _fly_landing(self) -> None:
        self._speed = 0.0
        self._alt = max(0.0, self._alt - _LAND_RATE_MS * self._dt)
        if self._alt <= 0.0:
            self._lat, self._lon = self._base_lat, self._base_lon
            self.mode = UAVMode.IDLE
            self.status = DeviceStatus.ONLINE

    def _advance(self, heading: float, speed: float, alt_cmd: float) -> None:
        self._heading = heading
        self._speed   = speed
        self._lat, self._lon = _move(self._lat, self._lon, heading, speed * self._dt)
        self._alt += max(-_CLIMB_RATE_MS * self._dt,
                         min(_CLIMB_RATE_MS * self._dt, alt_cmd - self._alt))


def _segment_min_norm(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Minimum |a + s(b − a)| for s ∈ [0, 1]."""
    d = [bi - ai for ai, bi in zip(a, b)]
    dd = sum(c * c for c in d)
    s = 0.0 if dd < 1e-12 else max(0.0, min(1.0, -sum(ai * di for ai, di in zip(a, d)) / dd))
    return math.sqrt(sum((ai + s * di) ** 2 for ai, di in zip(a, d)))
