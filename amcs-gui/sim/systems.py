"""
Systems catalog — real air-defence, surveillance and counter-UAS systems the
simulation can place, with their published (open-source) performance.

Every entry carries `source`.  Figures the open literature does not give —
kill probability against a small drone, engagement cycle, radar range against
a −15/−20 dBsm drone for radars only specified against aircraft — are model
assumptions and listed in `assumed`, so nobody mistakes them for data.

Roles
─────
  SAM / SHORAD   surface-to-air missile fire unit       → PVO sites
  SPAAG          gun + missile vehicle                  → PVO sites
  RADAR          surveillance radar                     → radar sites
  SSM            surface-to-surface (anti-armour) missile → GG sites
  CUAS_EW        RF / GNSS jammer                       → UGV payload

Kill resolution (sim/scenario.py): a missile flies reaction_s + range /
missile_speed_ms, then kills the target it was fired at with probability
pk if that target is still alive and within the envelope.  Guns fire bursts
at gun_pk inside gun_range_m and are preferred for close drones, which saves
missiles — the doctrine of every gun-missile system.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class SystemSpec:
    code:      str
    name:      str
    role:      str                   # SAM | SHORAD | SPAAG | RADAR | SSM | CUAS_EW
    origin:    str
    serbia:    str                   # service status in the Serbian Armed Forces
    # Engagement envelope (missiles)
    range_m:     float = 0.0
    min_range_m: float = 0.0
    max_alt_m:   float = 0.0
    min_alt_m:   float = 0.0
    ready:       int   = 0           # ready rounds on the launcher
    reserve:     int   = 0           # reloads carried / at the site
    reload_s:    float = 0.0         # time to reload the launcher from reserve
    reaction_s:  float = 0.0         # detection-to-launch
    cycle_s:     float = 0.0         # minimum time between two engagements
    missile_speed_ms: float = 0.0
    pk:          float = 0.0         # single-shot kill probability vs a small UAV / target class
    channels:    int   = 1           # targets engaged simultaneously
    targets:     str   = "AIR"       # AIR | GROUND
    # Gun (SPAAG / Pantsir)
    gun_range_m: float = 0.0
    gun_bursts:  int   = 0
    gun_pk:      float = 0.0
    gun_cycle_s: float = 0.0
    # Sensors
    detect_m:    float = 0.0         # own search radar / instrumented range
    radar_ref_m: float = 0.0         # detection range against radar_ref_dbsm
    radar_ref_dbsm: float = -15.0
    revisit_s:   float = 1.0
    ground_range_m: float = 0.0      # GMTI (ground moving target) range
    # EW
    jam_range_m: float = 0.0
    jam_bands:   str   = ""
    assumed:     tuple[str, ...] = ()
    source:      tuple[str, ...] = ()
    notes:       str   = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["assumed"], d["source"] = list(self.assumed), list(self.source)
        return d


_WIKI = "https://en.wikipedia.org/wiki/"

CATALOG: dict[str, SystemSpec] = {s.code: s for s in (
    # ── PVO: surface-to-air ───────────────────────────────────────────────
    SystemSpec(
        "STRELA_10M3", "9K35 Strela-10M3", "SHORAD", "USSR/Russia",
        "in service, 18 systems (Military Balance)",
        range_m=5_000, min_range_m=800, max_alt_m=3_500, min_alt_m=10,
        ready=4, reserve=8, reload_s=180, reaction_s=8, cycle_s=10,
        missile_speed_ms=550, pk=0.5, detect_m=0,
        assumed=("pk vs small UAV (IR seeker, weak drone signature)", "reload_s", "reaction_s", "cycle_s"),
        source=(_WIKI + "Strela-10",),
        notes="IR-homing; range 0.8–5 km, altitude 10–3500 m, 4 ready + 8 reloads in the vehicle"),
    SystemSpec(
        "MISTRAL_3", "MBDA Mistral 3 (firing post)", "SHORAD", "France",
        "ordered 2019, in service",
        range_m=8_000, min_range_m=500, max_alt_m=6_000, min_alt_m=5,
        ready=1, reserve=5, reload_s=60, reaction_s=6, cycle_s=8,
        missile_speed_ms=930, pk=0.7,
        assumed=("pk vs small UAV", "min_range_m", "reserve/reload_s per firing post", "reaction_s", "cycle_s"),
        source=(_WIKI + "Mistral_(missile)",),
        notes="IR imaging seeker; 8 km, ceiling 6 km, Mach 2.7"),
    SystemSpec(
        "PASARS_16", "PASARS-16 (Bofors 40 mm + Mistral 3)", "SPAAG", "Serbia",
        "in service, 5 batteries",
        range_m=8_000, min_range_m=500, max_alt_m=6_000, min_alt_m=5,
        ready=4, reserve=4, reload_s=240, reaction_s=6, cycle_s=8,
        missile_speed_ms=930, pk=0.7,
        gun_range_m=4_000, gun_bursts=40, gun_pk=0.3, gun_cycle_s=4,
        detect_m=10_000, radar_ref_m=10_000, radar_ref_dbsm=-20,
        assumed=("pk / gun_pk vs small UAV", "reserve", "reload_s", "reaction_s", "cycle_s",
                 "gun bursts carried"),
        source=(_WIKI + "PASARS-16", _WIKI + "Mistral_(missile)"),
        notes="40 mm/70 gun 4 km, 2–4 Mistral 3; cued by RPS-42 or modernised M85 Žirafa"),
    SystemSpec(
        "PANTSIR_S1", "Pantsir-S1", "SPAAG", "Russia",
        "in service, 1 battery S1 + 2 batteries S1-M (18 vehicles)",
        range_m=20_000, min_range_m=1_200, max_alt_m=15_000, min_alt_m=5,
        ready=12, reserve=0, reload_s=0, reaction_s=5, cycle_s=4,
        missile_speed_ms=1_000, pk=0.75, channels=2,
        gun_range_m=4_000, gun_bursts=60, gun_pk=0.35, gun_cycle_s=3,
        detect_m=36_000, radar_ref_m=28_000, radar_ref_dbsm=3.0,
        assumed=("pk / gun_pk vs small UAV", "min_range_m", "cycle_s", "channels",
                 "mean missile speed (1300 m/s at burnout, 780 m/s at 18 km)"),
        source=(_WIKI + "Pantsir_missile_system",),
        notes="20 km / 15 km altitude, 12 ready missiles, reaction 4–6 s, 30 mm guns 4 km, "
              "search radar 32–36 km, tracking radar 24–28 km vs 2 m²"),
    SystemSpec(
        "HQ17AE", "HQ-17AE", "SAM", "China",
        "in service since 2024",
        range_m=15_000, min_range_m=1_500, max_alt_m=10_000, min_alt_m=10,
        ready=8, reserve=0, reload_s=0, reaction_s=8, cycle_s=5,
        missile_speed_ms=850, pk=0.8, channels=2,
        detect_m=45_000, radar_ref_m=45_000, radar_ref_dbsm=0.0,
        assumed=("pk vs small UAV", "reaction_s", "cycle_s", "missile speed", "radar reference RCS"),
        source=(_WIKI + "HQ-17",),
        notes="1.5–15 km, 10 m–10 km altitude, 8 missiles, tracks 24 / engages 2 targets, search radar 45 km"),
    SystemSpec(
        "FK3", "FK-3 (HQ-22 export)", "SAM", "China",
        "in service since April 2022",
        range_m=100_000, min_range_m=5_000, max_alt_m=27_000, min_alt_m=50,
        ready=4, reserve=0, reload_s=0, reaction_s=15, cycle_s=10,
        missile_speed_ms=1_400, pk=0.8, channels=6,
        detect_m=150_000, radar_ref_m=150_000, radar_ref_dbsm=3.0,
        assumed=("min_range_m", "altitude envelope", "reaction_s", "cycle_s", "missile speed",
                 "pk vs small UAV", "radar range"),
        source=(_WIKI + "HQ-22",),
        notes="100 km, 4 missiles per TEL, 6 targets engaged simultaneously — a strategic SAM, "
              "uneconomical against cheap drones"),
    # ── surveillance radars ───────────────────────────────────────────────
    SystemSpec(
        "RPS42", "RADA RPS-42 (MHR)", "RADAR", "Israel",
        "in service (cues PASARS-16, part of Kobac-1PR)",
        detect_m=30_000, radar_ref_m=10_000, radar_ref_dbsm=-20, revisit_s=1.0,
        ground_range_m=10_000,
        assumed=("revisit_s (AESA, non-rotating)", "ground_range_m"),
        source=("https://www.academia.edu/35239235/RPS-42_Radar_System_for_Tactical_Air_Surveillance_RADA_Innovative_Defense_Electronics",
                "https://breakingdefense.com/2022/10/why-countering-small-uas-and-swarms-demands-highly-capable-radars/"),
        notes="AESA hemispheric, up to 30 km for aerial targets, micro/mini UAS (groups 1–2) up to 10 km"),
    SystemSpec(
        "GIRAFFE_AMB", "Saab Giraffe AMB", "RADAR", "Sweden",
        "not in Serbian service",
        detect_m=100_000, radar_ref_m=20_000, radar_ref_dbsm=-15, revisit_s=1.0,
        ground_range_m=15_000,
        assumed=("range vs −15 dBsm drone", "ground_range_m"),
        source=(_WIKI + "Giraffe_radar",),
        notes="instrumented 30/60/100 km, 0–20 km altitude, 70° elevation, 1 scan per second"),
    SystemSpec(
        "GM403", "Thales Ground Master 400α", "RADAR", "France",
        "in service, 3 GM400α",
        detect_m=470_000, radar_ref_m=35_000, radar_ref_dbsm=-15, revisit_s=6.0,
        ground_range_m=0,
        assumed=("range vs −15 dBsm drone (only aircraft figures published)",),
        source=(_WIKI + "Ground_Master_400",),
        notes="S-band long-range, 470 km instrumented, 30.5 km altitude, 10 rpm (6 s revisit)"),
    # ── surface-to-surface (GG sites) ─────────────────────────────────────
    SystemSpec(
        "ALAS", "ALAS (fibre-optic guided missile)", "SSM", "Serbia",
        "in service, 60 missiles (2025)",
        range_m=25_000, min_range_m=1_000, ready=6, reserve=0, reaction_s=30, cycle_s=40,
        missile_speed_ms=140, pk=0.8, targets="GROUND",
        assumed=("pk vs truck (operator-guided)", "ready rounds per launcher (4–8 published)",
                 "reaction_s", "cycle_s"),
        source=(_WIKI + "ALAS_(missile)",),
        notes="25 km, 130–150 m/s cruise, 10.5 kg warhead, operator-guided over fibre"),
    # ── counter-UAS EW ────────────────────────────────────────────────────
    SystemSpec(
        "YUGOIMPORT_JAMMER", "Yugoimport anti-drone jammer", "CUAS_EW", "Serbia",
        "in production",
        jam_range_m=2_000,
        jam_bands="400–470, 800–1227, 1164–1610, 2200–2500, 3400–3800, 4900–5900 MHz",
        source=("https://www.yugoimport.com/sites/default/files/documents/2023-12/Anti-drone%20jammer.pdf",),
        notes="RC-link and GNSS jamming, up to 2 km"),
    SystemSpec(
        "KOBAC_1PR", "Kobac-1PR counter-UAS", "CUAS_EW", "Serbia",
        "shown at Partner 2025",
        jam_range_m=4_000, detect_m=4_000,
        jam_bands="400–6000 MHz, six bands, ~50 W per module",
        source=("https://www.armyrecognition.com/news/army-news/2025/serbia-counters-drones-with-ai-jamming-thanks-to-new-kobac-1pr-system",),
        notes="MHR radar + RF reconnaissance + jammer, automatic detection to neutralisation in 4 km"),
)}

# Which catalog roles each placeable site kind accepts, and its default system
SITE_ROLES = {
    "pvo":   ("SAM", "SHORAD", "SPAAG"),
    "radar": ("RADAR",),
    "gg":    ("SSM",),
}
DEFAULT_SYSTEM = {"pvo": "STRELA_10M3", "radar": "RPS42", "gg": "ALAS"}


def get(code: str | None) -> SystemSpec | None:
    return CATALOG.get(code or "")


def for_kind(kind: str) -> list[SystemSpec]:
    roles = SITE_ROLES.get(kind, ())
    return [s for s in CATALOG.values() if s.role in roles]


def catalog_view() -> dict:
    """GUI view: systems per placeable kind plus the full records."""
    return {
        "byKind": {k: [{"code": s.code, "name": s.name, "rangeM": s.range_m or s.detect_m}
                       for s in for_kind(k)] for k in SITE_ROLES},
        "defaults": dict(DEFAULT_SYSTEM),
        "systems": {c: s.to_dict() for c, s in CATALOG.items()},
    }
