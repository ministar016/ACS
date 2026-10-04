"""
Scenario — end-to-end counter-UAS simulation.

    targets ─▶ sensors ─▶ tracker ─▶ threat evaluation ─▶ engagement manager
       ▲                                                         │
       └──────────── effectors (interceptor UAVs, UGV jammers) ◀─┘

Call scenario.step() at your desired rate (e.g. every 100 ms for 10 Hz).
Returns a ScenarioSnapshot with sensor data, tracks, engagements and ground
truth.

Everything is placed by a Laydown (sim/laydown.py — default Preševo Valley,
artemides-trax `vojsrb`; editable and saveable from the GUI):
  • protected asset + hexagonal restricted zone and warning buffer
  • surveillance radars (30 km) and acoustic arrays (10 km, bearing only),
    seismic nodes (ground targets only)
  • interceptor drones idle on the pad at the base — they launch on an
    engagement or an operator call and are invisible until airborne
  • UGV jammers at operator-chosen positions, moving only on drivable routes

Default threat picture:
  HOSTILE-A  fixed-wing from the west, transit that cuts through the zone
  HOSTILE-B  quadcopter spawning at t=60 s in the south-east, homing on BASE
  CIVIL-C    neutral transit well south of the zone — must NOT be engaged
  CONVOY     4 enemy trucks / UGVs assembling in the south (North Macedonian
             border side), one artemides A* road route north to an objective
             near the base, vehicles 25 s apart.  The air element — 15 attack
             UAVs + 2 attack helicopters — launches in the west (Kosovo side),
             flies to the convoy and takes up formation on both flanks; the
             trucks move off once it is on station (rendezvous).  When the lead
             is within 2.5 km of the base (or at its objective, or the convoy is
             lost) air and ground attack together: UAVs strike the base,
             helicopters fire missiles from 1.5 km stand-off

Air defence: PVO sites fire autonomously (one shot per minute each) at
hostile drones in range.  UGVs carry 3 charges against enemy UGVs or UAVs.

Route provider
──────────────
UGVs ask for ground routes through `route_provider.request(...)`, which
returns a handle with .done() / .result() → (waypoints, source).  An empty
waypoint list means "no drivable route" and the UGV holds.  Offline the
StraightLineRouter answers immediately; the GUI swaps in the artemides-trax
A* router (see integrations/artemides.py) without the scenario knowing.
"""
from __future__ import annotations
import dataclasses
import math
import random

from .models import (
    GeoCoord, Velocity, Track, ThreatLevel, ScenarioSnapshot,
    AcousticReading, SeismicReading,
)
from .target import (AerialTarget, AttackHelicopter, EscortDrone, GroundTarget, TargetState,
                     _bearing_deg, _haversine_m, _move)
from .devices.uav import UAV
from .devices.ugv import UGV
from .sensors.acoustic import AcousticSensor
from .sensors.seismic  import SeismicSensor
from .sensors.radar    import RadarSensor
from .zone import LocalFrame, RestrictedZone, ProtectedAsset
from .laydown import Laydown, DEFAULT_LAYDOWN, ACOUSTIC_RANGE_M, RADAR_RANGE_M
SEISMIC_RANGE_M = 10_000.0
from .drivability import DrivabilityGrid, UNKNOWN_SPEED_KMH
from .tracker import (MultiTargetTracker, TrackStatus, BearingMeas, PositionMeas,
                      radar_to_meas)
from .threat import ThreatEvaluator
from .engagement import EngagementManager, TrackView, PvoSite


_ACOUSTIC_SIGMA_RAD = math.radians(3.0)
_UAV_CALLSIGNS = ("ALPHA", "DELTA", "ECHO", "FOXTROT", "GOLF", "HOTEL")
_PVO_RESOLVE_M = 250.0          # PVO round resolves against a drone this close to the aim point
_P_PVO_KILL    = 1.0            # "every minute one drone in range is destroyed"
_SITE_GROUND_RANGE_M = 12_000.0 # surveillance radar GMTI mode
_P_MISSILE_HIT = 0.6            # attack-helicopter missile vs. the base
_AXIS_SMOOTH   = 0.01           # per-tick EMA of the convoy's direction of advance (~10 s)
# Classified platform types that jump the engagement queue (lower = more urgent):
# an attack helicopter fires stand-off missiles, so it outranks a single drone.
_CLASS_PRIORITY = {"ATTACK_HELICOPTER": 0.25}
_SEISMIC_SIGMA_RAD = math.radians(8.0)
_RENDEZVOUS_M      = 1_200.0    # air element "on station" within this of its slot
_RENDEZVOUS_FRAC   = 0.8
_BEARING_SHOW_S    = 1.6        # how long a bearing detection stays on the map
_ACOUSTIC_GROUND_M = 3_000.0    # wedge length for acoustic detections of vehicles

