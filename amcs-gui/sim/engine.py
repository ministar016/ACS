"""
SimEngine — the simulation backend: scenario, operator commands, scenario
editor, drivability layer and the artemides-trax link.  No Qt in here: the
engine runs in its own process (sim/worker.py) and the GUI talks to it
through sim/bus.py.

Output goes through one callback, emit(name, payload), where name is one of
the GUI signals (timeUpdated, tracksUpdated, …) and payload is plain
JSON-serialisable data.  publish() emits the whole picture of one moment;
commands emit only what they change.

    engine = SimEngine(emit=lambda name, payload: ...)
    engine.start()
    while engine.running:
        snap = engine.step()
        engine.publish(snap)
"""
from __future__ import annotations
import os
import re
import time
from dataclasses import replace
from pathlib import Path

from .scenario import Scenario
from .engagement import EngState
from .laydown import Laydown, DEFAULT_LAYDOWN, ConvoySpec
from .drivability import CLASSES, classify, UNKNOWN_SPEED_KMH
from . import paths, systems

from integrations.artemides import (ArtemidesBridge, ArtemidesClient, ArtemidesConfig,
                                    ArtemidesRouter, CACHE_DIR, load_drivability,
                                    drivability_cache_path)

SCENARIO_DIR = paths.scenario_dir()
_BUILTIN = "PREŠEVO VALLEY (built-in)"
_LAST_SAVED = ".last_saved"          # pointer file: the startup scenario


def _r(x, nd=1):
    return None if x is None else round(x, nd)


_TRANSLIT = str.maketrans("ŠšĐđČčĆćŽž", "SsDdCcCcZz")


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip().translate(_TRANSLIT)).strip("-").lower()
    return s or "scenario"


def scenario_files() -> dict[str, Path]:
    """Saved scenarios by display name (the name stored inside each file)."""
    out: dict[str, Path] = {}
    if SCENARIO_DIR.exists():
        for p in sorted(SCENARIO_DIR.glob("*.json")):
            try:
                out[Laydown.from_json(p.read_text(encoding="utf-8")).name] = p
            except (ValueError, KeyError):
                continue
    return out


