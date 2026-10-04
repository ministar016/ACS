"""
Laydown — where everything sits on the map, and the unit of a saved scenario.

Editable by the operator (GUI editor) and serialised to JSON:
  • protected asset (base) and restricted-zone radius
  • sensors: acoustic arrays (10 km), surveillance radars (30 km), seismic nodes
  • PVO air-defence sites, GG ground-system sites
  • UGV positions (each UGV's home / deployment point)
  • number of interceptor drones kept at the base

Every placed site is a fixed map position — moving the base does not drag
them along (except the base's own radar).  Threat approaches and the enemy
convoy are stored as (north, east) km offsets from the base, so the attack
always comes at wherever the base is.

PRESEVO_VALLEY is centred on the artemides-trax `vojsrb` deployment: its
segmented terrain covers lat 42.2323–42.31654, lon 21.52359–21.6891, and the
A* router works there (guest/demo routing needs no token).  UGVs are kept
inside `ground_bbox` so every route request lands on segmented terrain.
"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, replace

from . import systems

_M_PER_DEG_LAT = 111_320.0

ACOUSTIC_RANGE_M = 10_000.0      # UAV detection range of an acoustic array
ACOUSTIC_GROUND_RANGE_M = 2_500.0  # vehicle detection range of an acoustic array
SEISMIC_DETECT_M = 8_000.0       # vehicle detection range of a seismic array (5–10 km)
RADAR_RANGE_M    = 30_000.0      # surveillance radar vs. reference drone RCS
ZONE_RADIUS_MIN  = 500.0
ZONE_RADIUS_MAX  = 8_000.0
SCHEMA_VERSION   = 1


def offset(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    return (lat + north_m / _M_PER_DEG_LAT,
            lon + east_m / (_M_PER_DEG_LAT * math.cos(math.radians(lat))))


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * _M_PER_DEG_LAT
    dx = (lon2 - lon1) * _M_PER_DEG_LAT * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


@dataclass(frozen=True)
class Site:
    site_id: str
    lat: float
    lon: float
    label: str = ""
    system: str = ""                  # systems.CATALOG code (radars, GG sites)


@dataclass(frozen=True)
class ThreatSpec:
    target_id:   str
    start_km:    tuple[float, float]  # (north, east) from the base
    heading:     float
    speed_kmh:   float                # hostile drones fly 60–120 km/h
    altitude_m:  float
    spawn_time:  float = 0.0
    homing:      bool  = False        # steer toward the protected asset
    hostile:     bool  = True
    rcs_dbsm:    float = -15.0
    drone_class: str   = "UAV_FIXED_WING"


@dataclass(frozen=True)
class PvoSpec:
    """Air-defence site: autonomous fire at hostile drones in range."""
    site_id:  str
    lat:      float
    lon:      float
    range_m:  float = 5_000.0
    ammo:     int   = 8
    label:    str   = ""
    system:   str   = ""              # systems.CATALOG code; range / ammo follow it

    @classmethod
    def of(cls, site_id: str, lat: float, lon: float, system: str, label: str = "") -> "PvoSpec":
        spec = systems.get(system)
        return cls(site_id, lat, lon, range_m=spec.range_m, ammo=spec.ready + spec.reserve,
                   label=label, system=system)


@dataclass(frozen=True)
class ConvoySpec:
    """
    Enemy combined attack.  Default: trucks / UGVs assemble in the south (the
    North Macedonian border side) and drive north on the road network; the
    air element (attack UAVs + helicopters) launches in the west (Kosovo side),
    flies to the convoy and takes up formation; the convoy moves off once the
    air element is on station (or after `rendezvous_timeout_s`).
    Checked against artemides A*: start → objective is a clean road route for
    both the built-in base and a base moved ~1 km east.
    """
    vehicles:       int   = 4
    start_km:       tuple[float, float] = (-4.5, 2.4)
    via_km:         tuple[tuple[float, float], ...] = ()
    objective_km:   tuple[float, float] = (-0.5, 0.3)
    spawn_time:     float = 0.0           # air element launch
    spacing_s:      float = 25.0          # time gap between vehicles
    air_start_km:   tuple[float, float] | None = (-3.0, -9.5)   # None = air starts at the convoy
    rendezvous_timeout_s: float = 900.0
    escort_drones:  int   = 15            # UAV escort
    aviation:       int   = 2             # attack helicopters
    escort_radius_m: float = 500.0        # flank distance of the escort formation
    release_dist_m: float = 2_500.0       # air element strikes when the lead is this close to the base


@dataclass(frozen=True)
class Laydown:
    name:          str
    base:          Site
    zone_radius_m: float
    zone_buffer_m: float
    ground_bbox:   tuple[float, float, float, float]   # lat_min, lat_max, lon_min, lon_max
    acoustic:      tuple[Site, ...] = ()
    radars:        tuple[Site, ...] = ()
    seismic:       tuple[Site, ...] = ()
    ugvs:          tuple[Site, ...] = ()
    interceptors:  int = 2
    threats:       tuple[ThreatSpec, ...] = ()
    pvo:           tuple[PvoSpec, ...] = ()
    gg:            tuple[Site, ...] = ()
    convoy:        ConvoySpec | None = None
    ugv_charges:   int = 3
    map_zoom:      int = 12
    artemides_url: str | None = None

    # ── derived geometry ──────────────────────────────────────────────────

    def at(self, north_km: float, east_km: float) -> tuple[float, float]:
        return offset(self.base.lat, self.base.lon, north_km * 1000, east_km * 1000)

    @property
    def area_bounds(self) -> tuple[float, float, float, float]:
        """Airspace in which simulated drones live (±~22 km around the base)."""
        return (self.base.lat - 0.2, self.base.lat + 0.2,
                self.base.lon - 0.27, self.base.lon + 0.27)

    def threat_start(self, t: ThreatSpec) -> tuple[float, float]:
        return self.at(*t.start_km)

    def in_ground_bbox(self, lat: float, lon: float) -> bool:
        la0, la1, lo0, lo1 = self.ground_bbox
        return la0 <= lat <= la1 and lo0 <= lon <= lo1

    # ── editing (returns a new Laydown) ───────────────────────────────────

    def with_base(self, lat: float, lon: float) -> "Laydown":
        # The base radar moves with the base; other radars stay put.
        radars = tuple(replace(r, lat=lat, lon=lon) if r.site_id == "RAD-SITE-01" else r
                       for r in self.radars)
        return replace(self, base=replace(self.base, lat=lat, lon=lon), radars=radars)

    def with_zone_radius(self, radius_m: float) -> "Laydown":
        return replace(self, zone_radius_m=min(ZONE_RADIUS_MAX, max(ZONE_RADIUS_MIN, radius_m)))

    def add_site(self, kind: str, lat: float, lon: float,
                 system: str | None = None) -> tuple["Laydown", Site | PvoSpec]:
        prefix, label_fmt = _KIND_NAMING[kind]
        field_name = _KIND_FIELD[kind]
        existing = {x.site_id for x in getattr(self, field_name)}
        n = 1
        while f"{prefix}-{n:02d}" in existing:
            n += 1
        sid = f"{prefix}-{n:02d}"
        label = label_fmt.format(n=n, sid=sid)
        system = system if systems.get(system) else systems.DEFAULT_SYSTEM.get(kind, "")
        site = (PvoSpec.of(sid, lat, lon, system, label) if kind == "pvo"
                else Site(sid, lat, lon, label, system))
        return replace(self, **{field_name: getattr(self, field_name) + (site,)}), site

    def nearest(self, lat: float, lon: float, max_m: float = 600.0,
                kinds=None) -> tuple[str | None, Site | PvoSpec | None]:
        """(kind, site) of the closest placed item within max_m — 'base' included."""
        kinds = kinds or ("base",) + tuple(_KIND_FIELD)
        best, best_kind, best_d = None, None, max_m
        for kind in kinds:
            items = (self.base,) if kind == "base" else getattr(self, _KIND_FIELD[kind])
            for x in items:
                d = distance_m(lat, lon, x.lat, x.lon)
                if d < best_d:
                    best, best_kind, best_d = x, kind, d
        return best_kind, best

    def move_site(self, kind: str, site_id: str, lat: float, lon: float) -> "Laydown":
        if kind == "base":
            return self.with_base(lat, lon)
        field_name = _KIND_FIELD[kind]
        return replace(self, **{field_name: tuple(
            replace(x, lat=lat, lon=lon) if x.site_id == site_id else x
            for x in getattr(self, field_name))})

    def remove_nearest(self, lat: float, lon: float, max_m: float = 600.0,
                       kinds=None) -> tuple["Laydown", Site | PvoSpec | None]:
        kind, best = self.nearest(lat, lon, max_m, kinds or tuple(_KIND_FIELD))
        if best is None:
            return self, None
        field_name = _KIND_FIELD[kind]
        return replace(self, **{field_name: tuple(x for x in getattr(self, field_name) if x is not best)}), best

    # ── serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """GUI view of the laydown."""
        def sites(ss, **extra):
            return [dict(id=s.site_id, lat=s.lat, lon=s.lon, label=s.label or s.site_id,
                         system=s.system, systemName=_sys_name(s.system), **extra) for s in ss]

        def pvo_sites():
            return [dict(id=p.site_id, lat=p.lat, lon=p.lon, label=p.label or p.site_id,
                         rangeM=p.range_m, ammo=p.ammo, armed=True, system=p.system,
                         systemName=_sys_name(p.system)) for p in self.pvo]

        lat_min, lat_max, lon_min, lon_max = self.ground_bbox
        return {
            "name":       self.name,
            "base":       {"id": self.base.site_id, "lat": self.base.lat, "lon": self.base.lon},
            "zoneRadiusM": self.zone_radius_m,
            "mapCenter":  {"lat": self.base.lat, "lon": self.base.lon, "zoom": self.map_zoom},
            "acoustic":   sites(self.acoustic, rangeM=ACOUSTIC_RANGE_M, groundRangeM=ACOUSTIC_GROUND_RANGE_M),
            "radars":     [dict(r, rangeM=radar_range_m(r["system"])) for r in sites(self.radars)],
            "seismic":    sites(self.seismic, rangeM=SEISMIC_DETECT_M),
            "ugvs":       sites(self.ugvs),
            "interceptors": self.interceptors,
            "pvo":        pvo_sites(),
            "gg":         [dict(g, armed=True, rangeM=(systems.get(g["system"]).range_m
                                                       if systems.get(g["system"]) else 0))
                           for g in sites(self.gg)],
            "ugvCharges": self.ugv_charges,
            "convoy":     None if self.convoy is None else {
                "vehicles": self.convoy.vehicles, "escortDrones": self.convoy.escort_drones,
                "aviation": self.convoy.aviation},
            "groundBbox": {"latMin": lat_min, "latMax": lat_max, "lonMin": lon_min, "lonMax": lon_max},
        }

    def to_json(self) -> str:
        def sites(ss):
            return [dict({"id": s.site_id, "lat": s.lat, "lon": s.lon, "label": s.label},
                         **({"system": s.system} if s.system else {})) for s in ss]
        doc = {
            "schema": SCHEMA_VERSION,
            "name": self.name,
            "base": {"id": self.base.site_id, "lat": self.base.lat, "lon": self.base.lon},
            "zone": {"radius_m": self.zone_radius_m, "buffer_m": self.zone_buffer_m},
            "ground_bbox": list(self.ground_bbox),
            "acoustic": sites(self.acoustic),
            "radars": sites(self.radars),
            "seismic": sites(self.seismic),
            "ugvs": sites(self.ugvs),
            "interceptors": self.interceptors,
            "threats": [{
                "id": t.target_id, "start_km": list(t.start_km), "heading": t.heading,
                "speed_kmh": t.speed_kmh, "altitude_m": t.altitude_m, "spawn_time": t.spawn_time,
                "homing": t.homing, "hostile": t.hostile, "rcs_dbsm": t.rcs_dbsm,
                "class": t.drone_class,
            } for t in self.threats],
            "pvo": [{"id": p.site_id, "lat": p.lat, "lon": p.lon, "label": p.label,
                     "range_m": p.range_m, "ammo": p.ammo, "system": p.system} for p in self.pvo],
            "gg": sites(self.gg),
            "convoy": None if self.convoy is None else {
                "vehicles": self.convoy.vehicles, "start_km": list(self.convoy.start_km),
                "via_km": [list(v) for v in self.convoy.via_km],
                "objective_km": list(self.convoy.objective_km),
                "spawn_time": self.convoy.spawn_time, "spacing_s": self.convoy.spacing_s,
                "air_start_km": list(self.convoy.air_start_km) if self.convoy.air_start_km else None,
                "rendezvous_timeout_s": self.convoy.rendezvous_timeout_s,
                "escort_drones": self.convoy.escort_drones,
                "aviation": self.convoy.aviation,
                "escort_radius_m": self.convoy.escort_radius_m,
                "release_dist_m": self.convoy.release_dist_m},
            "ugv_charges": self.ugv_charges,
            "map_zoom": self.map_zoom,
            "artemides_url": self.artemides_url,
        }
        return json.dumps(doc, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Laydown":
        d = json.loads(text)
        if d.get("schema") != SCHEMA_VERSION:
            raise ValueError(f"unsupported scenario schema {d.get('schema')!r}")

        def sites(items, kind=None):
            # Files saved before the systems catalog: radars / GG get the default system
            dflt = systems.DEFAULT_SYSTEM.get(kind, "")
            return tuple(Site(s["id"], float(s["lat"]), float(s["lon"]), s.get("label", ""),
                              s.get("system") or dflt) for s in items)
        b = d["base"]

        def rel(n_km, e_km):             # legacy files stored PVO / GG as base offsets
            return offset(float(b["lat"]), float(b["lon"]), float(n_km) * 1000, float(e_km) * 1000)

        def pvo(p):
            lat, lon = (p["lat"], p["lon"]) if "lat" in p else rel(p["north_km"], p["east_km"])
            if p.get("system") and systems.get(p["system"]):
                return PvoSpec(p["id"], float(lat), float(lon), float(p.get("range_m", 5000)),
                               int(p.get("ammo", 8)), p.get("label", ""), p["system"])
            return PvoSpec.of(p["id"], float(lat), float(lon),
                              legacy_pvo_system(float(p.get("range_m", 5000))), p.get("label", ""))
        return cls(
            name=d["name"],
            base=Site(b["id"], float(b["lat"]), float(b["lon"])),
            zone_radius_m=float(d["zone"]["radius_m"]),
            zone_buffer_m=float(d["zone"]["buffer_m"]),
            ground_bbox=tuple(float(x) for x in d["ground_bbox"]),
            acoustic=sites(d.get("acoustic", [])),
            radars=sites(d.get("radars", []), "radar"),
            seismic=sites(d.get("seismic", [])),
            ugvs=sites(d.get("ugvs", [])),
            interceptors=int(d.get("interceptors", 2)),
            threats=tuple(ThreatSpec(
                t["id"], tuple(t["start_km"]), float(t["heading"]), float(t["speed_kmh"]),
                float(t["altitude_m"]), float(t.get("spawn_time", 0)), bool(t.get("homing", False)),
                bool(t.get("hostile", True)), float(t.get("rcs_dbsm", -15)), t.get("class", "UAV_FIXED_WING"),
            ) for t in d.get("threats", [])),
            pvo=tuple(pvo(p) for p in d.get("pvo", [])) or
                tuple(PvoSpec.of(p[0], *rel(p[1], p[2]), legacy_pvo_system(5_000.0))
                      for p in d.get("pvo_km", [])),
            gg=sites(d.get("gg", []), "gg") or
               tuple(Site(g[0], *rel(g[1], g[2]), g[0], systems.DEFAULT_SYSTEM["gg"])
                     for g in d.get("gg_km", [])),
            # Files saved before the convoy existed have no "convoy" key: give them
            # the default attack.  An explicit null means "no convoy".
            convoy=(ConvoySpec() if "convoy" not in d else None) if not d.get("convoy") else ConvoySpec(
                vehicles=int(d["convoy"]["vehicles"]),
                start_km=tuple(d["convoy"]["start_km"]),
                via_km=tuple(tuple(v) for v in d["convoy"].get("via_km", [])),
                objective_km=tuple(d["convoy"]["objective_km"]),
                spawn_time=float(d["convoy"].get("spawn_time", 30)),
                spacing_s=float(d["convoy"].get("spacing_s", 25)),
                air_start_km=tuple(d["convoy"]["air_start_km"]) if d["convoy"].get("air_start_km") else None,
                rendezvous_timeout_s=float(d["convoy"].get("rendezvous_timeout_s", 900)),
                escort_drones=int(d["convoy"].get("escort_drones", 15)),
                aviation=int(d["convoy"].get("aviation", 2)),
                escort_radius_m=float(d["convoy"].get("escort_radius_m", 500)),
                release_dist_m=float(d["convoy"].get("release_dist_m", 2500))),
            ugv_charges=int(d.get("ugv_charges", 3)),
            map_zoom=int(d.get("map_zoom", 12)),
            artemides_url=d.get("artemides_url"),
        )


_KIND_FIELD = {"ugv": "ugvs", "acoustic": "acoustic", "radar": "radars",
               "seismic": "seismic", "pvo": "pvo", "gg": "gg"}
_KIND_NAMING = {                      # id prefix, label format
    "ugv":      ("UGV", "{sid}"),
    "acoustic": ("ACO-FIELD", "ACO-{n}"),
    "radar":    ("RAD", "RAD-{n}"),
    "seismic":  ("SEI-FIELD", "SEI-{n}"),
    "pvo":      ("PVO", "{sid}"),
    "gg":       ("GG", "{sid}"),
}


def _sys_name(code: str) -> str:
    spec = systems.get(code)
    return spec.name if spec else ""


def radar_range_m(code: str) -> float:
    """Ring drawn for a radar site: its range against the reference drone (−15 dBsm)."""
    spec = systems.get(code)
    if spec is None or not spec.radar_ref_m:
        return RADAR_RANGE_M
    r = spec.radar_ref_m * 10.0 ** ((-15.0 - spec.radar_ref_dbsm) / 40.0)
    return min(r, spec.detect_m or r)


def legacy_pvo_system(range_m: float) -> str:
    """Generic PVO sites of older files → the real system with that envelope."""
    return "PASARS_16" if range_m >= 7_000 else "STRELA_10M3"


def _presevo_valley() -> Laydown:
    b = (42.27442, 21.606345)            # vojsrb demo focus point

    def pos(n_km, e_km):
        return offset(b[0], b[1], n_km * 1000, e_km * 1000)

    def site(sid, n_km, e_km, label=""):
        return Site(sid, *pos(n_km, e_km), label)

    return Laydown(
        name="PREŠEVO VALLEY",
        base=Site("BASE-01", *b),
        zone_radius_m=2_200.0,
        zone_buffer_m=1_500.0,
        ground_bbox=(42.2323, 42.31654, 21.52359, 21.6891),
        acoustic=(
            site("ACO-FIELD-01", 1.10, -5.20, "ACO-W"),
            site("ACO-FIELD-02", 0.90, -0.60, "ACO-C"),
            site("ACO-FIELD-03", -1.40, 5.00, "ACO-E"),
        ),
        radars=(Site("RAD-SITE-01", *pos(0.0, 0.0), "RAD-BASE", "RPS42"),),
        seismic=(
            site("SEI-FIELD-01", -0.40, -3.00, "SEI-W"),
            site("SEI-FIELD-02", -2.10, 0.30, "SEI-C"),
            site("SEI-FIELD-03", 1.20, 3.60, "SEI-E"),
        ),
        ugvs=(site("UGV-BRAVO-02", -0.78, -0.41, "UGV-BRAVO"),),
        interceptors=2,
        threats=(
            # Fixed-wing from the west, crossing the zone north of the asset
            ThreatSpec("HOSTILE-A", (1.55, -9.00), heading=100.0, speed_kmh=120.0,
                       altitude_m=100.0, rcs_dbsm=-15.0, drone_class="UAV_FIXED_WING"),
            # Quadcopter from the south-east, homing on the asset
            ThreatSpec("HOSTILE-B", (-5.10, 4.90), heading=315.0, speed_kmh=80.0,
                       altitude_m=60.0, spawn_time=60.0, homing=True,
                       rcs_dbsm=-20.0, drone_class="UAV_QUADCOPTER"),
            # Neutral transit north of the base (away from the southern attack axis) — never engaged
            ThreatSpec("CIVIL-C", (4.70, -13.10), heading=88.0, speed_kmh=105.0,
                       altitude_m=150.0, spawn_time=20.0, hostile=False,
                       rcs_dbsm=-10.0, drone_class="UAV_FIXED_WING"),
        ),
        pvo=(
            # ALPHA: Strela-10M3 (5 km), BETA: PASARS-16 (40 mm gun 4 km + Mistral 3 8 km)
            PvoSpec.of("PVO-ALPHA-01", *pos(2.60, -3.60), "STRELA_10M3"),
            PvoSpec.of("PVO-ALPHA-02", *pos(2.50, 3.60), "STRELA_10M3"),
            PvoSpec.of("PVO-BETA-03", *pos(-2.60, -3.50), "PASARS_16"),
            PvoSpec.of("PVO-BETA-04", *pos(-2.70, 3.50), "PASARS_16"),
        ),
        # GG: ALAS surface-to-surface launchers covering the southern approach
        gg=(Site("GG-ZETA-01", *pos(-3.30, -2.50), "", "ALAS"),
            Site("GG-ZETA-02", *pos(-3.40, 0.00), "", "ALAS"),
            Site("GG-ZETA-03", *pos(-3.10, 2.50), "", "ALAS")),
        # 4 vehicles from the west on the road network (artemides A*: start →
        # via → objective is a clean route west of the river), 15 escort drones
        convoy=ConvoySpec(),
        ugv_charges=3,
        artemides_url="https://vojsrb.artemides-trax.com",
    )


PRESEVO_VALLEY = _presevo_valley()
DEFAULT_LAYDOWN = PRESEVO_VALLEY
