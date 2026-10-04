"""
artemides-trax link — connects the AMCS counter-UAS chain to the
artemides-trax platform (terrain / traversability / A* ground routing).

What flows where
────────────────
  AMCS  ──POST /api/route.php──────────▶  artemides   UGV ground route over real
        ◀── waypoints (A* / fallback) ──              terrain + traversability
  AMCS  ──GET  /api/traversability.php─▶  artemides   drivability layer (token)
  AMCS  ──POST /api/telemetry.php──────▶  artemides   own-vehicle telemetry (opt-in)
  AMCS  ──POST /api/manual_edit.php────▶  artemides   'threat' marker under each
        ──DELETE ?id=N ────────────────▶              hostile track (opt-in), so
                                                      ground routes avoid it

Every call runs on a worker thread and never blocks the 10 Hz sim loop.  A
routing failure (no network, 401, 403 outside demo area, A* failure) is
returned as "no route" — the UGV holds instead of cutting across terrain —
and is reported in status().

Configuration (environment)
───────────────────────────
  ARTEMIDES_URL              base URL, e.g. https://dev.artemides-trax.com
                             (unset → link disabled, fully offline)
  ARTEMIDES_TOKEN            Bearer API token (api/auth.php create_token)
  ARTEMIDES_VEHICLE_PROFILE  vehicle_profiles.code for UGV routing (optional)
  ARTEMIDES_ROUTE_PROFILE    route_profile (default "medium")
  ARTEMIDES_TELEMETRY=1      push own-vehicle telemetry        (default off)
  ARTEMIDES_PUBLISH_THREATS=1  publish hostile tracks as markers (default off)

The two write paths are opt-in on purpose: simulated positions posted as
real telemetry would pollute artemides' driven-corridor statistics.
"""
from __future__ import annotations
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import hashlib
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from sim.drivability import DrivabilityGrid

_TIMEOUT_S = 15.0
_ROUTE_TIMEOUT_S = 60.0          # long A* legs can take ~25 s server-side


@dataclass
class ArtemidesConfig:
    base_url:        str | None = None
    token:           str | None = None
    vehicle_profile: str | None = None
    route_profile:   str = "medium"
    telemetry:       bool = False
    publish_threats: bool = False

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    @classmethod
    def from_env(cls) -> "ArtemidesConfig":
        url = (os.environ.get("ARTEMIDES_URL") or "").strip().rstrip("/")
        return cls(
            base_url        = url or None,
            token           = (os.environ.get("ARTEMIDES_TOKEN") or "").strip() or None,
            vehicle_profile = (os.environ.get("ARTEMIDES_VEHICLE_PROFILE") or "").strip() or None,
            route_profile   = (os.environ.get("ARTEMIDES_ROUTE_PROFILE") or "medium").strip(),
            telemetry       = os.environ.get("ARTEMIDES_TELEMETRY") == "1",
            publish_threats = os.environ.get("ARTEMIDES_PUBLISH_THREATS") == "1",
        )


class ArtemidesError(RuntimeError):
    pass


