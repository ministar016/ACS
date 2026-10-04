"""
EngagementManager — the kill chain from threat declaration to battle-damage
assessment.

    DETECT ─▶ TRACK ─▶ IDENTIFY ─▶ DECIDE ─▶ ENGAGE ─▶ ASSESS
    (sensors) (tracker) (threat)   (this module)

Engagement states
─────────────────
  PROPOSED ──operator approve / auto-ROE──▶ APPROVED ──effector free──▶ ENGAGING
     │                                          │                          │
     └─ deny ─▶ DENIED                          └─ track lost ─▶ LOST      ├─ kill ─▶ NEUTRALIZED
                                                                           ├─ track lost ─▶ LOST
                                                                           └─ abort ─▶ ABORTED

Human in the loop
─────────────────
By default every engagement waits for operator approval.  With auto-ROE
enabled ("weapons free inside the zone") an engagement is approved
automatically only when the track is already inside the restricted zone or
will enter it within AUTO_ROE_TTE_S — outside that envelope the operator
still decides.

PVO (air defence)
─────────────────
PVO sites are weapons-free against declared-HOSTILE air tracks: every site
that has reloaded (PVO_RELOAD_S = one shot per minute) and has ammunition
fires at the most urgent hostile drone inside its range.  The operator can
put all PVO on HOLD.  A PVO kill also closes any engagement on that track.

Weapon–target assignment
────────────────────────
For each approved engagement without an effector, every free effector is
scored by time-to-effect and the fastest one is assigned:
  • interceptor UAV — launch time (if still on the pad) + PIP time-to-go at
                      dash speed from where it is (must be feasible)
  • UGV jammer      — 0 if the track is already inside jammer range, else the
                      time until its predicted path enters jammer range
                      (drones and enemy UGVs)
  • UGV charge      — same, against charge range (3 km ground / 2 km air);
                      only while the UGV has rounds left
Interceptors only take air tracks.  Drones prefer the jammer and ground
vehicles prefer charges (CHARGE_BIAS_S); while any hostile ground track
exists the UGV charges are reserved for vehicles altogether, so rounds are
spent where only they can stop the threat.  A UGV that runs out of rounds hands the engagement back for
re-assignment.
Interceptors are released back to the base (RTB → land → IDLE); UGVs drive
back to their home position over a drivable route.
"""
from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto

from .guidance import solve_intercept
from .threat import ThreatAssessment, Identity
from .models import ThreatLevel
from .zone import LocalFrame, RestrictedZone
from .devices.uav import UAV, UAVMode, DASH_SPEED_MS
from .devices.ugv import UGV, JAM_RANGE_M

PVO_RELOAD_S  = 60.0
CHARGE_BIAS_S = 5.0

AUTO_ROE_TTE_S   = 30.0
_REROUTE_EVERY_S = 15.0
_REROUTE_MOVE_M  = 300.0


class EngState(Enum):
    PROPOSED    = auto()
    APPROVED    = auto()
    ENGAGING    = auto()
    NEUTRALIZED = auto()
    DENIED      = auto()
    ABORTED     = auto()
    LOST        = auto()


_TERMINAL = {EngState.NEUTRALIZED, EngState.DENIED, EngState.ABORTED, EngState.LOST}


@dataclass
class Engagement:
    eng_id:      str
    track_id:    str
    state:       EngState
    created_t:   float
    effector_id: str | None = None
    effector_kind: str | None = None          # INTERCEPTOR | JAMMER
    recommended: str | None = None            # WTA recommendation while PROPOSED
    approved_by: str | None = None
    approved_t:  float | None = None
    ended_t:     float | None = None
    result:      str = ""
    t_go:        float | None = None
    aim_lat:     float | None = None
    aim_lon:     float | None = None
    passes:      int = 0

    @property
    def active(self) -> bool:
        return self.state not in _TERMINAL


@dataclass
class TrackView:
    """What the engagement manager needs from a track (estimate only)."""
    track_id: str
    x: float
    y: float
    vx: float
    vy: float
    alt: float
    confirmed: bool
    domain: str = "AIR"
    obj_class: str = "UNKNOWN"


# Classified platform types a jammer cannot stop (manned / not remote-controlled)
UNJAMMABLE_CLASSES = {"ATTACK_HELICOPTER"}


