"""
UGV — ground vehicle with a directional RF jammer (soft kill) and CHARGES
kinetic rounds (hard kill) against enemy UGVs or UAVs.

Mobility
────────
UGVs drive only on drivable terrain.  Every move is a route request through
`route_request`, answered by the scenario's route provider (artemides-trax
A* over segmented terrain / traversability) and delivered with
`set_route()`.  Until a route arrives the vehicle keeps following its
current (already drivable) route or holds; if the router cannot find a
route the vehicle holds and reports NO ROUTE — it never cuts across
terrain on its own.  Offline (no artemides link) the provider answers with a
straight line, labelled as such.

Speed depends on the ground under the vehicle: 15–80 km/h from the
drivability class (see sim/drivability.py), UNKNOWN_SPEED_KMH without data.

Jammer effect model
───────────────────
Beam of JAM_BEAM_DEG pointed at the assigned track's *estimated* position.
Any airborne target inside the beam and within JAM_RANGE_M accumulates
dwell time; after JAM_DWELL_S of continuous illumination each further second
has P_JAM_PER_S chance of breaking the control/GNSS link → target.jam()
(it then descends and lands).  The beam is not identity-aware — collateral
effect on neutral aircraft inside the beam is real, which is why the
engagement manager only points it at approved hostile tracks.  Enemy UGVs
are remote-controlled too: a jammed vehicle stops (DISABLED).

Kinetic charges
───────────────
CHARGES rounds per vehicle.  In CHARGE mode the UGV fires at the assigned
track's estimated position once it is within range (3 km ground, 2 km air)
and the launcher has reloaded (RELOAD_S).  The round resolves against the
real target nearest the aim point (within RESOLVE_RADIUS_M): P_HIT_GROUND /
P_HIT_AIR.  Every shot costs a round, hit or miss.

Carries RadarSensor + CameraSensor.
"""
from __future__ import annotations
import random
from typing import Callable
from ..models import GeoCoord, DeviceStatus, UGVTelemetry
from ..target import AerialTarget, _move, _bearing_deg, _haversine_m
from ..sensors.radar  import RadarSensor
from ..sensors.camera import CameraSensor
from ..drivability import UNKNOWN_SPEED_KMH

_BATTERY_DRAIN = 0.0015         # % per second
_WP_THRESH_M   = 15.0

JAM_RANGE_M   = 2_000.0
JAM_BEAM_DEG  = 60.0
JAM_DWELL_S   = 3.0
P_JAM_PER_S   = 0.5

CHARGES             = 3
CHARGE_RANGE_GROUND = 3_000.0
CHARGE_RANGE_AIR    = 2_000.0
RELOAD_S            = 8.0
P_HIT_GROUND        = 0.8
P_HIT_AIR           = 0.6
RESOLVE_RADIUS_M    = 150.0


