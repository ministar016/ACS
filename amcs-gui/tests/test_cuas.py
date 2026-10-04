"""
Counter-UAS chain tests — run from amcs-gui/:

    .venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations
import json
import math
import os
import random
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.zone import LocalFrame, RestrictedZone, ProtectedAsset
from sim.guidance import solve_intercept
from sim.tracker import MultiTargetTracker, PositionMeas, TrackStatus
from sim.scenario import Scenario
from sim.target import TargetState
from sim.engagement import EngState
from sim.laydown import DEFAULT_LAYDOWN, Laydown
from dataclasses import replace as dc_replace

# The original three-drone picture (no convoy, no PVO) isolates the kill chain
BASIC = dc_replace(DEFAULT_LAYDOWN, convoy=None, pvo=())
from sim.drivability import DrivabilityGrid, classify
from sim.devices.uav import UAVMode
import integrations.artemides as artemides
from integrations.artemides import (ArtemidesBridge, ArtemidesClient, ArtemidesConfig,
                                    ArtemidesRouter, load_drivability)


def _square_zone() -> RestrictedZone:
    f = LocalFrame(42.0, 20.0)
    verts = [f.to_latlon(x, y) for x, y in ((-1000, -1000), (1000, -1000), (1000, 1000), (-1000, 1000))]
    return RestrictedZone("Z", verts, f, ProtectedAsset("A", 42.0, 20.0), buffer_m=500)


def _run(sc: Scenario, seconds: float, on_step=None):
    for _ in range(int(seconds / sc._dt)):
        snap = sc.step()
        if on_step:
            on_step(sc, snap)
    return snap


class ZoneTests(unittest.TestCase):
    def test_contains_and_distance(self):
        z = _square_zone()
        self.assertTrue(z.contains(0, 0))
        self.assertFalse(z.contains(1500, 0))
        self.assertAlmostEqual(z.distance_to_boundary(1500, 0), 500, delta=1)
        self.assertLess(z.distance_to_boundary(0, 0), 0)
        self.assertTrue(z.in_buffer(1400, 0))

    def test_time_to_entry(self):
        z = _square_zone()
        self.assertAlmostEqual(z.time_to_entry(3000, 0, -20, 0), 100.0, delta=0.5)
        self.assertIsNone(z.time_to_entry(3000, 0, 20, 0))       # outbound
        self.assertEqual(z.time_to_entry(0, 0, 5, 5), 0.0)       # inside

    def test_cpa(self):
        z = _square_zone()
        d, t = z.cpa_to_asset(-2000, 300, 10, 0)
        self.assertAlmostEqual(d, 300, delta=1)
        self.assertAlmostEqual(t, 200, delta=1)


class GuidanceTests(unittest.TestCase):
    def test_stationary_target(self):
        sol = solve_intercept(1000, 0, 0, 0, 0, 0, 50)
        self.assertTrue(sol.feasible)
        self.assertAlmostEqual(sol.t_go, 20.0, places=3)

    def test_crossing_target_lands_on_collision_course(self):
        sol = solve_intercept(2000, 0, 0, 30, 0, 0, 55)
        self.assertTrue(sol.feasible)
        # interceptor path length equals speed × time at the PIP
        self.assertAlmostEqual(math.hypot(sol.aim_x, sol.aim_y), 55 * sol.t_go, delta=1e-6)

    def test_faster_opening_target_is_infeasible(self):
        sol = solve_intercept(1000, 0, 80, 0, 0, 0, 55)
        self.assertFalse(sol.feasible)


class TrackerTests(unittest.TestCase):
    def test_converges_on_constant_velocity_target(self):
        rng = random.Random(1)
        trk = MultiTargetTracker()
        vx, vy = 25.0, -10.0
        for k in range(1, 101):
            t = k * 0.5
            x, y = -3000 + vx * t, 2000 + vy * t
            m = PositionMeas("RAD", x + rng.gauss(0, 30), y + rng.gauss(0, 30),
                             [[900, 0], [0, 900]], alt=100)
            trk.update(t, [m], [])
        self.assertEqual(len(trk.tracks), 1)
        tr = trk.tracks[0]
        self.assertEqual(tr.status, TrackStatus.CONFIRMED)
        self.assertLess(math.hypot(tr.x[2] - vx, tr.x[3] - vy), 2.0)

    def test_iff_suppresses_own_platform(self):
        rng = random.Random(2)
        trk = MultiTargetTracker()
        for k in range(1, 200):
            t = k * 0.1
            fx, fy = 100 * math.cos(t / 10), 100 * math.sin(t / 10)
            m = PositionMeas("RAD", fx + rng.gauss(0, 30), fy + rng.gauss(0, 30),
                             [[900, 0], [0, 900]])
            trk.update(t, [m], [], friendlies=[(fx, fy)])
        self.assertEqual(trk.tracks, [])
        self.assertGreater(trk.iff_rejects, 190)

    def test_two_sensors_one_target_gives_one_track(self):
        trk = MultiTargetTracker()
        for k in range(1, 40):
            t = k * 0.1
            x, y = 30 * t, 0.0
            trk.update(t, [PositionMeas("RAD-A", x + 5, y, [[900, 0], [0, 900]]),
                           PositionMeas("RAD-B", x - 5, y, [[900, 0], [0, 900]])], [])
        self.assertEqual(len(trk.tracks), 1)


class SensorRangeTests(unittest.TestCase):
    def _at(self, km_east, domain="AIR"):
        from sim.target import AerialTarget, GroundTarget, TargetState
        from sim.laydown import offset
        lat, lon = offset(42.27, 21.60, 0, km_east * 1000)
        if domain == "AIR":
            return AerialTarget("T", lat, lon, 90, 25, 100)
        g = GroundTarget("G", lat, lon)
        g.state = TargetState.MOVING
        return g

    def _rate(self, sensor, tgt, n=40):
        return sum(sensor.sample(tgt, 0).target_detected for _ in range(n)) / n

    def test_acoustic_air_10km_ground_2_to_3km(self):
        from sim.sensors.acoustic import AcousticSensor
        a = AcousticSensor("A", 42.27, 21.60, seed=1)
        self.assertGreater(self._rate(a, self._at(9.0)), 0.8)
        self.assertEqual(self._rate(a, self._at(10.5)), 0.0)
        self.assertGreater(self._rate(a, self._at(2.0, "GROUND")), 0.8)
        self.assertLess(self._rate(a, self._at(3.5, "GROUND")), 0.1)

    def test_seismic_ground_5_to_10km_never_air(self):
        from sim.sensors.seismic import SeismicSensor
        s = SeismicSensor("S", 42.27, 21.60, seed=1)
        self.assertGreater(self._rate(s, self._at(6.0, "GROUND")), 0.8)
        self.assertEqual(self._rate(s, self._at(11.0, "GROUND")), 0.0)
        self.assertEqual(self._rate(s, self._at(1.0)), 0.0)

    def test_detection_wedges_published(self):
        sc = Scenario(dt=0.1)
        kinds = set()
        for _ in range(9000):
            sc.step()
            dets = sc.recent_bearings()
            for d in dets:
                kinds.add(d["kind"])
                self.assertIn(d["rangeM"], (10_000.0, 3_000.0))
                self.assertGreaterEqual(d["toDeg"] - d["fromDeg"], 15.0 - 1e-6)
            # merged: a sensor never has two overlapping sectors of the same range
            per = {}
            for d in dets:
                per.setdefault((d["sensorId"], d["rangeM"]), []).append((d["fromDeg"], d["toDeg"]))
            for secs in per.values():
                secs.sort()
                self.assertTrue(all(b[0] > a[1] for a, b in zip(secs, secs[1:])))
            if kinds == {"ACOUSTIC", "SEISMIC"}:
                break
        self.assertEqual(kinds, {"ACOUSTIC", "SEISMIC"})


class EndToEndTests(unittest.TestCase):
    def test_auto_roe_neutralises_hostiles_and_spares_neutral(self):
        sc = Scenario(dt=0.1, auto_roe=True, laydown=BASIC)
        max_tracks = [0]

        def watch(sc, snap):
            max_tracks[0] = max(max_tracks[0], len(snap.tracks))
            # No engagement may ever be pointed at our own interceptor
            for e in sc.engage.active():
                trk = sc.tracker.get(e.track_id)
                if trk:
                    for u in sc.uavs:
                        if u.airborne and e.effector_id != u.DEVICE_ID:
                            ux, uy = u.xy
                            self.assertGreater(math.hypot(trk.x[0] - ux, trk.x[1] - uy), 50)

        _run(sc, 330, watch)
        states = {t.target_id: t.state for t in sc.targets}
        self.assertIn(states["HOSTILE-A"], (TargetState.DESTROYED, TargetState.LANDED))
        self.assertIn(states["HOSTILE-B"], (TargetState.DESTROYED, TargetState.LANDED))
        self.assertEqual(states["CIVIL-C"], TargetState.FLYING)
        kills = [e for e in sc.engage.engagements.values() if e.state == EngState.NEUTRALIZED]
        self.assertEqual(len(kills), 2)
        self.assertLessEqual(max_tracks[0], 4, "duplicate / ghost tracks")

    def test_no_engagement_without_approval(self):
        sc = Scenario(dt=0.1, auto_roe=False, laydown=BASIC)
        _run(sc, 200)
        engs = list(sc.engage.engagements.values())
        self.assertTrue(engs, "hostile tracks should produce proposals")
        self.assertTrue(all(e.state == EngState.PROPOSED for e in engs))
        self.assertTrue(all(t.state != TargetState.DESTROYED for t in sc.targets))

    def test_operator_approval_kills_before_zone_entry(self):
        sc = Scenario(dt=0.1, auto_roe=False, laydown=BASIC)
        kill_pos = {}

        def approve_and_watch(sc, snap):
            if sc.engage.approve(operator="TEST"):
                pass
            for t in sc.targets:
                if t.state == TargetState.DESTROYED and t.target_id not in kill_pos:
                    kill_pos[t.target_id] = sc.frame.to_xy(t.position.lat, t.position.lon)

        _run(sc, 330, approve_and_watch)
        self.assertIn("HOSTILE-A", kill_pos)
        self.assertFalse(sc.zone.contains(*kill_pos["HOSTILE-A"]),
                         "with early approval HOSTILE-A must die before entering the zone")

    def test_deny_is_respected(self):
        sc = Scenario(dt=0.1, auto_roe=False, laydown=BASIC)
        for _ in range(3000):
            sc.step()
            if any(e.state == EngState.PROPOSED for e in sc.engage.engagements.values()):
                break
        denied = sc.engage.deny(operator="TEST")
        self.assertIsNotNone(denied)
        track = sc.engage.engagements[denied].track_id
        _run(sc, 60)
        again = [e for e in sc.engage.engagements.values()
                 if e.track_id == track and e.eng_id != denied]
        self.assertEqual(again, [])


class FullAttackTests(unittest.TestCase):
    """Default laydown: convoy of 4 enemy UGVs + 15 escort drones, PVO live."""

    def _run_attack(self, auto_roe=True, pvo=True, seconds=900):
        sc = Scenario(dt=0.1, auto_roe=auto_roe)
        sc.engage.pvo_enabled = pvo
        shots = {p.site_id: [] for p in sc.engage.pvo_sites}
        last = {p.site_id: 0 for p in sc.engage.pvo_sites}
        c = sc.laydown.convoy
        s0, g0 = sc.laydown.at(*c.start_km), sc.laydown.at(*c.objective_km)
        via = ((s0[0] + g0[0]) / 2, (s0[1] + g0[1]) / 2)     # midpoint of the (offline, straight) route
        passed_via = set()
        for _ in range(int(seconds / sc._dt)):
            sc.step()
            for p in sc.engage.pvo_sites:
                if p.shots != last[p.site_id]:
                    shots[p.site_id].append(sc._t)
                    last[p.site_id] = p.shots
            for v in sc.convoy:
                if v.distance_to_m(*via) < 60:
                    passed_via.add(v.target_id)
            if all(not t.engageable for t in sc.targets if t.hostile and t.state.name != "PENDING") \
                    and all(t.state.name != "PENDING" for t in sc.targets if t.hostile):
                break
        return sc, shots, passed_via

    def test_attack_is_repelled_with_auto_roe(self):
        sc, shots, passed_via = self._run_attack(seconds=1500)
        self.assertEqual(len(sc.convoy), 4)
        self.assertEqual(len(sc.escorts), 17)                 # 15 attack UAVs + 2 helicopters
        self.assertEqual(len(sc.helicopters), 2)
        # Every vehicle that got going drove the planned route past its midpoint
        started = {v.target_id for v in sc.convoy if v.distance_to_m(*sc.laydown.at(*sc.laydown.convoy.start_km)) > 100}
        self.assertTrue(started <= passed_via | {v.target_id for v in sc.convoy if v.state.name != "MOVING"})
        self.assertEqual(sc.assaults, 0, "no vehicle may reach its objective")
        self.assertTrue(all(v.state.name in ("DESTROYED", "DISABLED") for v in sc.convoy))
        # The escort stays with the convoy and strikes as one wave from 2.5 km, so
        # some leakers are expected: at least ~80 % of the 17 hostile drones stopped.
        self.assertLessEqual(sc.base_hits, 3)
        civil = next(t for t in sc.targets if t.target_id == "CIVIL-C")
        self.assertIn(civil.state.name, ("FLYING", "EXITED"), "the neutral drone must never be shot")
        # PVO: at most one shot per minute per site, never beyond its ammunition
        for site in sc.engage.pvo_sites:
            ts = shots[site.site_id]
            self.assertTrue(all(b - a >= 59.9 for a, b in zip(ts, ts[1:])), (site.site_id, ts))
            self.assertGreaterEqual(site.ammo, 0)
        self.assertGreater(sum(p.kills for p in sc.engage.pvo_sites), 5)
        # UGV charges: never more than 3 rounds
        for g in sc.ugvs:
            self.assertGreaterEqual(g.charges, 0)
            self.assertLessEqual(g.max_charges - g.charges, 3)

    def test_pvo_hold_fire(self):
        sc, shots, _ = self._run_attack(auto_roe=False, pvo=False, seconds=200)
        self.assertEqual(sum(len(v) for v in shots.values()), 0)

    def test_air_element_flies_in_parallel_and_attacks_together(self):
        from sim.target import _bearing_deg
        sc = Scenario(dt=0.1)
        sc.engage.pvo_enabled = False
        base = (sc.laydown.base.lat, sc.laydown.base.lon)
        samples = 0
        release_ticks = set()
        fired_from = []
        missiles = {h.target_id: h.missiles for h in sc.helicopters}
        for _ in range(13000):
            sc.step()
            lead = sc._convoy_lead()
            flying = [e for e in sc.escorts if e.alive and not e.released]
            if lead and flying and lead.distance_to_m(*base) > 3_000 and int(sc._t * 10) % 300 == 0:
                samples += 1
                L = lead.position
                sides = [((_bearing_deg(L.lat, L.lon, e.position.lat, e.position.lon) - sc._axis_deg) % 360) < 180
                         for e in flying]
                self.assertTrue(any(sides) and not all(sides), "escort must fly on both flanks")
                near = [e.distance_to_m(L.lat, L.lon) < 2_000 for e in flying]
                self.assertGreaterEqual(sum(near), 0.8 * len(near), "escort stays with the convoy")
            for e in sc.escorts:
                if e.released and e.target_id not in {x for x, _ in release_ticks}:
                    release_ticks.add((e.target_id, round(sc._t, 1)))
            for h in sc.helicopters:
                if h.missiles < missiles[h.target_id]:
                    missiles[h.target_id] = h.missiles
                    fired_from.append(h.distance_to_m(*base))
        self.assertGreater(samples, 3)
        self.assertEqual(len({t for _, t in release_ticks}), 1, "the whole air element attacks at once")
        self.assertTrue(fired_from, "helicopters fire missiles")
        self.assertTrue(all(d > 1_300 for d in fired_from), "helicopters fire from stand-off")

    def test_jammer_never_used_on_helicopters(self):
        sc = Scenario(dt=0.1, auto_roe=True)
        sc.engage.pvo_enabled = False                        # keep the helicopters alive longer
        for _ in range(11000):
            sc.step()
            for h in sc.helicopters:
                self.assertNotIn(h.state.name, ("JAMMED", "LANDED"), "a manned helicopter cannot be jammed")
        # Once classified, a helicopter track is never *kept* on a jammer
        for e in sc.engage.engagements.values():
            trk = sc.tracker.get(e.track_id)
            if trk is not None and trk.obj_class == "ATTACK_HELICOPTER" and e.state.name == "ENGAGING":
                self.assertNotEqual(e.effector_kind, "JAMMER")

    def test_convoy_waits_for_air_from_the_west_then_attacks_from_the_south(self):
        sc = Scenario(dt=0.1)
        sc.engage.pvo_enabled = False
        ld, c = sc.laydown, sc.laydown.convoy
        start, air0 = ld.at(*c.start_km), ld.at(*c.air_start_km)
        self.assertLess(start[0], ld.base.lat - 0.03, "trucks assemble south of the base")
        self.assertLess(air0[1], ld.ground_bbox[2], "air element launches west of the terrain area (Kosovo side)")
        went = None
        for _ in range(12000):
            sc.step()
            if sc._convoy_go and went is None:
                went = sc._t
                on = [e for e in sc.escorts if e.alive and e.distance_to_m(*e.slot_position()) <= 1_200]
                self.assertGreaterEqual(len(on), 0.8 * sum(e.alive for e in sc.escorts))
            if went is None:
                self.assertTrue(all(v.state.name == "PENDING" for v in sc.convoy),
                                "trucks hold until the air element is on station")
        self.assertIsNotNone(went)
        self.assertLess(went, c.rendezvous_timeout_s)

    def test_escorts_break_off_when_convoy_closes(self):
        sc = Scenario(dt=0.1)
        base = (sc.laydown.base.lat, sc.laydown.base.lon)
        released_at_dist = None
        for _ in range(14000):
            sc.step()
            lead = sc._convoy_lead()
            if lead and any(e.released for e in sc.escorts):
                released_at_dist = lead.distance_to_m(*base)
                break
        self.assertIsNotNone(released_at_dist)
        self.assertLessEqual(released_at_dist, sc.laydown.convoy.release_dist_m + 50)


# ── artemides-trax contract (local fake server) ──────────────────────────────

class _FakeArtemides(BaseHTTPRequestHandler):
    calls: list = []
    edits: dict = {}
    route_delay = 0.0
    river_until_via = False      # answer like vojsrb: straight line + no_route_found without a via

    def log_message(self, *a):
        pass

    def _reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self):
        return self.headers.get("Authorization") == "Bearer test-token"

    def do_GET(self):
        u = urlparse(self.path)
        _FakeArtemides.calls.append(("GET", u.path, None))
        if u.path == "/api/auth.php":
            return self._reply(200, {"ok": True, "user": {"username": "amcs"} if self._auth_ok() else None})
        if u.path == "/api/traversability.php":
            if not self._auth_ok():
                return self._reply(401, {"error": "Authentication required"})
            q = {k: float(v[0]) for k, v in parse_qs(u.query).items()}
            lat, lon, rad, res = q["lat"], q["lng"], q["radius"], q["res"]
            cells = []
            n = int(2 * rad / res)
            for r in range(n):
                for c in range(n):
                    cl, cn = lat - rad + (r + 0.5) * res, lon - rad + (c + 0.5) * res
                    # a paved road along lat 42.2744, forest elsewhere
                    cost = 0.08 if abs(cl - 42.2744) < res else 0.92
                    cells.append({"lat": cl, "lon": cn, "cost": cost, "trust": 1 - cost, "sources": {}})
            return self._reply(200, {"cells": cells, "meta": {"resolution": res}})
        self._reply(404, {"error": "nope"})

    def do_POST(self):
        u = urlparse(self.path)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeArtemides.calls.append(("POST", u.path, body))
        if not self._auth_ok():
            return self._reply(401, {"error": "Authentication required"})
        if u.path == "/api/route.php":
            threading.Event().wait(_FakeArtemides.route_delay)
            f, t = body["from"], body["to"]
            mid = {"lat": (f["lat"] + t["lat"]) / 2 + 0.001, "lon": (f["lon"] + t["lon"]) / 2}
            if _FakeArtemides.river_until_via and not body.get("via"):
                return self._reply(200, {"status": "ok", "method": "mixed",
                                         "waypoints": [dict(f, seq=0), dict(t, seq=1)],
                                         "suggestions": [{"type": "no_route_found", "leg_index": 0,
                                                          "reason": "water_no_known_bridge",
                                                          "suggested_via": mid}]})
            return self._reply(200, {"status": "ok", "method": "astar",
                                     "waypoints": [dict(f, seq=0), dict(mid, seq=1), dict(t, seq=2)]})
        if u.path == "/api/manual_edit.php":
            eid = len(_FakeArtemides.edits) + 1
            _FakeArtemides.edits[eid] = body
            return self._reply(200, {"ok": True, "id": eid})
        if u.path == "/api/telemetry.php":
            return self._reply(200, {"ok": True})
        self._reply(404, {"error": "nope"})

    def do_DELETE(self):
        u = urlparse(self.path)
        _FakeArtemides.calls.append(("DELETE", u.path, parse_qs(u.query)))
        eid = int(parse_qs(u.query)["id"][0])
        _FakeArtemides.edits.pop(eid, None)
        self._reply(200, {"ok": True})


class ArtemidesLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), _FakeArtemides)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        _FakeArtemides.calls.clear()
        _FakeArtemides.edits.clear()

    def test_router_failure_means_no_route_offline_means_straight_line(self):
        client = ArtemidesClient(ArtemidesConfig())
        h = ArtemidesRouter(client).request("UGV", (42.0, 20.0), (42.01, 20.01))
        h._fut.exception(timeout=5)
        wps, src = h.result()
        self.assertEqual(wps, [])
        self.assertTrue(src.startswith("NO ROUTE"))
        client.shutdown()
        # Without any artemides link the scenario uses the offline straight-line router
        sc = Scenario(dt=0.1)
        ugv = sc.ugvs[0]
        ugv.assign("TEST")
        ugv.navigate_to(ugv.home[0] + 0.01, ugv.home[1])
        sc.step()
        self.assertEqual(ugv.route_source, "offline straight-line")

    def test_route_whoami_and_auth_error(self):
        client = ArtemidesClient(ArtemidesConfig(base_url=self.url, token="test-token"))
        self.assertEqual(client.whoami()["username"], "amcs")
        wps, src = client.route((42.0, 20.0), (42.02, 20.02))
        self.assertEqual(len(wps), 3)
        self.assertEqual(src, "artemides:astar")
        sent = [c for c in _FakeArtemides.calls if c[1] == "/api/route.php"][0][2]
        self.assertFalse(sent["save_to_db"])

        bad = ArtemidesClient(ArtemidesConfig(base_url=self.url, token="wrong"))
        h = ArtemidesRouter(bad).request("UGV", (42.0, 20.0), (42.01, 20.01))
        h._fut.exception(timeout=5)
        wps, src = h.result()
        self.assertIn("HTTP 401", src)
        self.assertEqual(bad.status()["errors"], 1)
        client.shutdown(); bad.shutdown()

    def test_scenario_drives_ugv_on_artemides_route(self):
        client = ArtemidesClient(ArtemidesConfig(base_url=self.url, token="test-token"))
        _FakeArtemides.route_delay = 0.3
        sc = Scenario(dt=0.1, route_provider=ArtemidesRouter(client))
        ugv = sc.ugvs[0]
        start = ugv.position
        ugv.navigate_to(start.lat + 0.01, start.lon + 0.01)
        sc.step()
        self.assertEqual((ugv.position.lat, ugv.position.lon), (start.lat, start.lon),
                         "UGV must not cut across terrain while the route is pending")
        for _ in range(100):
            sc.step()
            if ugv.route_source.startswith("artemides"):
                break
            threading.Event().wait(0.02)
        _FakeArtemides.route_delay = 0.0
        self.assertEqual(ugv.route_source, "artemides:astar")
        for _ in range(20):
            sc.step()
        self.assertNotEqual((ugv.position.lat, ugv.position.lon), (start.lat, start.lon))
        client.shutdown()

    def test_bridge_publishes_and_retracts_threats(self):
        cfg = ArtemidesConfig(base_url=self.url, token="test-token",
                              telemetry=True, publish_threats=True)
        bridge = ArtemidesBridge(ArtemidesClient(cfg))
        sc = Scenario(dt=0.1, auto_roe=True)
        sc.engage.pvo_enabled = False       # PVO would kill hostiles in the tick they are declared
        published = False
        for _ in range(3300):
            snap = sc.step()
            bridge.on_snapshot(snap)
            published = published or bool(_FakeArtemides.edits)
        bridge.shutdown()
        self.assertTrue(published, "hostile track should be published as a threat marker")
        kinds = {b["edit_type"] for b in [c[2] for c in _FakeArtemides.calls
                                          if c[1] == "/api/manual_edit.php" and c[0] == "POST"]}
        self.assertEqual(kinds, {"threat"})
        self.assertEqual(_FakeArtemides.edits, {}, "all markers retracted after neutralisation")
        self.assertTrue(any(c[1] == "/api/telemetry.php" for c in _FakeArtemides.calls))

    def test_straight_line_over_river_is_not_a_route(self):
        client = ArtemidesClient(ArtemidesConfig(base_url=self.url, token="test-token"))
        _FakeArtemides.river_until_via = True
        try:
            wps, src = client.route((42.0, 20.0), (42.02, 20.02))
            self.assertEqual(src, "artemides:astar +1 via")          # retried with the suggested via
            self.assertTrue(any(c[1] == "/api/route.php" and c[2].get("via") for c in _FakeArtemides.calls))
            self.assertTrue(all(c[2].get("allow_long_route") for c in _FakeArtemides.calls
                                if c[1] == "/api/route.php"))
            with self.assertRaises(artemides.ArtemidesError):
                client.route((42.0, 20.0), (42.02, 20.02), max_retries=0)
        finally:
            _FakeArtemides.river_until_via = False
            client.shutdown()

    def test_failed_route_holds_ugv(self):
        bad = ArtemidesClient(ArtemidesConfig(base_url=self.url, token="wrong"))
        sc = Scenario(dt=0.1, route_provider=ArtemidesRouter(bad))
        ugv = sc.ugvs[0]
        start = (ugv.position.lat, ugv.position.lon)
        ugv.navigate_to(start[0] + 0.01, start[1])
        for _ in range(50):
            sc.step()
            if ugv.route_source.startswith("NO ROUTE"):
                break
            threading.Event().wait(0.02)
        self.assertTrue(ugv.route_source.startswith("NO ROUTE"))
        for _ in range(20):
            sc.step()
        self.assertEqual((ugv.position.lat, ugv.position.lon), start)
        bad.shutdown()

    def test_drivability_download_and_cache(self):
        import tempfile
        from pathlib import Path
        client = ArtemidesClient(ArtemidesConfig(base_url=self.url, token="test-token"))
        bbox = (42.26, 42.29, 21.59, 21.62)
        with tempfile.TemporaryDirectory() as tmp:
            old = artemides.CACHE_DIR
            artemides.CACHE_DIR = Path(tmp)
            try:
                grid, src = load_drivability(client, bbox, res_deg=0.001)
                self.assertEqual(src, "artemides traversability")
                self.assertEqual(grid.classify_at(42.2744, 21.60)[0], "ROAD")
                self.assertEqual(grid.classify_at(42.285, 21.60)[0], "NO-GO")
                calls = len(_FakeArtemides.calls)
                grid2, src2 = load_drivability(client, bbox, res_deg=0.001)
                self.assertTrue(src2.startswith("cache"))
                self.assertEqual(len(_FakeArtemides.calls), calls, "second load must hit the cache")
                self.assertEqual(grid2.costs, grid.costs)
            finally:
                artemides.CACHE_DIR = old
        no_token = ArtemidesClient(ArtemidesConfig(base_url=self.url))
        with self.assertRaises(artemides.ArtemidesError):
            no_token.fetch_drivability(bbox, 0.001)
        client.shutdown(); no_token.shutdown()


# ── laydown / drivability / platforms ─────────────────────────────────────────

def _road_grid(bbox=(42.23, 42.32, 21.52, 21.69), res=0.001) -> DrivabilityGrid:
    cells = []
    la0, la1, lo0, lo1 = bbox
    r = 0
    while la0 + (r + 0.5) * res < la1:
        c = 0
        while lo0 + (c + 0.5) * res < lo1:
            lat = la0 + (r + 0.5) * res
            cells.append({"lat": lat, "lon": lo0 + (c + 0.5) * res,
                          "cost": 0.08 if abs(lat - 42.2674) < 0.0015 else 0.95})
            c += 1
        r += 1
    return DrivabilityGrid.from_cells(cells, bbox, res)


class LaydownTests(unittest.TestCase):
    def test_json_round_trip(self):
        ld, _ = DEFAULT_LAYDOWN.add_site("ugv", 42.28, 21.60)
        ld = ld.with_zone_radius(3000).with_base(42.28, 21.61)
        back = Laydown.from_json(ld.to_json())
        self.assertEqual(back, ld)

    def test_editing(self):
        ld = DEFAULT_LAYDOWN.with_base(42.29, 21.62)
        self.assertEqual((ld.radars[0].lat, ld.radars[0].lon), (42.29, 21.62), "base radar follows base")
        self.assertEqual(DEFAULT_LAYDOWN.with_zone_radius(10).zone_radius_m, 500.0)
        ld2, site = ld.add_site("acoustic", 42.25, 21.55)
        self.assertEqual(len(ld2.acoustic), len(ld.acoustic) + 1)
        ld3, removed = ld2.remove_nearest(42.2501, 21.5501)
        self.assertEqual(removed, site)
        self.assertEqual(ld3.acoustic, ld.acoustic)
        # threats move with the base
        t = DEFAULT_LAYDOWN.threats[0]
        a, b = DEFAULT_LAYDOWN.threat_start(t), ld.threat_start(t)
        self.assertAlmostEqual(b[0] - a[0], 42.29 - DEFAULT_LAYDOWN.base.lat, places=6)


class DrivabilityTests(unittest.TestCase):
    def test_classes_and_speeds(self):
        self.assertEqual(classify(0.05), ("ROAD", 80.0))
        self.assertEqual(classify(0.6), ("DIFFICULT", 15.0))
        self.assertEqual(classify(0.9)[0], "NO-GO")
        self.assertEqual(classify(None)[0], "UNKNOWN")

    def test_nearest_drivable_and_png(self):
        g = _road_grid()
        self.assertFalse(g.is_drivable(42.30, 21.60))
        near = g.nearest_drivable(42.2720, 21.60, max_m=1000)
        self.assertIsNotNone(near)
        self.assertTrue(g.is_drivable(*near))
        png = g.to_png()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
        self.assertEqual((w, h), (g.cols, g.rows))

    def test_ugv_speed_follows_terrain(self):
        sc = Scenario(dt=0.1)
        ugv = sc.ugvs[0]
        ugv.assign("TEST")                                   # keep it from returning home
        ugv.navigate_to(ugv.home[0], ugv.home[1] + 0.02)
        sc.step(); sc.step()
        self.assertAlmostEqual(ugv._speed * 3.6, 20.0, delta=0.5)        # no data → 20 km/h
        sc.set_drivability(_road_grid())
        ugv.set_route([(ugv.home[0], ugv.home[1] + 0.02)], "test")
        sc.step()
        self.assertAlmostEqual(ugv._speed * 3.6, 80.0, delta=0.5)        # on the road → 80 km/h
        self.assertEqual(ugv.terrain_class, "ROAD")


class InterceptorLifecycleTests(unittest.TestCase):
    def test_idle_hidden_launch_recall_land(self):
        sc = Scenario(dt=0.1, targets=[])
        u = sc.uavs[0]
        self.assertEqual(u.mode, UAVMode.IDLE)
        self.assertFalse(u.airborne)
        for _ in range(50):
            sc.step()
        self.assertEqual(sc.tracker.iff_rejects, 0, "idle drones on the pad are invisible to our radars")
        u.launch_patrol()
        for _ in range(300):
            sc.step()
        self.assertEqual(u.mode, UAVMode.PATROL)
        self.assertGreater(u.position.alt, 100)
        self.assertGreater(sc.tracker.iff_rejects, 0, "airborne drone is seen by radar and IFF-filtered")
        self.assertEqual(sc.tracker.tracks, [])
        u.return_to_base()
        for _ in range(900):
            sc.step()
        self.assertEqual(u.mode, UAVMode.IDLE)
        self.assertEqual(u.position.alt, 0.0)


class EditorBusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["ARTEMIDES_URL"] = ""                     # offline bus
        from PyQt6.QtCore import QCoreApplication
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_placement_rules_and_save_load(self):
        import tempfile
        from pathlib import Path
        import sim.bus as busmod
        bus = busmod.SimBus(laydown=DEFAULT_LAYDOWN)
        results = []
        bus.editResult.connect(lambda r: results.append(r))
        bus.setEditMode(True)
        bus.editPlace("ugv", 42.40, 21.60)                   # outside artemides area
        self.assertFalse(results[-1]["ok"])
        bus._drivability = _road_grid()
        bus.editPlace("ugv", 42.30, 21.60)                   # forest → NO-GO
        self.assertFalse(results[-1]["ok"])
        self.assertIn("NO-GO", results[-1]["message"])
        n = len(bus._laydown.ugvs)
        bus.editPlace("ugv", 42.2674, 21.62)                 # on the road
        self.assertTrue(results[-1]["ok"], results[-1])
        self.assertEqual(len(bus._laydown.ugvs), n + 1)
        bus.editPlace("radar", 42.25, 21.55)
        self.assertEqual(len(bus._scenario.radars), 2)
        with tempfile.TemporaryDirectory() as tmp:
            old = busmod.SCENARIO_DIR
            busmod.SCENARIO_DIR = Path(tmp)
            try:
                bus.saveScenario("Test Laydown")
                saved = bus._laydown
                bus.loadScenario(busmod._BUILTIN)
                self.assertEqual(bus._laydown, DEFAULT_LAYDOWN)
                bus.loadScenario("Test Laydown")
                self.assertEqual(bus._laydown, saved)
            finally:
                busmod.SCENARIO_DIR = old
        bus.setEditMode(False)
        bus.shutdown()

    def test_place_move_delete_all_kinds(self):
        import sim.bus as busmod
        bus = busmod.SimBus(laydown=DEFAULT_LAYDOWN)
        results = []
        bus.editResult.connect(lambda r: results.append(r))
        bus.setEditMode(True)
        n_pvo, n_gg, n_sei = len(bus._laydown.pvo), len(bus._laydown.gg), len(bus._laydown.seismic)
        bus.editPlace("pvo", 42.24, 21.55)
        bus.editPlace("gg", 42.25, 21.56)
        bus.editPlace("seismic", 42.26, 21.57)
        self.assertEqual((len(bus._laydown.pvo), len(bus._laydown.gg), len(bus._laydown.seismic)),
                         (n_pvo + 1, n_gg + 1, n_sei + 1))
        self.assertEqual(len(bus._scenario.engage.pvo_sites), n_pvo + 1, "new PVO site is live in the sim")
        # MOVE: pick PVO-ALPHA-01, drop it elsewhere
        p0 = bus._laydown.pvo[0]
        bus.editPlace("move", p0.lat + 0.001, p0.lon)
        self.assertTrue(results[-1]["ok"]); self.assertEqual(results[-1]["picked"]["label"], p0.site_id)
        bus.editPlace("move", 42.31, 21.60)
        moved = next(p for p in bus._laydown.pvo if p.site_id == p0.site_id)
        self.assertEqual((moved.lat, moved.lon), (42.31, 21.60))
        # MOVE a UGV onto NO-GO terrain is refused and the pick is kept
        bus._drivability = _road_grid()
        u0 = bus._laydown.ugvs[0]
        bus.editPlace("move", u0.lat, u0.lon)
        bus.editPlace("move", 42.30, 21.60)
        self.assertFalse(results[-1]["ok"])
        bus.editPlace("move", 42.2674, 21.63)
        self.assertTrue(results[-1]["ok"], results[-1])
        self.assertEqual(bus._laydown.ugvs[0].lon, 21.63)
        # MOVE the base: PVO stays put, zone follows
        b = bus._laydown.base
        bus.editPlace("move", b.lat, b.lon)
        bus.editPlace("move", b.lat + 0.01, b.lon)
        self.assertAlmostEqual(bus._laydown.base.lat, b.lat + 0.01)
        self.assertEqual(next(p for p in bus._laydown.pvo if p.site_id == p0.site_id).lat, 42.31)
        # DELETE the GG we placed
        bus.editPlace("delete", 42.2501, 21.5601)
        self.assertEqual(len(bus._laydown.gg), n_gg)
        bus.shutdown()

    def test_startup_uses_last_saved_scenario(self):
        import tempfile, json
        from pathlib import Path
        import sim.bus as busmod
        with tempfile.TemporaryDirectory() as tmp:
            old = busmod.SCENARIO_DIR
            busmod.SCENARIO_DIR = Path(tmp)
            try:
                self.assertEqual(busmod.startup_laydown()[0], DEFAULT_LAYDOWN)   # nothing saved yet
                bus = busmod.SimBus(laydown=DEFAULT_LAYDOWN)
                bus.saveScenario("Alfa")
                bus.setZoneRadius(3000)
                bus.saveScenario("Bravo")
                self.assertEqual(busmod.startup_laydown()[0].name, "Bravo")
                bus.saveScenario("Alfa")                      # re-saving an older one makes it the default
                ld, src = busmod.startup_laydown()
                self.assertEqual((ld.name, ld.zone_radius_m), ("Alfa", 3000.0))
                self.assertIn("last saved", src)
                self.assertEqual(len(list(Path(tmp).glob("*.json"))), 2, "same name overwrites its file")
                bus.shutdown()
                fresh = busmod.SimBus()                       # no laydown given → last saved
                self.assertEqual(fresh._laydown.name, "Alfa")
                fresh.shutdown()
                # Legacy file: PVO / GG stored as base offsets
                d = json.loads(DEFAULT_LAYDOWN.to_json())
                d["name"] = "Legacy"
                d.pop("pvo"); d.pop("gg")
                d["pvo_km"] = [["PVO-01", 2.6, -3.6]]
                d["gg_km"] = [["GG-01", -3.3, -2.5]]
                legacy = Laydown.from_json(json.dumps(d))
                exp = DEFAULT_LAYDOWN.at(2.6, -3.6)
                self.assertAlmostEqual(legacy.pvo[0].lat, exp[0], places=6)
                self.assertEqual(legacy.gg[0].site_id, "GG-01")
            finally:
                busmod.SCENARIO_DIR = old


if __name__ == "__main__":
    unittest.main()