@dataclass
class PvoSite:
    site_id:  str
    lat:      float
    lon:      float
    range_m:  float
    ammo:     int
    ready_at: float = 0.0
    kills:    int = 0
    shots:    int = 0
    last_shot: dict | None = None


@dataclass
class _Event:
    t: float
    level: str        # INFO | WARN | ALERT | KILL
    text: str


class EngagementManager:
    def __init__(self, frame: LocalFrame, zone: RestrictedZone,
                 interceptors: list[UAV], jammers: list[UGV], auto_roe: bool = False,
                 ground_bbox: tuple[float, float, float, float] | None = None,
                 drivability=None, pvo_sites: list[PvoSite] | None = None) -> None:
        self.pvo_sites    = list(pvo_sites or [])
        self.pvo_enabled  = True
        self.ground_bbox  = ground_bbox        # lat_min, lat_max, lon_min, lon_max
        self.drivability  = drivability        # DrivabilityGrid | None
        self.frame        = frame
        self.zone         = zone
        self.interceptors = list(interceptors)
        self.jammers      = list(jammers)
        self.auto_roe     = auto_roe
        self.engagements: dict[str, Engagement] = {}
        self.events: deque[_Event] = deque(maxlen=200)
        self.new_events: list[_Event] = []
        self._next_id = 1
        self.kill_count = 0                  # confirmed kills reported by effectors (BDA)
        self._denied: set[str] = set()
        self._neutralized: set[str] = set()
        self._last_route_t: dict[str, float] = {}
        self._reserve_charges = False       # hostile ground threat present → charges for vehicles only
        self._t = 0.0

    def _effector(self, effector_id: str | None):
        for dev in self.interceptors + self.jammers:
            if dev.DEVICE_ID == effector_id:
                return dev
        return None

    # ── operator commands ─────────────────────────────────────────────────

    def approve(self, eng_id: str | None = None, operator: str = "OPERATOR") -> str | None:
        """Approve the given (or most urgent) proposed engagement."""
        eng = self._pick(eng_id, EngState.PROPOSED)
        if eng is None:
            return None
        eng.state = EngState.APPROVED
        eng.approved_by = operator
        eng.approved_t = self._t
        self._log("WARN", f"{eng.eng_id} {eng.track_id} APPROVED by {operator}")
        return eng.eng_id

    def deny(self, eng_id: str | None = None, operator: str = "OPERATOR") -> str | None:
        eng = self._pick(eng_id, EngState.PROPOSED)
        if eng is None:
            return None
        self._end(eng, EngState.DENIED, f"denied by {operator}")
        self._denied.add(eng.track_id)
        return eng.eng_id

    def abort(self, eng_id: str | None = None) -> list[str]:
        """Abort one engagement, or all active ones when eng_id is None."""
        aborted = []
        for eng in list(self.engagements.values()):
            if eng.active and (eng_id is None or eng.eng_id == eng_id):
                self._release(eng)
                self._end(eng, EngState.ABORTED, "aborted by operator")
                aborted.append(eng.eng_id)
        return aborted

    # ── per-tick update ───────────────────────────────────────────────────

    def step(self, t: float, tracks: dict[str, TrackView],
             threats: dict[str, ThreatAssessment]) -> None:
        self._t = t
        self._reserve_charges = any(
            v.domain == "GROUND" and threats[tid].identity == Identity.HOSTILE
            and tid not in self._neutralized for tid, v in tracks.items())

        # 1. Propose engagements for newly hostile tracks
        for tid, ta in threats.items():
            if (ta.level == ThreatLevel.HIGH and ta.identity == Identity.HOSTILE
                    and tracks[tid].confirmed
                    and tid not in self._denied and tid not in self._neutralized
                    and not any(e.active and e.track_id == tid for e in self.engagements.values())):
                eng = Engagement(f"ENG-{self._next_id:03d}", tid, EngState.PROPOSED, t)
                self._next_id += 1
                self.engagements[eng.eng_id] = eng
                self._log("ALERT", f"{tid} HOSTILE — {ta.reason}. {eng.eng_id} proposed")

        # 2. Advance every active engagement
        for eng in sorted(self.engagements.values(),
                          key=lambda e: threats[e.track_id].priority if e.track_id in threats else 1e9):
            if not eng.active:
                continue
            trk = tracks.get(eng.track_id)
            if trk is None:
                self._release(eng)
                self._end(eng, EngState.LOST, "track lost")
                continue
            ta = threats[eng.track_id]

            if eng.state == EngState.PROPOSED:
                kind, eid, tgo = self._best_effector(trk)
                eng.recommended = eid
                eng.t_go = tgo
                if self.auto_roe and (ta.inside_zone or
                                      (ta.time_to_entry is not None and ta.time_to_entry <= AUTO_ROE_TTE_S)):
                    self.approve(eng.eng_id, operator="AUTO-ROE")

            if eng.state == EngState.APPROVED:
                kind, eid, tgo = self._best_effector(trk)
                if eid is not None:
                    self._assign(eng, trk, kind, eid)

            if eng.state == EngState.ENGAGING:
                self._guide(eng, trk)

        # 3. Idle UGVs drive back to their home position
        for ugv in self.jammers:
            if ugv.assigned_track is None and ugv.goal != ugv.home:
                ugv.navigate_to(*ugv.home)

    def report_effect(self, effector_id: str, target_id: str, success: bool, kind: str) -> None:
        """Called by the scenario when an effector's effect lands (BDA)."""
        eng = next((e for e in self.engagements.values()
                    if e.state == EngState.ENGAGING and e.effector_id == effector_id), None)
        label = eng.eng_id if eng else effector_id
        if not success:
            if eng:
                eng.passes += 1
            self._log("WARN", f"{label} MISS by {effector_id} — re-attacking")
            return
        self.kill_count += 1
        if eng is None:
            self._log("KILL", f"{target_id} neutralised by {effector_id} ({kind}) — no engagement on file")
            return
        eng.passes += 1
        self._neutralized.add(eng.track_id)
        self._release(eng)
        self._end(eng, EngState.NEUTRALIZED, f"{kind} by {effector_id}")

    # ── PVO autonomous fire ───────────────────────────────────────────────

    def pvo_fire(self, tracks: dict[str, TrackView],
                 threats: dict[str, ThreatAssessment]) -> list[tuple[PvoSite, str, float, float]]:
        """Shots fired this tick: (site, track_id, aim_lat, aim_lon)."""
        shots = []
        if not self.pvo_enabled:
            return shots
        claimed: set[str] = set()
        for site in self.pvo_sites:
            if site.ammo <= 0 or self._t < site.ready_at:
                continue
            sx, sy = self.frame.to_xy(site.lat, site.lon)
            cands = [
                (threats[tid].priority, tid) for tid, tv in tracks.items()
                if tv.domain != "GROUND" and tv.confirmed and tid in threats
                and threats[tid].identity == Identity.HOSTILE
                and tid not in self._neutralized and tid not in claimed
                and math.hypot(tv.x - sx, tv.y - sy) <= site.range_m
            ]
            if not cands:
                continue
            _, tid = min(cands)
            claimed.add(tid)
            tv = tracks[tid]
            site.ammo -= 1
            site.shots += 1
            site.ready_at = self._t + PVO_RELOAD_S
            lat, lon = self.frame.to_latlon(tv.x, tv.y)
            shots.append((site, tid, lat, lon))
        return shots

    def report_pvo(self, site: PvoSite, track_id: str, target_id: str | None, hit: bool,
                   lat: float, lon: float) -> None:
        site.last_shot = {"t": self._t, "lat": lat, "lon": lon, "hit": hit, "track": track_id}
        if not hit:
            self._log("WARN", f"{site.site_id} fired at {track_id} — miss ({site.ammo} left)")
            return
        site.kills += 1
        self.kill_count += 1
        self._neutralized.add(track_id)
        self._log("KILL", f"{site.site_id} fired at {track_id} — destroyed {target_id} ({site.ammo} left)")
        for eng in self.engagements.values():
            if eng.active and eng.track_id == track_id:
                self._release(eng)
                self._end(eng, EngState.NEUTRALIZED, f"PVO {site.site_id}")

    # ── views ─────────────────────────────────────────────────────────────

    def drain_events(self) -> list[_Event]:
        """Events logged since the last drain (for the GUI / external bridges)."""
        out, self.new_events = self.new_events, []
        return out

    def active(self) -> list[Engagement]:
        return [e for e in self.engagements.values() if e.active]

    def is_neutralized(self, track_id: str) -> bool:
        return track_id in self._neutralized

    # ── internals ─────────────────────────────────────────────────────────

    def _pick(self, eng_id: str | None, state: EngState) -> Engagement | None:
        if eng_id:
            eng = self.engagements.get(eng_id)
            return eng if eng and eng.state == state else None
        cands = [e for e in self.engagements.values() if e.state == state]
        return min(cands, key=lambda e: e.t_go if e.t_go is not None else 1e9, default=None)

    def _best_effector(self, trk: TrackView) -> tuple[str | None, str | None, float | None]:
        options: list[tuple[float, str, str]] = []
        ground = trk.domain == "GROUND"
        if not ground:
            for uav in self.interceptors:
                if not uav.available:
                    continue
                ux, uy = uav.xy
                t_launch = uav.time_to_launch()
                # Where the target will be when the interceptor leaves the pad
                px, py = trk.x + trk.vx * t_launch, trk.y + trk.vy * t_launch
                sol = solve_intercept(px, py, trk.vx, trk.vy, ux, uy, DASH_SPEED_MS)
                if sol.feasible:
                    options.append((t_launch + sol.t_go, "INTERCEPTOR", uav.DEVICE_ID))
        for ugv in self.jammers:
            if not ugv.available:
                continue
            t_jam = (None if trk.obj_class in UNJAMMABLE_CLASSES
                     else self._time_into_range(trk, ugv, JAM_RANGE_M))
            if t_jam is not None:
                options.append((t_jam + (CHARGE_BIAS_S if ground else 0.0), "JAMMER", ugv.DEVICE_ID))
            if ugv.charges > 0 and (ground or not self._reserve_charges):
                t_chg = self._time_into_range(trk, ugv, ugv.charge_range(trk.domain))
                if t_chg is not None:
                    options.append((t_chg + (0.0 if ground else CHARGE_BIAS_S), "CHARGE", ugv.DEVICE_ID))
        if not options:
            return None, None, None
        tgo, kind, eid = min(options)
        return kind, eid, tgo

    def _time_into_range(self, trk: TrackView, ugv: UGV, range_m: float,
                         horizon_s: float = 180.0) -> float | None:
        gx, gy = self.frame.to_xy(ugv.position.lat, ugv.position.lon)
        rx, ry = trk.x - gx, trk.y - gy
        r = range_m * 0.9
        if math.hypot(rx, ry) <= r:
            return 0.0
        a = trk.vx ** 2 + trk.vy ** 2
        b = 2 * (rx * trk.vx + ry * trk.vy)
        c = rx * rx + ry * ry - r * r
        disc = b * b - 4 * a * c
        if a < 1e-9 or disc < 0:
            return None
        t = (-b - math.sqrt(disc)) / (2 * a)
        return t if 0 <= t <= horizon_s else None

    def _time_into_jam_range(self, trk: TrackView, ugv: UGV, horizon_s: float = 180.0) -> float | None:
        return self._time_into_range(trk, ugv, JAM_RANGE_M, horizon_s)

    def _assign(self, eng: Engagement, trk: TrackView, kind: str, eid: str) -> None:
        eng.state = EngState.ENGAGING
        eng.effector_id = eid
        eng.effector_kind = kind
        dev = self._effector(eid)
        if kind == "INTERCEPTOR":
            launching = dev.mode == UAVMode.IDLE
            dev.start_intercept(trk.track_id)
            dev.update_track_estimate(trk.x, trk.y, trk.vx, trk.vy, trk.alt)
            if launching:
                self._log("INFO", f"{eid} launching from base")
        else:
            dev.assign(trk.track_id, weapon="CHARGE" if kind == "CHARGE" else "JAM", domain=trk.domain)
        self._log("ALERT", f"{eng.eng_id} ENGAGING {trk.track_id} with {eid} ({kind})")

    def _guide(self, eng: Engagement, trk: TrackView) -> None:
        dev = self._effector(eng.effector_id)
        if eng.effector_kind == "INTERCEPTOR":
            dev.update_track_estimate(trk.x, trk.y, trk.vx, trk.vy, trk.alt)
            sol = dev.solution
            if sol is not None:
                eng.t_go = sol.t_go
                eng.aim_lat, eng.aim_lon = self.frame.to_latlon(sol.aim_x, sol.aim_y)
        else:
            if eng.effector_kind == "JAMMER" and trk.obj_class in UNJAMMABLE_CLASSES:
                # Classified as a manned platform after assignment: a jammer cannot stop it
                dev.release()
                self._log("WARN", f"{eng.eng_id} {trk.track_id} is {trk.obj_class} — jammer useless, re-assigning")
                eng.state, eng.effector_id, eng.effector_kind = EngState.APPROVED, None, None
                return
            if eng.effector_kind == "CHARGE" and dev.charges <= 0:
                # Out of rounds: hand the engagement back for re-assignment
                dev.release()
                self._log("WARN", f"{eng.eng_id} {dev.DEVICE_ID} out of charges — re-assigning")
                eng.state, eng.effector_id, eng.effector_kind = EngState.APPROVED, None, None
                return
            lat, lon = self.frame.to_latlon(trk.x, trk.y)
            dev.jam_aim = (lat, lon)
            reach = JAM_RANGE_M if eng.effector_kind == "JAMMER" else dev.charge_range(trk.domain)
            eng.t_go = self._time_into_range(trk, dev, reach)
            last = self._last_route_t.get(dev.DEVICE_ID, -1e9)
            in_reach = math.hypot(*[a - b for a, b in zip(self.frame.to_xy(lat, lon),
                                                          self.frame.to_xy(dev.position.lat, dev.position.lon))]) <= reach
            # Reposition toward the track's closest approach if it is out of reach
            if not in_reach and self._t - last >= _REROUTE_EVERY_S:
                gx, gy = self.frame.to_xy(dev.position.lat, dev.position.lon)
                v2 = trk.vx ** 2 + trk.vy ** 2
                s = 0.0 if v2 < 1e-6 else max(0.0, ((gx - trk.x) * trk.vx + (gy - trk.y) * trk.vy) / v2)
                cx, cy = trk.x + trk.vx * s, trk.y + trk.vy * s
                goal = self._ground_goal(*self.frame.to_latlon(cx, cy))
                old = dev.goal
                if goal is not None and (old is None or math.hypot(
                        *[a - b for a, b in zip(self.frame.to_xy(*goal), self.frame.to_xy(*old))]) > _REROUTE_MOVE_M):
                    dev.navigate_to(*goal)
                    self._last_route_t[dev.DEVICE_ID] = self._t
            eng.aim_lat, eng.aim_lon = lat, lon

    def _ground_goal(self, lat: float, lon: float) -> tuple[float, float] | None:
        """A drivable goal inside the routable ground area, near (lat, lon)."""
        lat, lon = self._clamp_ground(lat, lon)
        if self.drivability is not None:
            snapped = self.drivability.nearest_drivable(lat, lon, max_m=800.0)
            if snapped is not None:
                return snapped
        return lat, lon

    def _clamp_ground(self, lat: float, lon: float) -> tuple[float, float]:
        """Keep UGV goals inside the routable ground area (segmented terrain)."""
        if self.ground_bbox is None:
            return lat, lon
        la0, la1, lo0, lo1 = self.ground_bbox
        m = 0.002                                  # ~200 m inside the edge
        return min(max(lat, la0 + m), la1 - m), min(max(lon, lo0 + m), lo1 - m)

    def _release(self, eng: Engagement) -> None:
        if eng.state != EngState.ENGAGING:
            return
        dev = self._effector(eng.effector_id)
        if dev is None:
            return
        if eng.effector_kind == "INTERCEPTOR":
            dev.return_to_base()
            self._log("INFO", f"{dev.DEVICE_ID} returning to base")
        elif eng.effector_kind in ("JAMMER", "CHARGE"):
            dev.release()

    def _end(self, eng: Engagement, state: EngState, result: str) -> None:
        eng.state = state
        eng.ended_t = self._t
        eng.result = result
        level = "KILL" if state == EngState.NEUTRALIZED else "WARN"
        self._log(level, f"{eng.eng_id} {eng.track_id} {state.name}: {result}")

    def _log(self, level: str, text: str) -> None:
        ev = _Event(round(self._t, 1), level, text)
        self.events.append(ev)
        self.new_events.append(ev)