# Sensor revisit periods (s): a surveillance radar reports once per antenna
# rotation, acoustic arrays integrate ~1 s, onboard sensors run faster.
SITE_RADAR_PERIOD_S = 1.0
ONBOARD_PERIOD_S    = 0.5
ACOUSTIC_PERIOD_S   = 1.0


def build_targets(laydown: Laydown, dt: float, seed: int) -> list[AerialTarget]:
    base = (laydown.base.lat, laydown.base.lon)
    out = []
    for i, t in enumerate(laydown.threats):
        lat, lon = laydown.threat_start(t)
        out.append(AerialTarget(
            t.target_id, lat, lon, heading=t.heading, speed_ms=t.speed_kmh / 3.6,
            altitude_m=t.altitude_m, dt=dt, seed=seed + i, spawn_time=t.spawn_time,
            aim_point=base if t.homing else None, bounds=laydown.area_bounds,
            hostile=t.hostile, rcs_dbsm=t.rcs_dbsm, drone_class=t.drone_class))
    return out


def build_zone(laydown: Laydown, frame: LocalFrame) -> RestrictedZone:
    r = laydown.zone_radius_m
    verts = []
    for k in range(6):
        a = math.radians(30 + 60 * k)
        verts.append(frame.to_latlon(r * math.sin(a), r * math.cos(a)))
    return RestrictedZone("ZONE-BRAVO", verts, frame,
                          ProtectedAsset(laydown.base.site_id, laydown.base.lat, laydown.base.lon),
                          buffer_m=laydown.zone_buffer_m)


# ── Route providers ───────────────────────────────────────────────────────────

class _ReadyRoute:
    def __init__(self, waypoints, source):
        self._r = (waypoints, source)

    def done(self) -> bool:
        return True

    def result(self):
        return self._r


class StraightLineRouter:
    """Offline fallback (no terrain data at all): drive straight to the goal."""

    def request(self, vehicle_id: str, start: tuple[float, float],
                goal: tuple[float, float], via=None) -> _ReadyRoute:
        return _ReadyRoute(list(via or []) + [goal], "offline straight-line")


# ── IFF: our own airborne UAVs as radar-visible objects ───────────────────────

class _FriendlyEmitter:
    """Adapts a friendly platform to the sensor-target interface."""

    rcs_dbsm = -12.0
    drone_class = "FRIENDLY_UAV"
    domain = "AIR"

    def __init__(self, platform: UAV) -> None:
        self._p = platform

    @property
    def alive(self) -> bool:
        return self._p.airborne

    @property
    def position(self) -> GeoCoord:
        return self._p.position

    def distance_to_m(self, lat, lon):
        return _haversine_m(self._p.position.lat, self._p.position.lon, lat, lon)

    def bearing_from_m(self, lat, lon):
        return _bearing_deg(lat, lon, self._p.position.lat, self._p.position.lon)

    def radial_velocity_ms(self, lat, lon):
        b = _bearing_deg(lat, lon, self._p.position.lat, self._p.position.lon)
        return -self._p._speed * math.cos(math.radians(self._p.heading_deg - b))