class ArtemidesClient:
    """Thin HTTP client for the artemides-trax PHP API."""

    def __init__(self, cfg: ArtemidesConfig) -> None:
        self.cfg = cfg
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="artemides")
        self._lock = threading.Lock()
        self._stats = {"ok": 0, "errors": 0, "last_error": "", "last_ok": None, "user": None}

    # ── low level ─────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: dict | None = None,
                 query: dict | None = None, timeout: float = _TIMEOUT_S) -> dict:
        if not self.cfg.enabled:
            raise ArtemidesError("artemides link disabled (ARTEMIDES_URL not set)")
        url = f"{self.cfg.base_url}/{path.lstrip('/')}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "AMCS-C2/1.0")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.cfg.token:
            req.add_header("Authorization", f"Bearer {self.cfg.token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode()).get("error", e.reason)
            except Exception:
                msg = e.reason
            self._record_error(f"{method} {path}: HTTP {e.code} {msg}")
            raise ArtemidesError(f"HTTP {e.code}: {msg}") from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            self._record_error(f"{method} {path}: {e}")
            raise ArtemidesError(str(e)) from None
        with self._lock:
            self._stats["ok"] += 1
            self._stats["last_ok"] = time.time()
        return payload

    def _record_error(self, msg: str) -> None:
        with self._lock:
            self._stats["errors"] += 1
            self._stats["last_error"] = msg

    def status(self) -> dict:
        with self._lock:
            s = dict(self._stats)
        s.update(enabled=self.cfg.enabled, url=self.cfg.base_url or "",
                 authenticated=bool(self.cfg.token),
                 telemetry=self.cfg.telemetry, publishThreats=self.cfg.publish_threats)
        return s

    def shutdown(self, wait: bool = False) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=not wait)

    # ── API calls (synchronous) ───────────────────────────────────────────

    def whoami(self) -> dict | None:
        user = self._request("GET", "api/auth.php", query={"action": "me"}).get("user")
        with self._lock:
            self._stats["user"] = user.get("username") if user else None
        return user

    def route(self, start: tuple[float, float], goal: tuple[float, float],
              vehicle_id: str | None = None,
              via: list[tuple[float, float]] | None = None,
              max_retries: int = 2) -> tuple[list[tuple[float, float]], str]:
        """
        Drivable route start → via… → goal.

        artemides may answer a leg it cannot solve (e.g. "river without a
        known bridge") with a straight line, flagged only in `suggestions`
        as no_route_found.  That is not drivable: we retry with the via point
        the server suggests for that leg, and give up after max_retries.
        """
        via = list(via or [])
        for attempt in range(max_retries + 1):
            body = {
                "from": {"lat": start[0], "lon": start[1]},
                "to":   {"lat": goal[0],  "lon": goal[1]},
                "max_waypoints": 150,
                "route_profile": self.cfg.route_profile,
                "save_to_db": False,
                "allow_long_route": True,
            }
            if via:
                body["via"] = [{"lat": v[0], "lon": v[1]} for v in via]
            if self.cfg.vehicle_profile:
                body["vehicle_profile"] = self.cfg.vehicle_profile
            res = self._request("POST", "api/route.php", body, timeout=_ROUTE_TIMEOUT_S)
            blocked = [sg for sg in res.get("suggestions", []) if sg.get("type") == "no_route_found"]
            wps = [(float(w["lat"]), float(w["lon"])) for w in res.get("waypoints", [])]
            if res.get("status", "ok") != "ok" or not wps:
                raise ArtemidesError(res.get("error") or res.get("message") or "route returned no waypoints")
            if not blocked:
                tag = f"artemides:{res.get('method', 'unknown')}"
                return wps, tag + (f" +{len(via)} via" if via else "")
            sg = blocked[0]
            sv = sg.get("suggested_via")
            if attempt == max_retries or not sv:
                raise ArtemidesError(f"no drivable route ({sg.get('reason', 'blocked')})")
            leg = int(sg.get("leg_index", 0))
            via.insert(min(leg, len(via)), (float(sv["lat"]), float(sv["lon"])))
        raise ArtemidesError("no drivable route")

    def traversability(self, lat: float, lon: float, radius_deg: float,
                       res_deg: float) -> list[dict]:
        res = self._request("GET", "api/traversability.php", query={
            "lat": f"{lat:.6f}", "lng": f"{lon:.6f}",
            "radius": f"{radius_deg:.5f}", "res": f"{res_deg:.6f}"})
        return res.get("cells", [])

    def fetch_drivability(self, bbox: tuple[float, float, float, float],
                          res_deg: float = 0.0007, tile_radius_deg: float = 0.02,
                          progress=None) -> DrivabilityGrid:
        """Tile the bbox into traversability requests and merge them."""
        lat_min, lat_max, lon_min, lon_max = bbox
        cells: list[dict] = []
        step = 2 * tile_radius_deg
        centers = []
        la = lat_min + tile_radius_deg
        while la - tile_radius_deg < lat_max:
            lo = lon_min + tile_radius_deg
            while lo - tile_radius_deg < lon_max:
                centers.append((la, lo))
                lo += step
            la += step
        for i, (la, lo) in enumerate(centers):
            cells += self.traversability(la, lo, tile_radius_deg, res_deg)
            if progress:
                progress(i + 1, len(centers))
        return DrivabilityGrid.from_cells(cells, bbox, res_deg)

    def post_telemetry(self, vehicle_id: str, lat: float, lon: float,
                       alt: float | None, speed: float, heading: float) -> dict:
        body = {"vehicle_id": vehicle_id, "lat": lat, "lon": lon,
                "speed": round(speed, 2), "heading": round(heading, 1)}
        if alt is not None:
            body["alt"] = round(alt, 1)
        return self._request("POST", "api/telemetry.php", body)

    def create_threat(self, lat: float, lon: float, radius_m: float,
                      label: str, meta: dict) -> int:
        res = self._request("POST", "api/manual_edit.php", {
            "lat": lat, "lon": lon, "radius_m": radius_m,
            "edit_type": "threat", "label": label, "meta": meta,
        })
        return int(res["id"])

    def delete_edit(self, edit_id: int) -> None:
        self._request("DELETE", "api/manual_edit.php", query={"id": edit_id})

    # ── async wrappers ────────────────────────────────────────────────────

    def submit(self, fn, *args, **kw) -> Future:
        return self._pool.submit(fn, *args, **kw)


# ── Drivability layer (cached on disk) ────────────────────────────────────────

from sim import paths

CACHE_DIR = paths.cache_dir()