class UGV:
    def __init__(self, dt: float = 0.1, seed: int = 20,
                 home: tuple[float, float] = (42.2674, 21.6013),
                 device_id: str = "UGV-BRAVO-02",
                 speed_fn: Callable[[float, float], float] | None = None,
                 charges: int = CHARGES) -> None:
        self.DEVICE_ID = device_id
        self._dt      = dt
        self._rng     = random.Random(seed)
        self._lat, self._lon = home
        self.home     = home
        self._battery = 92.3
        self._heading = 90.0
        self._speed   = 0.0
        self._speed_fn = speed_fn or (lambda lat, lon: UNKNOWN_SPEED_KMH / 3.6)
        self.status   = DeviceStatus.DEPLOYED

        # Route following
        self.route: list[tuple[float, float]] = []
        self.route_source = "at home"
        self.goal: tuple[float, float] | None = home
        self.route_request: tuple[tuple[float, float], tuple[float, float]] | None = None
        self.terrain_class = "UNKNOWN"

        # Weapons: jammer + kinetic charges
        self.assigned_track: str | None = None
        self.weapon = "JAM"                                   # JAM | CHARGE
        self.jam_aim: tuple[float, float] | None = None      # lat, lon of track estimate
        self.aim_domain = "AIR"
        self.jamming = False
        self._dwell: dict[str, float] = {}
        self.charges = charges
        self.max_charges = charges
        self._reload = 0.0
        self.last_shot: dict | None = None

        # Sensors
        self.radar  = RadarSensor(f"RAD-{device_id}", range_m=5_000, seed=seed+1)
        self.camera = CameraSensor(f"CAM-{device_id}", night_vision=True, seed=seed+2)

    # ── public interface ──────────────────────────────────────────────────

    @property
    def position(self) -> GeoCoord:
        return GeoCoord(self._lat, self._lon, 0.0)

    @property
    def heading_deg(self) -> float:
        return self._heading

    @property
    def available(self) -> bool:
        return self.assigned_track is None and self._battery > 15.0

    def charge_range(self, domain: str) -> float:
        return CHARGE_RANGE_GROUND if domain == "GROUND" else CHARGE_RANGE_AIR

    def navigate_to(self, lat: float, lon: float) -> None:
        """Request a drivable route to (lat, lon); the route provider fulfils it."""
        self.goal = (lat, lon)
        self.route_request = ((self._lat, self._lon), (lat, lon))
        if self.route:
            self.route_source = self.route_source.split(" ")[0] + " (re-routing…)"
        else:
            self.route_source = "route pending…"

    def set_route(self, waypoints: list[tuple[float, float]], source: str) -> None:
        wps = list(waypoints)
        if not wps:
            # No drivable route: stop and hold where we are
            self.route = []
            self.route_source = source
            return
        if len(wps) > 1:
            # Join the planned route at the waypoint nearest to where we are now
            i = min(range(len(wps)), key=lambda k: _haversine_m(self._lat, self._lon, *wps[k]))
            wps = wps[i:]
        self.route = wps
        self.route_source = source

    def assign(self, track_id: str, weapon: str = "JAM", domain: str = "AIR") -> None:
        self.assigned_track = track_id
        self.weapon = weapon
        self.aim_domain = domain
        self._dwell.clear()

    def release(self) -> None:
        self.assigned_track = None
        self.jam_aim = None
        self.jamming = False
        self.weapon = "JAM"
        self._dwell.clear()

    def step(self, target: AerialTarget | None, timestamp: float) -> UGVTelemetry:
        self._drive()
        self._battery = max(0.0, self._battery - _BATTERY_DRAIN * self._dt)
        self._reload = max(0.0, self._reload - self._dt)

        self.radar .update_platform(self._lat, self._lon, self._heading, 2.0)
        self.camera.update_platform(self._lat, self._lon, self._heading)

        radar_ret  = self.radar .sample(target, timestamp) if target is not None else None
        camera_det = self.camera.sample(target, timestamp) if target is not None else None

        return UGVTelemetry(
            device_id   = self.DEVICE_ID,
            timestamp   = timestamp,
            position    = self.position,
            speed_ms    = round(max(0.0, self._speed + (self._rng.gauss(0.0, 0.1) if self._speed else 0.0)), 2),
            heading_deg = round(self._heading, 1),
            battery_pct = round(self._battery, 2),
            status      = self.status,
            terrain_mode= self.terrain_class,
            radar       = radar_ret,
            camera      = camera_det,
        )

    def in_jam_range(self, lat: float, lon: float) -> bool:
        return _haversine_m(self._lat, self._lon, lat, lon) <= JAM_RANGE_M

    def evaluate_effect(self, targets: list[AerialTarget]) -> list[AerialTarget]:
        """Jammer effect for this tick.  Returns targets whose link was broken."""
        jammed: list[AerialTarget] = []
        self.jamming = (self.assigned_track is not None and self.weapon == "JAM"
                        and self.jam_aim is not None and self.in_jam_range(*self.jam_aim))
        if not self.jamming:
            self._dwell.clear()
            return jammed
        beam_az = _bearing_deg(self._lat, self._lon, *self.jam_aim)
        for tgt in targets:
            if not tgt.engageable or not getattr(tgt, "jammable", True):
                continue
            p = tgt.position
            az = _bearing_deg(self._lat, self._lon, p.lat, p.lon)
            off = abs((az - beam_az + 180) % 360 - 180)
            if off > JAM_BEAM_DEG / 2 or not self.in_jam_range(p.lat, p.lon):
                self._dwell.pop(tgt.target_id, None)
                continue
            dwell = self._dwell.get(tgt.target_id, 0.0) + self._dt
            self._dwell[tgt.target_id] = dwell
            if dwell >= JAM_DWELL_S and self._rng.random() < P_JAM_PER_S * self._dt:
                tgt.jam()
                jammed.append(tgt)
        return jammed

    def evaluate_charge(self, targets: list, timestamp: float) -> list[tuple[object | None, bool]]:
        """
        Fire a charge at the assigned track if in range and reloaded.
        Returns [(target_or_None, hit)] for the shot fired this tick (if any).
        """
        if (self.assigned_track is None or self.weapon != "CHARGE" or self.jam_aim is None
                or self.charges <= 0 or self._reload > 0):
            return []
        alat, alon = self.jam_aim
        if _haversine_m(self._lat, self._lon, alat, alon) > self.charge_range(self.aim_domain):
            return []
        self.charges -= 1
        self._reload = RELOAD_S
        cands = [t for t in targets if t.engageable and getattr(t, "domain", "AIR") == self.aim_domain]
        tgt = min(cands, key=lambda t: t.distance_to_m(alat, alon), default=None)
        if tgt is not None and tgt.distance_to_m(alat, alon) > RESOLVE_RADIUS_M:
            tgt = None
        p_hit = P_HIT_GROUND if self.aim_domain == "GROUND" else P_HIT_AIR
        hit = tgt is not None and self._rng.random() < p_hit
        if hit:
            tgt.destroy()
        self.last_shot = {"t": timestamp, "lat": alat, "lon": alon, "hit": hit}
        return [(tgt, hit)]

    # ── private ───────────────────────────────────────────────────────────

    def _drive(self) -> None:
        # Skip waypoints already reached
        while self.route and _haversine_m(self._lat, self._lon, *self.route[0]) < _WP_THRESH_M:
            self.route.pop(0)
        if not self.route:
            self._speed = 0.0
            self.status = DeviceStatus.DEPLOYED
            return

        self.status   = DeviceStatus.DEPLOYING
        wp_lat, wp_lon = self.route[0]
        self._heading = _bearing_deg(self._lat, self._lon, wp_lat, wp_lon)
        self._speed   = self._speed_fn(self._lat, self._lon)
        dist_step = min(self._speed * self._dt,
                        _haversine_m(self._lat, self._lon, wp_lat, wp_lon))
        self._lat, self._lon = _move(self._lat, self._lon, self._heading, dist_step)