class Scenario:
    """
    Full AMCS counter-UAS scenario.

    Usage
    -----
    scenario = Scenario(dt=0.1, auto_roe=True)
    for _ in range(6000):                 # 10 minutes at 10 Hz
        snap = scenario.step()
    """

    def __init__(self, dt: float = 0.1, seed: int = 42, auto_roe: bool = False,
                 targets: list[AerialTarget] | None = None,
                 route_provider=None, laydown: Laydown = DEFAULT_LAYDOWN,
                 drivability: DrivabilityGrid | None = None) -> None:
        self._dt   = dt
        self._t    = 0.0
        self._rng  = random.Random(seed)
        self.laydown = laydown
        self.drivability = drivability
        base = laydown.base

        self.frame = LocalFrame(base.lat, base.lon)
        self.zone  = build_zone(laydown, self.frame)

        # Ground truth
        self.targets: list = targets if targets is not None else build_targets(laydown, dt, seed)
        self.convoy: list[GroundTarget] = []
        self.escorts: list[EscortDrone] = []           # UAVs + helicopters
        self.helicopters: list[AttackHelicopter] = []
        self._axis_deg = 0.0
        self._convoy_go = False
        self._escort_since: dict[str, float] = {}      # air track → first time seen with a hostile vehicle
        self._escorting: set[str] = set()              # air tracks declared part of the hostile force
        self.bearing_display: dict[str, tuple[float, list]] = {}   # sensor → (t, [(brg, range, kind)])
        if targets is None and laydown.convoy is not None and \
                (laydown.convoy.vehicles + laydown.convoy.escort_drones + laydown.convoy.aviation > 0):
            self._build_convoy(laydown, dt, seed)
        self.base_hits = 0
        self.assaults = 0
        self._outcomes_reported: set[str] = set()

        # Field sensors
        self.acoustic_sensors: list[AcousticSensor] = [
            AcousticSensor(s.site_id, s.lat, s.lon, seed=seed + i)
            for i, s in enumerate(laydown.acoustic)
        ]
        self.seismic_sensors: list[SeismicSensor] = [
            SeismicSensor(s.site_id, s.lat, s.lon, seed=seed + 10 + i)
            for i, s in enumerate(laydown.seismic)
        ]
        self.radars: list[RadarSensor] = []
        for i, s in enumerate(laydown.radars):
            r = RadarSensor(s.site_id, range_m=RADAR_RANGE_M, seed=seed + 40 + i,
                            ground_range_m=_SITE_GROUND_RANGE_M)
            r.update_platform(s.lat, s.lon, 0.0, 10.0)
            self.radars.append(r)

        # Effectors
        self.uavs: list[UAV] = [
            UAV(dt=dt, seed=seed + 20 + 7 * i, frame=self.frame, base=(base.lat, base.lon),
                device_id=f"UAV-{_UAV_CALLSIGNS[i % len(_UAV_CALLSIGNS)]}-{i + 1:03d}")
            for i in range(laydown.interceptors)
        ]
        self.ugvs: list[UGV] = [
            UGV(dt=dt, seed=seed + 30 + 7 * i, home=(s.lat, s.lon), device_id=s.site_id,
                speed_fn=self._ugv_speed, charges=laydown.ugv_charges)
            for i, s in enumerate(laydown.ugvs)
        ]
        self._friendly_uavs = [_FriendlyEmitter(u) for u in self.uavs]

        # C2 chain
        self.tracker  = MultiTargetTracker()
        self.threats  = ThreatEvaluator(self.zone)
        pvo = []
        for p in laydown.pvo:
            pvo.append(PvoSite(p.site_id, p.lat, p.lon, p.range_m, p.ammo))
        self.engage   = EngagementManager(self.frame, self.zone, self.uavs, self.ugvs,
                                          auto_roe=auto_roe, ground_bbox=laydown.ground_bbox,
                                          drivability=drivability, pvo_sites=pvo)
        self.route_provider = route_provider or StraightLineRouter()
        self._route_pending: dict[str, tuple] = {}
        self.last_threats: dict = {}
        self.convoy_route_source = "none"
        self._convoy_route_handle = None
        if self.convoy:
            c = laydown.convoy
            self._convoy_plan = (laydown.at(*c.start_km),
                                 [laydown.at(*v) for v in c.via_km],
                                 laydown.at(*c.objective_km))
            start, via, goal = self._convoy_plan
            self._convoy_route_handle = self.route_provider.request("ENEMY-CONVOY", start, goal, via=via)
            self.convoy_route_source = "route pending…"

    # ── enemy convoy ──────────────────────────────────────────────────────

    def _build_convoy(self, laydown: Laydown, dt: float, seed: int) -> None:
        c = laydown.convoy
        rng = random.Random(seed + 500)
        slat, slon = laydown.at(*c.start_km)
        olat, olon = laydown.at(*c.objective_km)
        base = (laydown.base.lat, laydown.base.lon)
        self._axis_deg = _bearing_deg(slat, slon, olat, olon)
        for i in range(c.vehicles):
            # Trucks wait at the assembly point until the air element is on station
            self.convoy.append(GroundTarget(
                f"ENEMY-UGV-{i + 1}", slat, slon, dt=dt, seed=seed + 600 + i,
                spawn_time=float("inf"), speed_fn=self._enemy_speed))
        air0 = laydown.at(*c.air_start_km) if c.air_start_km else None

        def axis():
            lead = self._convoy_lead()
            if lead is not None:
                return lead.position.lat, lead.position.lon, self._axis_deg, lead._speed
            return slat, slon, self._axis_deg, 0.0

        def release():
            if not self.convoy:
                return True                          # air element without vehicles: straight to the attack
            lead = self._convoy_lead()
            if lead is None:
                # convoy destroyed or not yet moving: attack once it has started
                return any(v.state != TargetState.PENDING for v in self.convoy)
            return (lead.state == TargetState.ARRIVED or
                    _haversine_m(lead.position.lat, lead.position.lon, *base) <= c.release_dist_m)

        def spawn_at(slot):
            if air0 is not None:
                # Launch from the air start, spread ~150 m apart
                k = len(self.escorts)
                return _move(air0[0], air0[1], (k * 47) % 360, 150.0 * (k % 5))
            along, cross = slot
            lat, lon = _move(slat, slon, self._axis_deg if along >= 0 else (self._axis_deg + 180) % 360, abs(along))
            return _move(lat, lon, (self._axis_deg + (90 if cross >= 0 else 270)) % 360, abs(cross))

        # Attack UAVs: two columns on the flanks, staggered from ahead of the lead to behind it
        flank = c.escort_radius_m
        for k in range(c.escort_drones):
            side = 1 if k % 2 == 0 else -1
            row = k // 2
            slot = (700.0 - row * 260.0, side * (flank + (row % 2) * 250.0))
            quad = k % 3 != 0
            lat, lon = spawn_at(slot)
            self.escorts.append(EscortDrone(
                f"ESCORT-{k + 1:02d}", lat, lon, heading=_bearing_deg(lat, lon, slat, slon),
                speed_ms=rng.uniform(60, 120) / 3.6, altitude_m=rng.uniform(60, 150),
                dt=dt, seed=seed + 700 + k, spawn_time=c.spawn_time,
                bounds=laydown.area_bounds, hostile=True,
                rcs_dbsm=-20.0 if quad else -15.0,
                drone_class="UAV_QUADCOPTER" if quad else "UAV_FIXED_WING",
                axis_fn=axis, release_fn=release, strike_point=base, slot=slot))

        # Attack helicopters: close in over the column, one each side
        for j in range(c.aviation):
            side = 1 if j % 2 == 0 else -1
            slot = (250.0 - (j // 2) * 400.0, side * 250.0)
            lat, lon = spawn_at(slot)
            helo = AttackHelicopter(
                f"HELO-{j + 1}", lat, lon, heading=_bearing_deg(lat, lon, slat, slon), speed_ms=0.0,
                altitude_m=120.0, dt=dt, seed=seed + 800 + j, spawn_time=c.spawn_time,
                bounds=laydown.area_bounds, hostile=True, rcs_dbsm=5.0,
                drone_class="ATTACK_HELICOPTER",
                axis_fn=axis, release_fn=release, strike_point=base, slot=slot)
            self.helicopters.append(helo)
            self.escorts.append(helo)
        self.targets = self.targets + self.convoy + self.escorts

    def _check_rendezvous(self) -> None:
        """Trucks move off once the air element is on station (or on timeout)."""
        if self._convoy_go or not self.convoy or self.convoy[0].route is None:
            return
        c = self.laydown.convoy
        air = [e for e in self.escorts if e.alive and not e.released]
        if air:
            on_station = 0
            for e in air:
                slot = e.slot_position()
                if slot is not None and e.distance_to_m(*slot) <= _RENDEZVOUS_M:
                    on_station += 1
            ready = on_station >= _RENDEZVOUS_FRAC * len(air)
        else:
            ready = True
        timed_out = self._t >= c.spawn_time + c.rendezvous_timeout_s
        if ready or timed_out:
            self._convoy_go = True
            for i, v in enumerate(self.convoy):
                v.spawn_time = v.elapsed_s + i * c.spacing_s
            why = "air element on station" if ready else "rendezvous timeout"
            self.engage._log("INFO", f"Enemy convoy moving off ({why}) — {len(self.convoy)} vehicles")

    def _update_axis(self) -> None:
        """Smoothed direction of advance of the convoy lead (follows road bends slowly)."""
        lead = self._convoy_lead()
        if lead is None or lead._speed < 1.0:
            return
        err = (lead.velocity.heading_deg - self._axis_deg + 180) % 360 - 180
        self._axis_deg = (self._axis_deg + _AXIS_SMOOTH * err) % 360

    def _helicopter_fire(self) -> None:
        for h in self.helicopters:
            for _ in range(h.pop_shots()):
                if self._rng.random() < _P_MISSILE_HIT:
                    self.base_hits += 1
                    self.engage._log("ALERT", f"BASE HIT — {h.target_id} missile from stand-off "
                                              f"({h.missiles} left)")
                else:
                    self.engage._log("WARN", f"{h.target_id} missile missed {self.laydown.base.site_id} "
                                             f"({h.missiles} left)")

    def _convoy_lead(self) -> GroundTarget | None:
        for v in self.convoy:
            if v.state in (TargetState.MOVING, TargetState.ARRIVED):
                return v
        return None

    def _enemy_speed(self, lat: float, lon: float) -> float:
        if self.drivability is None:
            return GroundTarget.DEFAULT_SPEED_KMH / 3.6
        return self.drivability.speed_ms_at(lat, lon)

    def _service_convoy_route(self) -> None:
        h = self._convoy_route_handle
        if h is None or not h.done():
            return
        self._convoy_route_handle = None
        waypoints, source = h.result()
        start, via, goal = self._convoy_plan
        if not waypoints:
            # The enemy does not wait for our router: fall back to its plan
            waypoints, source = via + [goal], f"straight-line fallback ({source})"
        self.convoy_route_source = source
        for v in self.convoy:
            v.set_route(waypoints)

    # ── drivability ───────────────────────────────────────────────────────

    def set_drivability(self, grid: DrivabilityGrid | None) -> None:
        self.drivability = grid
        self.engage.drivability = grid

    def _ugv_speed(self, lat: float, lon: float) -> float:
        if self.drivability is None:
            return UNKNOWN_SPEED_KMH / 3.6
        return self.drivability.speed_ms_at(lat, lon)

    # ── main tick ─────────────────────────────────────────────────────────

    def step(self) -> ScenarioSnapshot:
        self._t += self._dt
        ts = self._t

        self._service_convoy_route()
        self._check_rendezvous()
        self._update_axis()
        for tgt in self.targets:
            tgt.step()
        self._helicopter_fire()
        alive = [t for t in self.targets if t.alive]
        fallback = self.targets[0] if self.targets else None
        self._score_outcomes()

        self._service_routes()

        # Per-sensor readings (nearest target) for the panels
        acoustic_readings: list[AcousticReading] = [
            s.sample(self._nearest(alive, GeoCoord(s._lat, s._lon)) or fallback, ts)
            for s in self.acoustic_sensors
        ] if fallback else []
        seismic_readings: list[SeismicReading] = [
            s.sample(self._nearest(self.targets, GeoCoord(s._lat, s._lon)), ts)
            for s in self.seismic_sensors
        ] if fallback else []

        # Devices (each also reads its own sensors against the nearest target)
        uav_tel = [u.step(self._nearest(alive, u.position) or fallback, ts) for u in self.uavs]
        ugv_tel = [g.step(self._nearest(alive, g.position) or fallback, ts) for g in self.ugvs]
        if self.drivability is not None:
            for g in self.ugvs:
                g.terrain_class = self.drivability.classify_at(g.position.lat, g.position.lon)[0]

        # ── Sense → track ────────────────────────────────────────────────
        positions, bearings, classes = self._collect_measurements(ts, alive)
        friendlies = [u.xy for u in self.uavs if u.airborne] + \
                     [self.frame.to_xy(g.position.lat, g.position.lon) for g in self.ugvs]
        self.tracker.update(ts, positions, bearings, friendlies, classes)

        # ── Evaluate threat ──────────────────────────────────────────────
        views: dict[str, TrackView] = {}
        threats = {}
        for trk in self.tracker.tracks:
            confirmed = trk.status != TrackStatus.TENTATIVE
            views[trk.track_id] = TrackView(trk.track_id, trk.x[0], trk.x[1],
                                            trk.x[2], trk.x[3], trk.alt, confirmed, trk.domain,
                                            trk.obj_class)
            threats[trk.track_id] = self.threats.assess(
                trk.track_id, trk.x[0], trk.x[1], trk.x[2], trk.x[3], confirmed, trk.domain)
        # Escort rule: air tracks flying with a hostile ground force are hostile too
        hostile_ground = [v for tid, v in views.items()
                          if v.domain == "GROUND" and threats[tid].identity.name == "HOSTILE"]
        from .threat import ESCORT_ASSOC_M, ESCORT_DWELL_S
        for tid, v in views.items():
            if v.domain == "GROUND" or not v.confirmed:
                continue
            ta = threats[tid]
            if ta.level == ThreatLevel.HIGH and ta.identity.name == "HOSTILE":
                continue                                   # already HIGH on its own kinematics
            d = min((math.hypot(v.x - g.x, v.y - g.y) for g in hostile_ground), default=1e9)
            if d > ESCORT_ASSOC_M:
                self._escort_since.pop(tid, None)
                continue
            since = self._escort_since.setdefault(tid, ts)
            if tid in self._escorting or ts - since >= ESCORT_DWELL_S:
                self._escorting.add(tid)
                threats[tid] = self.threats.as_escort(tid, ta, d)
        for tid, v in views.items():
            w = _CLASS_PRIORITY.get(v.obj_class)
            if w is not None and threats[tid].identity.name == "HOSTILE":
                threats[tid] = dataclasses.replace(threats[tid], priority=threats[tid].priority * w)
        self.last_threats = threats

        # ── Decide / engage ──────────────────────────────────────────────
        self.engage.step(ts, views, threats)

        # ── Effect / assess ──────────────────────────────────────────────
        for uav in self.uavs:
            for tgt, hit in uav.evaluate_effect(self.targets):
                self.engage.report_effect(uav.DEVICE_ID, tgt.target_id, hit, "hard kill")
        for ugv in self.ugvs:
            for tgt in ugv.evaluate_effect(self.targets):
                self.engage.report_effect(ugv.DEVICE_ID, tgt.target_id, True, "RF jam")
            for tgt, hit in ugv.evaluate_charge(self.targets, ts):
                self.engage.report_effect(ugv.DEVICE_ID, tgt.target_id if tgt else "—", hit,
                                          f"charge ({ugv.charges} left)")
        for site, tid, lat, lon in self.engage.pvo_fire(views, threats):
            cands = [t for t in self.targets if t.engageable and getattr(t, "domain", "AIR") == "AIR"]
            tgt = min(cands, key=lambda t: t.distance_to_m(lat, lon), default=None)
            if tgt is not None and tgt.distance_to_m(lat, lon) > _PVO_RESOLVE_M:
                tgt = None
            hit = tgt is not None and self._rng.random() < _P_PVO_KILL
            if hit:
                tgt.destroy()
            self.engage.report_pvo(site, tid, tgt.target_id if tgt else None, hit, lat, lon)

        tracks = self._build_tracks(ts, threats)
        threat = max((t.threat_level for t in tracks), default=ThreatLevel.NONE,
                     key=lambda lvl: lvl.value)

        return ScenarioSnapshot(
            timestamp           = round(ts, 3),
            target_position     = fallback.position if fallback else GeoCoord(0, 0),
            acoustic_readings   = acoustic_readings,
            seismic_readings    = seismic_readings,
            uavs                = uav_tel,
            ugvs                = ugv_tel,
            tracks              = tracks,
            threat_level        = threat,
            targets             = self.targets,
            engagements         = list(self.engage.engagements.values()),
            base_hits           = self.base_hits,
            assaults            = self.assaults,
        )

    def _score_outcomes(self) -> None:
        for t in self.targets:
            if t.target_id in self._outcomes_reported:
                continue
            if t.state == TargetState.IMPACT:
                self._outcomes_reported.add(t.target_id)
                self.base_hits += 1
                self.engage._log("ALERT", f"BASE HIT — {t.target_id} ({t.drone_class}) struck {self.laydown.base.site_id}")
            elif t.state == TargetState.ARRIVED:
                self._outcomes_reported.add(t.target_id)
                self.assaults += 1
                self.engage._log("ALERT", f"BASE ASSAULT — {t.target_id} reached its objective")

    # ── private helpers ───────────────────────────────────────────────────

    @staticmethod
    def _nearest(cands, pos: GeoCoord):
        return min(cands, key=lambda t: t.distance_to_m(pos.lat, pos.lon), default=None)

    def _service_routes(self) -> None:
        for ugv in self.ugvs:
            if ugv.route_request is not None:
                start, goal = ugv.route_request
                ugv.route_request = None
                self._route_pending[ugv.DEVICE_ID] = (
                    goal, self.route_provider.request(ugv.DEVICE_ID, start, goal))
            pending = self._route_pending.get(ugv.DEVICE_ID)
            if pending is not None and pending[1].done():
                del self._route_pending[ugv.DEVICE_ID]
                goal, handle = pending
                if goal == ugv.goal:                # ignore superseded requests
                    waypoints, source = handle.result()
                    ugv.set_route(waypoints, source)

    def recent_bearings(self, width_deg: float = 15.0) -> list[dict]:
        """
        Bearing detections from the last sensor cycle as map sectors.

        Each detection is a width_deg wedge; wedges of the same sensor (and
        range class) that touch are merged into one sector, so a sensor hearing
        a whole swarm adds one translucent layer — brightness on the map then
        counts *sensors* agreeing, not targets.
        """
        half = width_deg / 2
        out = []
        for sid, (t, kind, lat, lon, shown) in self.bearing_display.items():
            if self._t - t > _BEARING_SHOW_S:
                continue
            by_range: dict[float, list[float]] = {}
            for brg, rng in shown:
                by_range.setdefault(rng, []).append(brg % 360)
            for rng, brgs in by_range.items():
                brgs.sort()
                sectors = [[brgs[0] - half, brgs[0] + half]]
                for b in brgs[1:]:
                    if b - half <= sectors[-1][1]:
                        sectors[-1][1] = b + half
                    else:
                        sectors.append([b - half, b + half])
                # close the gap across north (e.g. 355° and 3°)
                if len(sectors) > 1 and sectors[0][0] + 360 <= sectors[-1][1]:
                    sectors[-1][1] = sectors[0][1] + 360
                    sectors.pop(0)
                for a0, a1 in sectors:
                    out.append({"kind": kind, "sensorId": sid, "lat": lat, "lon": lon,
                                "fromDeg": round(a0, 1), "toDeg": round(min(a1, a0 + 360), 1),
                                "rangeM": rng})
        return out

    def _due(self, ts: float, period: float, k: int) -> bool:
        """True on the tick where sensor k (staggered) completes its revisit."""
        phase = (k * 0.37) % period
        return int((ts + phase) / period) != int((ts - self._dt + phase) / period)

    def _collect_measurements(self, ts: float, alive: list[AerialTarget]):
        positions: list[PositionMeas] = []
        bearings:  list[BearingMeas]  = []
        classes:   list[tuple[float, float, str]] = []

        airborne_friendlies = [f for f, u in zip(self._friendly_uavs, self.uavs) if u.airborne]
        radars = [(r, r._plat_lat, r._plat_lon, 10.0, 0.0, alive + airborne_friendlies)
                  for k, r in enumerate(self.radars) if self._due(ts, SITE_RADAR_PERIOD_S, k)]
        for k, uav in enumerate(self.uavs):
            if uav.sensing and self._due(ts, ONBOARD_PERIOD_S, k):
                radars.append((uav.radar, uav.position.lat, uav.position.lon,
                               uav.position.alt, uav.heading_deg, alive))
        for k, ugv in enumerate(self.ugvs):
            if self._due(ts, ONBOARD_PERIOD_S, k + 3):
                radars.append((ugv.radar, ugv.position.lat, ugv.position.lon,
                               2.0, ugv.heading_deg, alive + airborne_friendlies))
        for radar, lat, lon, alt, hdg, objs in radars:
            sx, sy = self.frame.to_xy(lat, lon)
            for obj in objs:
                r = radar.sample(obj, ts)
                if r.target_detected:
                    m = radar_to_meas(
                        radar.sensor_id, sx, sy, alt, r.distance_m,
                        (r.azimuth_deg + hdg) % 360, r.elevation_deg,
                        domain=getattr(obj, "domain", "AIR"))
                    positions.append(m)
                    # Rotor micro-Doppler lets the radar classify helicopters
                    if getattr(obj, "drone_class", "") == "ATTACK_HELICOPTER":
                        classes.append((m.x, m.y, "ATTACK_HELICOPTER"))

        for k, s in enumerate(self.acoustic_sensors):
            if not self._due(ts, ACOUSTIC_PERIOD_S, k + 5):
                continue
            sx, sy = self.frame.to_xy(s._lat, s._lon)
            shown = []
            for tgt in alive:
                r = s.sample(tgt, ts)
                if r.target_detected:
                    bearings.append(BearingMeas(s.sensor_id, sx, sy,
                                                math.radians(r.estimated_bearing),
                                                _ACOUSTIC_SIGMA_RAD, ACOUSTIC_RANGE_M))
                    # The array tells engine from rotor/propeller spectrum → wedge length
                    ground = getattr(tgt, "domain", "AIR") == "GROUND"
                    shown.append((r.estimated_bearing, _ACOUSTIC_GROUND_M if ground else ACOUSTIC_RANGE_M))
            self.bearing_display[s.sensor_id] = (ts, "ACOUSTIC", s._lat, s._lon, shown)

        for k, s in enumerate(self.seismic_sensors):
            if not self._due(ts, ACOUSTIC_PERIOD_S, k + 9):
                continue
            sx, sy = self.frame.to_xy(s._lat, s._lon)
            shown = []
            for tgt in alive:
                r = s.sample(tgt, ts)
                if r.target_detected:
                    bearings.append(BearingMeas(s.sensor_id, sx, sy,
                                                math.radians(r.estimated_bearing),
                                                _SEISMIC_SIGMA_RAD, SEISMIC_RANGE_M, domain="GROUND"))
                    shown.append((r.estimated_bearing, SEISMIC_RANGE_M))
            self.bearing_display[s.sensor_id] = (ts, "SEISMIC", s._lat, s._lon, shown)

        cams = [(u.camera, u.position) for u in self.uavs if u.sensing] + \
               [(g.camera, g.position) for g in self.ugvs]
        if not self._due(ts, ONBOARD_PERIOD_S, 7):
            cams = []
        for cam, plat in cams:
            px, py = self.frame.to_xy(plat.lat, plat.lon)
            for tgt in alive:
                d = cam.sample(tgt, ts)
                if d.target_detected:
                    b = math.radians(d.bearing_deg)
                    classes.append((px + d.estimated_distance_m * math.sin(b),
                                    py + d.estimated_distance_m * math.cos(b),
                                    d.object_class))
        return positions, bearings, classes

    def _build_tracks(self, ts: float, threats) -> list[Track]:
        eng_by_track = {}
        for e in self.engage.engagements.values():
            if e.active or e.track_id not in eng_by_track:
                eng_by_track[e.track_id] = e
        out: list[Track] = []
        for trk in self.tracker.tracks:
            if trk.status == TrackStatus.TENTATIVE:
                continue
            ta = threats[trk.track_id]
            lat, lon = self.frame.to_latlon(trk.x[0], trk.x[1])
            speed = math.hypot(trk.x[2], trk.x[3])
            sigma = math.sqrt(max(trk.P[0][0], 0) + max(trk.P[1][1], 0))
            conf = max(0.0, min(1.0, 1.0 - sigma / 300.0)) * (0.7 if trk.status == TrackStatus.COASTING else 1.0)
            eng = eng_by_track.get(trk.track_id)
            level, reason = ta.level, ta.reason
            if self.engage.is_neutralized(trk.track_id):
                # Neutralised (e.g. jammed and descending) — no longer a threat
                level, reason = ThreatLevel.NONE, "neutralised — " + (eng.result if eng else "")
            out.append(Track(
                track_id        = trk.track_id,
                timestamp       = ts,
                position        = GeoCoord(lat, lon, trk.alt),
                velocity        = Velocity(speed, math.degrees(math.atan2(trk.x[2], trk.x[3])) % 360),
                confidence      = round(conf, 4),
                threat_level    = level,
                sensor_sources  = sorted(trk.sources),
                status          = trk.status.name,
                identity        = ta.identity.name,
                altitude_m      = round(trk.alt, 1),
                pos_sigma_m     = round(sigma, 1),
                inside_zone     = ta.inside_zone,
                time_to_entry_s = None if ta.time_to_entry is None else round(ta.time_to_entry, 1),
                cpa_asset_m     = round(ta.cpa_asset_m, 0),
                threat_reason   = reason,
                object_class    = trk.obj_class,
                engagement_id   = eng.eng_id if eng else None,
                engagement_state= eng.state.name if eng else None,
                domain          = trk.domain,
            ))
        out.sort(key=lambda t: threats[t.track_id].priority)
        return out