def startup_laydown() -> tuple[Laydown, str]:
    """The last saved scenario (pointer file, else newest file), else the built-in one."""
    candidates: list[Path] = []
    pointer = SCENARIO_DIR / _LAST_SAVED
    if pointer.exists():
        candidates.append(SCENARIO_DIR / pointer.read_text(encoding="utf-8").strip())
    if SCENARIO_DIR.exists():
        candidates += sorted(SCENARIO_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            return Laydown.from_json(path.read_text(encoding="utf-8")), f"last saved ({path.name})"
        except (OSError, ValueError, KeyError):
            continue
    return DEFAULT_LAYDOWN, "built-in"


class SimEngine:
    # Commands the GUI may send (sim/bus.py forwards QML slot calls by name)
    COMMANDS = frozenset({
        "start", "stop", "reset", "acceptMission", "approveEngagement", "denyEngagement",
        "abortEngagement", "abortAll", "setPvoEnabled", "setAutoRoe", "launchInterceptor",
        "recallInterceptor", "setEditMode", "editPlace", "cancelMove", "setZoneRadius",
        "setInterceptors", "setConvoy", "saveScenario", "loadScenario", "refreshScenarios",
        "loadDrivability", "setPlaceSystem",
    })

    def __init__(self, dt: float = 0.1, emit=None,
                 artemides: ArtemidesConfig | None = None,
                 laydown: Laydown | None = None) -> None:
        self._dt = dt
        self.emit = emit or (lambda name, payload: None)
        if laydown is None:
            laydown, self._laydown_source = startup_laydown()
        else:
            self._laydown_source = "given"
        self._laydown = laydown
        self._artemides_cfg = artemides or ArtemidesConfig.from_env()
        # The laydown's own artemides deployment is the default link;
        # ARTEMIDES_URL="" (set but empty) forces offline mode.
        if not self._artemides_cfg.base_url and "ARTEMIDES_URL" not in os.environ:
            self._artemides_cfg.base_url = laydown.artemides_url
        self._client = ArtemidesClient(self._artemides_cfg)
        self._bridge = ArtemidesBridge(self._client)
        self._auto_roe = False
        self._pvo_enabled = True
        self._edit_mode = False
        self._move_pick: tuple[str, str] | None = None     # (kind, site_id) picked by MOVE
        self._place_system = dict(systems.DEFAULT_SYSTEM)  # editor: system for new PVO / radar / GG
        self._drivability = None
        self._driv_future = None
        self._driv_status = "not loaded"
        self._driv_png: str | None = None
        self._driv_progress = (0, 0)
        self._scenario = self._new_scenario()
        self.running = False
        if self._artemides_cfg.enabled:
            self._client.submit(self._client.whoami)

    def _new_scenario(self) -> Scenario:
        router = ArtemidesRouter(self._client) if self._artemides_cfg.enabled else None
        sc = Scenario(dt=self._dt, auto_roe=self._auto_roe, route_provider=router,
                      laydown=self._laydown, drivability=self._drivability)
        sc.engage.pvo_enabled = self._pvo_enabled
        return sc

    def command(self, name: str, *args) -> None:
        if name not in self.COMMANDS:
            raise ValueError(f"unknown command {name}")
        getattr(self, name)(*args)

    # ── Simulation control ────────────────────────────────────────────────

    def start(self) -> None:
        self._scenario.engage._log("INFO", f"Scenario '{self._laydown.name}' — {self._laydown_source}")
        self.emit("catalogUpdated", systems.catalog_view())
        self._emit_static()
        self.emit("autoRoeChanged", self._auto_roe)
        self.refreshScenarios()
        # A cached drivability layer loads instantly; otherwise wait for the operator
        if drivability_cache_path(self._artemides_cfg.base_url or "",
                                  tuple(self._laydown.ground_bbox), 0.0007).exists():
            self.loadDrivability(False)
        else:
            self._emit_drivability()
        self.running = True

    def stop(self) -> None:
        self.running = False

    def shutdown(self) -> None:
        """Stop the sim and retract anything published to artemides-trax."""
        self.running = False
        self._bridge.shutdown()

    def reset(self) -> None:
        self._scenario = self._new_scenario()
        self._emit_static()
        self.running = not self._edit_mode

    def step(self):
        snap = self._scenario.step()
        self._bridge.on_snapshot(snap)
        return snap

    @property
    def sim_time(self) -> float:
        return self._scenario._t

    # ── Operator: engagements ─────────────────────────────────────────────

    def acceptMission(self) -> None:
        """Operator approves the most urgent proposed engagement."""
        self._scenario.engage.approve(operator="OPERATOR")
        self._emit_c2()

    def approveEngagement(self, eng_id: str) -> None:
        self._scenario.engage.approve(eng_id or None, operator="OPERATOR")
        self._emit_c2()

    def denyEngagement(self, eng_id: str) -> None:
        self._scenario.engage.deny(eng_id or None, operator="OPERATOR")
        self._emit_c2()

    def abortEngagement(self, eng_id: str) -> None:
        self._scenario.engage.abort(eng_id or None)
        self._emit_c2()

    def abortAll(self) -> None:
        self._scenario.engage.abort(None)
        self._emit_c2()

    def setPvoEnabled(self, enabled: bool) -> None:
        """PVO weapons free (AUTO) or HOLD fire."""
        self._pvo_enabled = enabled
        self._scenario.engage.pvo_enabled = enabled
        self._scenario.engage._log("WARN", f"PVO {'AUTO — weapons free on hostile drones' if enabled else 'HOLD FIRE'}")
        self._emit_c2()

    def setAutoRoe(self, enabled: bool) -> None:
        """Weapons-free inside the restricted zone (see EngagementManager)."""
        self._auto_roe = enabled
        self._scenario.engage.auto_roe = enabled
        self.emit("autoRoeChanged", enabled)

    # ── Operator: interceptors on call ────────────────────────────────────

    def launchInterceptor(self, device_id: str) -> None:
        for u in self._scenario.uavs:
            if u.DEVICE_ID == device_id and u.assigned_track is None:
                u.launch_patrol()
                self._scenario.engage._log("INFO", f"{device_id} launched on call (patrol over base)")
        self.publish(None)

    def recallInterceptor(self, device_id: str) -> None:
        for u in self._scenario.uavs:
            if u.DEVICE_ID == device_id and u.assigned_track is None and u.airborne:
                u.return_to_base()
                self._scenario.engage._log("INFO", f"{device_id} recalled to base")
        self.publish(None)

    # ── Scenario editor ───────────────────────────────────────────────────

    def setEditMode(self, on: bool) -> None:
        """Edit mode pauses the sim at T+0 so the laydown can be changed."""
        self._edit_mode = on
        self._scenario = self._new_scenario()
        self.emit("editModeChanged", on)
        self._emit_static()
        self.running = not on

    def setPlaceSystem(self, kind: str, code: str) -> None:
        """Editor: the catalog system new PVO / radar / GG sites get."""
        spec = systems.get(code)
        if spec is None or spec.role not in systems.SITE_ROLES.get(kind, ()):
            return self._result(False, f"{code} is not a {kind} system")
        self._place_system[kind] = code
        self._result(True, f"New {kind.upper()} sites: {spec.name}")

    def editPlace(self, tool: str, lat: float, lon: float) -> None:
        """
        Map click in edit mode.  Tools: base, ugv, acoustic, radar, seismic,
        pvo, gg (place), delete (nearest item), move (click item, then click
        its new position).
        """
        ld = self._laydown
        if tool != "move":
            self._move_pick = None
        if tool == "move":
            return self._edit_move(lat, lon)
        if tool == "base":
            self._laydown = ld.with_base(lat, lon)
            msg = f"Base moved to {lat:.5f}, {lon:.5f}"
        elif tool == "delete":
            self._laydown, removed = ld.remove_nearest(lat, lon)
            if removed is None:
                return self._result(False, "Nothing to delete within 600 m")
            msg = f"Removed {removed.label or removed.site_id}"
        elif tool == "ugv":
            ok, why = self._check_ugv_site(lat, lon)
            if not ok:
                return self._result(False, why)
            self._laydown, site = ld.add_site("ugv", lat, lon)
            msg = f"{site.site_id} placed — {why}"
        elif tool in ("acoustic", "radar", "seismic", "pvo", "gg"):
            self._laydown, site = ld.add_site(tool, lat, lon, self._place_system.get(tool))
            spec = systems.get(getattr(site, "system", ""))
            msg = f"{site.label or site.site_id} placed" + (f" — {spec.name}" if spec else "")
        else:
            return self._result(False, f"unknown tool {tool}")
        self._apply_edit()
        self._result(True, msg)

    def _edit_move(self, lat: float, lon: float) -> None:
        ld = self._laydown
        if self._move_pick is None:
            kind, site = ld.nearest(lat, lon)
            if site is None:
                return self._result(False, "MOVE: click on an item (within 600 m) to pick it")
            self._move_pick = (kind, site.site_id)
            name = getattr(site, "label", "") or site.site_id
            return self._result(True, f"Picked {name} — click its new position",
                                picked={"lat": site.lat, "lon": site.lon, "label": name})
        kind, sid = self._move_pick
        if kind == "ugv":
            ok, why = self._check_ugv_site(lat, lon)
            if not ok:
                return self._result(False, why + " — pick another spot")
        self._move_pick = None
        self._laydown = ld.move_site(kind, sid, lat, lon)
        self._apply_edit()
        self._result(True, f"Moved {sid} to {lat:.5f}, {lon:.5f}")

    def cancelMove(self) -> None:
        if self._move_pick is not None:
            self._move_pick = None
            self._result(True, "Move cancelled")

    def setZoneRadius(self, radius_m: float) -> None:
        self._laydown = self._laydown.with_zone_radius(radius_m)
        self._apply_edit()
        self._result(True, f"Zone radius {self._laydown.zone_radius_m / 1000:.1f} km")

    def setInterceptors(self, n: int) -> None:
        self._laydown = replace(self._laydown, interceptors=max(0, min(6, n)))
        self._apply_edit()
        self._result(True, f"{self._laydown.interceptors} interceptors at base")

    def setConvoy(self, vehicles: int, escorts: int, aviation: int) -> None:
        """Enemy attack: 0–5 trucks/UGVs, 0–20 escort UAVs, 0–6 attack helicopters (all 0 = none)."""
        vehicles, escorts, aviation = max(0, min(5, vehicles)), max(0, min(20, escorts)), max(0, min(6, aviation))
        convoy = None if vehicles + escorts + aviation == 0 else \
            replace(self._laydown.convoy or ConvoySpec(), vehicles=vehicles,
                    escort_drones=escorts, aviation=aviation)
        self._laydown = replace(self._laydown, convoy=convoy)
        self._apply_edit()
        self._result(True, f"Enemy attack: {vehicles} trucks/UGVs, {escorts} escort UAVs, {aviation} helicopters")

    def saveScenario(self, name: str) -> None:
        name = name.strip() or self._laydown.name
        self._laydown = replace(self._laydown, name=name)
        SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
        # Overwrite the file that already holds this name, else a new one
        path = scenario_files().get(name) or SCENARIO_DIR / f"{_slug(name)}.json"
        path.write_text(self._laydown.to_json(), encoding="utf-8")
        (SCENARIO_DIR / _LAST_SAVED).write_text(path.name, encoding="utf-8")
        self.refreshScenarios()
        self._emit_static()
        self._result(True, f"Saved {path.name} — it is now the startup scenario")

    def loadScenario(self, name: str) -> None:
        if name == _BUILTIN:
            self._laydown = DEFAULT_LAYDOWN
        else:
            path = scenario_files().get(name)
            if path is None:
                return self._result(False, f"No saved scenario named '{name}'")
            try:
                self._laydown = Laydown.from_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, KeyError) as e:
                return self._result(False, f"Cannot load {path.name}: {e}")
        self._apply_edit()
        self._result(True, f"Loaded {self._laydown.name}")

    def refreshScenarios(self) -> None:
        # Current scenario first so the LOAD box starts on it
        names = list(scenario_files()) + [_BUILTIN]
        cur = self._laydown.name
        names.sort(key=lambda n: n != cur)
        self.emit("scenariosUpdated", names)

    def _check_ugv_site(self, lat: float, lon: float) -> tuple[bool, str]:
        if not self._laydown.in_ground_bbox(lat, lon):
            return False, "Outside artemides terrain area — UGV could not be routed there"
        if self._drivability is None:
            return True, "drivability unknown (load the DRIVE layer to check)"
        cost = self._drivability.cost_at(lat, lon)
        label, kmh = classify(cost)
        if label == "UNKNOWN":
            return True, "no terrain data at this spot"
        if label == "NO-GO":
            near = self._drivability.nearest_drivable(lat, lon, 500)
            hint = f" — nearest drivable {near[0]:.5f}, {near[1]:.5f}" if near else ""
            return False, f"NO-GO terrain (cost {cost:.2f}){hint}"
        return True, f"{label} terrain, {kmh:.0f} km/h"

    def _apply_edit(self) -> None:
        self._scenario = self._new_scenario()
        self._emit_static()
        self.running = not self._edit_mode

    def _result(self, ok: bool, message: str, picked: dict | None = None) -> None:
        self.emit("editResult", {"ok": ok, "message": message, "picked": picked})

    # ── Drivability layer ─────────────────────────────────────────────────

    def loadDrivability(self, refresh: bool) -> None:
        if self._driv_future is not None and not self._driv_future.done():
            return
        self._driv_status = "loading…"
        self._emit_drivability()
        self._driv_progress = (0, 0)

        def progress(i, n):
            self._driv_progress = (i, n)
        self._driv_future = self._client.submit(
            load_drivability, self._client, self._laydown.ground_bbox, 0.0007, refresh, progress)

    def poll_jobs(self) -> None:
        """Background jobs (drivability download); call a few times per second."""
        fut = self._driv_future
        if fut is None:
            return
        if not fut.done():
            i, n = self._driv_progress
            if n:
                self._driv_status = f"loading… tile {i}/{n}"
                self._emit_drivability()
            return
        self._driv_future = None
        try:
            grid, source = fut.result()
        except Exception as e:
            hint = " — set ARTEMIDES_TOKEN (vojsrb → account.php → Novi token)" if "401" in str(e) else ""
            self._driv_status = f"unavailable: {e}{hint}"
            self._emit_drivability()
            return
        self._drivability = grid
        self._scenario.set_drivability(grid)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        png = CACHE_DIR / f"drivability_{int(time.time())}.png"   # unique → QML reloads
        png.write_bytes(grid.to_png())
        self._driv_png = png.resolve().as_uri()
        known = sum(1 for c in grid.costs if c is not None)
        self._driv_status = f"ready ({source}, {known} cells with data)"
        self._emit_drivability()

    def _emit_drivability(self) -> None:
        g = self._drivability
        la0, la1, lo0, lo1 = g.bbox if g else self._laydown.ground_bbox
        self.emit("drivabilityUpdated", {
            "status": self._driv_status,
            "ready":  g is not None,
            "url":    self._driv_png or "",
            "bbox":   {"latMin": la0, "latMax": la1, "lonMin": lo0, "lonMax": lo1},
            "stats":  g.stats() if g else {},
            "legend": [{"label": label, "kmh": kmh,
                        "color": "#%02x%02x%02x" % rgba[:3]} for _, label, kmh, rgba in CLASSES],
            "unknownKmh": UNKNOWN_SPEED_KMH,
        })

    # ── Output ────────────────────────────────────────────────────────────

    def _emit_static(self) -> None:
        self.emit("laydownUpdated", self._laydown.to_dict())
        self.emit("zoneUpdated", self._scenario.zone.to_dict())
        terr = self._scenario.territory
        self.emit("borderUpdated", terr.to_view() if terr else {"lines": [], "source": ""})
        self.publish(self.step() if self._scenario._t == 0 else None)

    def publish(self, snap) -> None:
        """Emit the full picture: platforms, sensors, tracks, C2 state."""
        sc = self._scenario
        emit = self.emit
        if snap is not None:
            emit("timeUpdated", snap.timestamp)

        emit("uavsUpdated", [{
            "deviceId":   u.DEVICE_ID,
            "lat":        round(u.position.lat, 6),
            "lon":        round(u.position.lon, 6),
            "altitudeM":  round(u.position.alt, 1),
            "speedMs":    round(u._speed, 1),
            "headingDeg": round(u.heading_deg, 1),
            "batteryPct": round(u._battery, 1),
            "status":     u.status.name,
            "mode":       u.mode.name,
            "airborne":   u.airborne,
            "expended":   u.expended,
            "assignedTrack": u.assigned_track or "",
            "station":    {"lat": u.station[0], "lon": u.station[1]} if u.station else None,
        } for u in sc.uavs])

        emit("ugvsUpdated", [{
            "deviceId":   g.DEVICE_ID,
            "lat":        round(g.position.lat, 6),
            "lon":        round(g.position.lon, 6),
            "homeLat":    g.home[0],
            "homeLon":    g.home[1],
            "speedKmh":   round(g._speed * 3.6, 0),
            "headingDeg": round(g.heading_deg, 1),
            "batteryPct": round(g._battery, 1),
            "status":     g.status.name,
            "terrain":    g.terrain_class,
            "jamming":    g.jamming,
            "assignedTrack": g.assigned_track or "",
            "jamAim":     {"lat": g.jam_aim[0], "lon": g.jam_aim[1]} if g.jam_aim else None,
            "weapon":     g.weapon,
            "charges":    g.charges,
            "maxCharges": g.max_charges,
            "lastShot":   g.last_shot,
            "route":      [{"lat": la, "lon": lo} for la, lo in g.route],
            "routeSource": g.route_source,
            "destroyed":  g.destroyed,
            "station":    {"lat": g.station[0], "lon": g.station[1]} if g.station else None,
        } for g in sc.ugvs])

        if snap is not None:
            emit("acousticUpdated", [{
                "sensorId":    r.sensor_id,
                "lat":         s._lat,
                "lon":         s._lon,
                "amplitudeDb": r.amplitude_db,
                "bearing":     r.estimated_bearing,
                "confidence":  r.detection_confidence,
                "detected":    r.target_detected,
            } for r, s in zip(snap.acoustic_readings, sc.acoustic_sensors)])
            emit("seismicUpdated", [{
                "sensorId":   r.sensor_id,
                "confidence": r.detection_confidence,
                "detected":   r.target_detected,
            } for r in snap.seismic_readings])

            emit("tracksUpdated", [{
                "trackId":     t.track_id,
                "lat":         round(t.position.lat, 6),
                "lon":         round(t.position.lon, 6),
                "altitudeM":   t.altitude_m,
                "speedMs":     round(t.velocity.speed_ms, 2),
                "headingDeg":  round(t.velocity.heading_deg, 1),
                "confidence":  t.confidence,
                "threatLevel": t.threat_level.name,
                "sources":     t.sensor_sources,
                "status":      t.status,
                "identity":    t.identity,
                "sigmaM":      t.pos_sigma_m,
                "insideZone":  t.inside_zone,
                "tteS":        t.time_to_entry_s,
                "cpaM":        t.cpa_asset_m,
                "reason":      t.threat_reason,
                "objClass":    t.object_class,
                "engId":       t.engagement_id or "",
                "engState":    t.engagement_state or "",
                "domain":      t.domain,
            } for t in snap.tracks])
            emit("threatUpdated", snap.threat_level.value)
            emit("targetsUpdated", [
                {"id": t.target_id, "lat": round(t.position.lat, 6), "lon": round(t.position.lon, 6),
                 "altM": round(t.position.alt, 1), "state": t.state.name, "hostile": t.hostile,
                 "domain": getattr(t, "domain", "AIR"), "cls": t.drone_class}
                for t in snap.targets if t.state.name != "PENDING"
            ])
            emit("statsUpdated", {"kills": sc.engage.kill_count, "baseHits": snap.base_hits,
                                  "assaults": snap.assaults, "ownLosses": sc.engage.own_losses,
                                  "uavLost": sum(1 for u in sc.uavs if u.expended),
                                  "ugvLost": sum(1 for g in sc.ugvs if g.destroyed)})
            emit("detectionsUpdated", sc.recent_bearings())
            lead = next((v for v in sc.convoy if v.route), None)
            emit("enemyRouteUpdated", {
                "source": sc.convoy_route_source,
                "route": [{"lat": la, "lon": lo} for la, lo in (lead.route if lead else [])],
            })

        self._emit_c2()

    def _emit_c2(self) -> None:
        sc = self._scenario
        eng = sc.engage
        t_now = sc._t

        def site_view(p):
            return {
                "id": p.site_id, "lat": p.lat, "lon": p.lon, "rangeM": p.range_m,
                "system": p.spec.code if p.spec else "", "name": p.name,
                "ammo": p.ammo, "reserve": p.reserve, "gunBursts": p.gun_bursts,
                "gunRangeM": p.spec.gun_range_m if p.spec else 0,
                "minRangeM": p.spec.min_range_m if p.spec else 0,
                "reloading": p.reload_until is not None,
                "destroyed": p.destroyed,
                "kills": p.kills, "shots": p.shots, "inFlight": p.in_flight,
                "readyIn": max(0.0, round(p.ready_at - t_now, 0)),
                "lastShot": p.last_shot,
            }
        self.emit("pvoUpdated", {
            "enabled": eng.pvo_enabled,
            "ggEnabled": eng.auto_roe,
            "sites": [site_view(p) for p in eng.pvo_sites],
            "gg": [site_view(p) for p in eng.gg_sites],
            "munitions": sc.munitions_view(),
        })
        self.emit("readinessUpdated", dict(eng.readiness_view(), war=sc.war,
                                           warT=sc.war_t, border=sc.territory is not None))
        self.emit("engagementsUpdated", [
            {
                "engId":      e.eng_id,
                "trackId":    e.track_id,
                "state":      e.state.name,
                "active":     e.active,
                "effector":   e.effector_id or e.recommended or "",
                "kind":       e.effector_kind or "",
                "approvedBy": e.approved_by or "",
                "tGo":        _r(e.t_go),
                "aimLat":     e.aim_lat,
                "aimLon":     e.aim_lon,
                "result":     e.result,
                "createdT":   round(e.created_t, 1),
                "endedT":     _r(e.ended_t),
            }
            for e in sorted(eng.engagements.values(),
                            key=lambda e: (not e.active, e.state != EngState.PROPOSED, -e.created_t))
        ])
        self.emit("eventsUpdated", [
            {"t": ev.t, "level": ev.level, "text": ev.text}
            for ev in list(eng.events)[-40:][::-1]
        ])
        st = self._client.status()
        st.update(iffRejects=sc.tracker.iff_rejects)
        self.emit("linkUpdated", st)