def drivability_cache_path(url: str, bbox, res_deg: float) -> Path:
    key = hashlib.sha1(f"{url}|{bbox}|{res_deg}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"drivability_{key}.json"


def load_drivability(client: ArtemidesClient, bbox, res_deg: float = 0.0007,
                     refresh: bool = False, progress=None) -> tuple[DrivabilityGrid, str]:
    """Grid for bbox from the disk cache, else from artemides (and cache it)."""
    path = drivability_cache_path(client.cfg.base_url or "", tuple(bbox), res_deg)
    if path.exists() and not refresh:
        return DrivabilityGrid.from_dict(json.loads(path.read_text())), f"cache {path.name}"
    grid = client.fetch_drivability(tuple(bbox), res_deg, progress=progress)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(grid.to_dict()))
    return grid, "artemides traversability"


# ── Route provider for Scenario ───────────────────────────────────────────────

class _RouteHandle:
    def __init__(self, fut: Future, goal: tuple[float, float]) -> None:
        self._fut = fut
        self._goal = goal

    def done(self) -> bool:
        return self._fut.done()

    def result(self):
        try:
            return self._fut.result()
        except Exception as e:
            # No drivable route known — the UGV holds rather than cutting across terrain
            return [], f"NO ROUTE ({e})"


class ArtemidesRouter:
    """Scenario route provider backed by artemides-trax A* routing."""

    def __init__(self, client: ArtemidesClient) -> None:
        self._client = client

    def request(self, vehicle_id: str, start: tuple[float, float],
                goal: tuple[float, float], via=None) -> _RouteHandle:
        return _RouteHandle(self._client.submit(self._client.route, start, goal, vehicle_id, via), goal)


# ── Snapshot bridge: telemetry + threat markers ───────────────────────────────

@dataclass
class _Published:
    edit_id: Future
    lat: float
    lon: float


class ArtemidesBridge:
    """
    Feeds scenario snapshots to artemides-trax:
      • own UAV / UGV telemetry at ≤ 1 Hz each      (ARTEMIDES_TELEMETRY=1)
      • one 'threat' manual_edit per hostile track,
        removed when the track is neutralised/lost   (ARTEMIDES_PUBLISH_THREATS=1)
    """

    TELEMETRY_PERIOD_S = 1.0
    THREAT_RADIUS_M    = 300.0

    def __init__(self, client: ArtemidesClient) -> None:
        self.client = client
        self._last_tel: dict[str, float] = {}
        self._tel_inflight: dict[str, Future] = {}
        self._threats: dict[str, _Published] = {}
        self._deletes: list[Future] = []

    def on_snapshot(self, snap) -> None:
        cfg = self.client.cfg
        if not cfg.enabled:
            return
        if cfg.telemetry:
            platforms = [(u, u.altitude_m) for u in snap.uavs if u.altitude_m > 1.0] + \
                        [(g, None) for g in snap.ugvs]
            for tel, alt in platforms:
                last = self._last_tel.get(tel.device_id, -1e9)
                inflight = self._tel_inflight.get(tel.device_id)
                # Never queue telemetry behind a request still in flight — a
                # stale position is worthless and would starve threat updates.
                if snap.timestamp - last >= self.TELEMETRY_PERIOD_S and (inflight is None or inflight.done()):
                    self._last_tel[tel.device_id] = snap.timestamp
                    self._tel_inflight[tel.device_id] = self.client.submit(
                        self.client.post_telemetry, tel.device_id,
                        tel.position.lat, tel.position.lon, alt,
                        tel.speed_ms, tel.heading_deg)
        if cfg.publish_threats:
            live = set()
            for trk in snap.tracks:
                if trk.identity != "HOSTILE" or trk.engagement_state == "NEUTRALIZED":
                    continue
                live.add(trk.track_id)
                if trk.track_id not in self._threats:
                    fut = self.client.submit(
                        self.client.create_threat, trk.position.lat, trk.position.lon,
                        self.THREAT_RADIUS_M, f"AMCS {trk.track_id} {trk.object_class}",
                        {"source": "amcs", "track_id": trk.track_id,
                         "class": trk.object_class, "alt_m": trk.altitude_m})
                    self._threats[trk.track_id] = _Published(fut, trk.position.lat, trk.position.lon)
            for tid in [t for t in self._threats if t not in live]:
                self._retract(tid)

    def _retract(self, track_id: str) -> None:
        pub = self._threats.pop(track_id)

        def _delete():
            edit_id = pub.edit_id.result(timeout=_TIMEOUT_S)
            self.client.delete_edit(edit_id)
        self._deletes = [f for f in self._deletes if not f.done()]
        self._deletes.append(self.client.submit(_delete))

    def shutdown(self) -> None:
        """Retract every published marker (waits for those deletes), then stop."""
        for tid in list(self._threats):
            self._retract(tid)
        for fut in self._deletes:
            try:
                fut.result(timeout=2 * _TIMEOUT_S)
            except Exception:
                pass                     # already recorded in client status
        self.client.shutdown(wait=False)
