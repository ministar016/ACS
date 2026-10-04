# AMCS — Counter-UAS Command & Control

End-to-end system for detecting, tracking and intercepting drones that enter a
restricted zone, with a live QML operator dashboard and a link to the
[artemides-trax](https://github.com/ministar016/artemides-trax) terrain/routing platform.

```
 targets ─▶ SENSE ─▶ TRACK ─▶ IDENTIFY ─▶ DECIDE ─▶ ENGAGE ─▶ ASSESS
           radar     Kalman    geofence    operator   UAV intercept   BDA
           acoustic  GNN+IFF   threat      / auto-ROE UGV RF jammer
           EO camera           rules       WTA        │
                                                      └─ UGV ground route ◀── artemides-trax A*
```

## Running

```bash
./run.sh                                   # dashboard (needs .venv with PyQt6: pip install -r requirements.txt)
.venv/bin/python -m unittest discover -s tests -v   # 34 tests, ~2 min
```

Dashboard controls (bottom bar / engagement cards):

| Control | Effect |
|---|---|
| **ENGAGE** | approve the most urgent proposed engagement (or per-card ✔ ENGAGE) |
| **DENY** | reject a proposal — that track is not proposed again |
| **AUTO-ROE** | weapons free *inside the zone*: auto-approves only tracks already in the zone or ≤ 30 s from entry |
| **ABORT ALL** | abort every running engagement, effectors return |
| **▲ LAUNCH / ▼ RECALL** (interceptor card) | call an interceptor up to patrol over the base / send it home |
| **PVO: AUTO / HOLD** | PVO sites weapons free on hostile drones, or hold fire |
| **DRIVE** (map header) | UGV drivability layer from artemides-trax, with speed legend |
| **TRUTH** (map header) | ground-truth overlay incl. the enemy convoy's planned route (debug — never used by the C2 chain) |
| **✎ EDIT** | scenario editor (sim paused at T+0) — see below |
| 1×…50× | simulation speed |

### Scenario editor

**✎ EDIT** pauses the simulation at T+0 and opens the editor toolbar over the map. Pick a
tool and click on the map:

| Tool | Effect |
|---|---|
| ✥ MOVE | click any item (base, UGV, PVO, GG, radar, acoustic, seismic) to pick it, then click its new position |
| ◆ BASE | move the protected asset; zone, base radar, threat approaches and the enemy convoy follow it |
| ▣ UGV | place a UGV — refused outside the artemides terrain area and on NO-GO terrain (the DRIVE layer is shown automatically); the same check applies when moving one |
| ◈ PVO | place a PVO site (5 km, 8 rounds) — live immediately |
| ▼ GG | place a GG ground-system site |
| ▲ RADAR | place a surveillance radar (30 km air / 12 km ground) |
| ◉ ACOUSTIC | place an acoustic array (10 km UAV detection; ring shown in edit mode) |
| ≈ SEISMIC | place a seismic node (ground targets, ~800 m) |
| ✘ DELETE | remove the nearest item within 600 m |

All placed items are fixed map positions (moving the base does not drag PVO / GG /
sensors along). Zone radius (±250 m) and the number of interceptors at the base are set in
the toolbar. **SAVE** writes `scenarios/<name>.json` and makes it the **startup scenario**
(`scenarios/.last_saved`); **LOAD** restores any saved scenario or the built-in Preševo
laydown; **▶ RUN** restarts the simulation with the edited laydown. Files saved by older
versions (PVO / GG as base offsets) are converted on load.

### Map: bearing detections

Acoustic and seismic arrays only measure a direction.  Every detection is drawn as a faint
15° sector fading with range (acoustic: 10 km for aircraft, 3 km for vehicles; seismic 10 km);
sectors of the same sensor that touch are merged, so a sensor hearing a whole swarm adds a
single translucent layer.  A lone sensor is barely visible — the target stands out only
where the sectors of several sensors overlap.  In edit mode the rings show acoustic 10 km
(air) / 2.5 km (ground) and seismic ~8 km coverage.

### Platforms and sensors

| | |
|---|---|
| Surveillance radar | 30 km vs. −15 dBsm drone (range scales with RCS^¼), ground (GMTI) 12 km, one plot per 1 s rotation |
| Acoustic array | 10 km vs. drones, 2–3 km vs. vehicles, bearing only (~3° σ at max range), 1 s |
| Seismic array | ground vehicles 5–10 km (≈ 8 km typical), bearing (~8° σ at max range), 1 s; bearings feed the tracker for ground tracks only; aircraft are never seen |
| Hostile drones | 60–120 km/h |
| Interceptor UAV | idle on the pad at the base and **invisible until airborne**; launches (5 s) on an approved engagement or an operator call, dashes at ~200 km/h, returns and lands after the engagement |
| UGV | 15–80 km/h depending on the ground under it (DRIVE classes below); drives **only on routes from artemides A\*** — if no drivable route is found it holds (`NO ROUTE`) instead of cutting across terrain. Directional RF jammer (2 km, stops drones and enemy UGVs) + **3 charges** (3 km vs. vehicles P_hit 0.8, 2 km vs. drones P_hit 0.6, 8 s reload) |
| PVO site | autonomous, weapons free on declared-HOSTILE drones in range; **one shot per minute** per site, destroys the drone; ALPHA 5 km / 8 rounds, BETA 8 km / 4 rounds |
| Enemy UGV | follows its road route at the drivability speed (40 km/h without data); seen by radar GMTI (12 km), acoustic (~4 km), seismic, cameras; ground tracks never mix with air tracks |

### UGV drivability layer

Built from artemides-trax `api/traversability.php` (satellite segmentation + driven telemetry
+ route blocks + manual edits), tiled over the artemides terrain area, cached in
`~/.cache/amcs/` and drawn as an overlay:

| Class | Cell cost | UGV speed |
|---|---|---|
| ROAD | ≤ 0.12 | 80 km/h |
| TRACK | ≤ 0.20 | 50 km/h |
| OPEN | ≤ 0.35 | 35 km/h |
| ROUGH | ≤ 0.50 | 25 km/h |
| DIFFICULT | ≤ 0.70 | 15 km/h |
| NO-GO | > 0.70 | impassable |
| (no data) | — | 20 km/h |

`traversability.php` requires a logged-in user: create a token on the deployment
(`account.php` → *Novi token*) and start with `ARTEMIDES_TOKEN=... ./run.sh`. Without it the
layer shows *unavailable (401)*, routing still works as a guest, and UGV speed uses the
no-data value.

## macOS app

A Mac app cannot be built on Linux, so it is built on GitHub's macOS runners:
`.github/workflows/amcs-macos.yml` runs the tests, builds **AMCS.app**, smoke-tests it and
publishes **`AMCS-<version>-macOS-<arch>.dmg`** (Apple Silicon `arm64`, plus Intel `x86_64`
when that runner is available):

* every push to `main` touching `amcs-gui/` → DMG under the run's *Artifacts*;
* a tag `amcs-v1.0.0` → DMG attached to a GitHub release.

On a Mac you can also build locally: `cd amcs-gui && bash packaging/build_macos.sh`
(PyInstaller spec `packaging/amcs.spec`, icon from `packaging/make_icon.py`, version in
`packaging/VERSION`).

Installing: open the DMG, drag **AMCS** to *Applications*. The app is ad-hoc signed, not
notarised — on first launch right-click → **Open** (or
`xattr -dr com.apple.quarantine /Applications/AMCS.app`).

The packaged app keeps its files in per-user folders (the bundle is read-only):

| | |
|---|---|
| scenarios | `~/Library/Application Support/AMCS/scenarios` (seeded from the bundle on first start) |
| settings | `~/Library/Application Support/AMCS/config.env` — e.g. `ARTEMIDES_TOKEN=…` (a Finder-launched app gets no shell environment) |
| drivability cache | `~/Library/Caches/AMCS` |
| log | `~/Library/Logs/AMCS/amcs.log` |

## Architecture (`sim/`)

| Module | Role |
|---|---|
| `zone.py` | Restricted zone polygon + warning buffer, local ENU frame, time-to-entry, CPA to asset |
| `target.py` | Aerial targets: transit / homing profiles, states FLYING → JAMMED → LANDED, DESTROYED, EXITED |
| `sensors/` | Radar (RCS-scaled range, elevation), acoustic bearings, EO camera classification, seismic (ground only) |
| `tracker.py` | Multi-target Kalman filter (CV model), radar position + EKF bearing updates, acoustic triangulation for initiation, per-sensor GNN association, M-of-N confirmation, IFF suppression of own platforms |
| `threat.py` | Rules → level / identity (HOSTILE, SUSPECT, NEUTRAL) / priority; hostile is sticky; air tracks staying ≥ 60 s within 2 km of a hostile ground track are declared hostile (escort rule — a passing civil aircraft is not); classified attack helicopters jump the queue |
| `engagement.py` | Kill-chain state machine, human-in-the-loop approval, weapon–target assignment, guidance hand-off, BDA |
| `guidance.py` | Predicted-intercept-point solver (collision course), turn-rate-limited steering |
| `devices/uav.py` | Interceptor: IDLE → LAUNCHING → INTERCEPT / PATROL → RTB → LANDING; PIP guidance on the *track estimate*; hard kill, P_k 0.85, 12 m |
| `devices/ugv.py` | Mobile RF jammer: 2 km, 60° beam, 3 s dwell; terrain-dependent speed; drives only on routed waypoints |
| `laydown.py` | Where everything sits: asset, zone, sensors, UGVs, interceptor count, threat approaches; editing + JSON save/load |
| `drivability.py` | Traversability grid → drivability classes, UGV speed, nearest drivable point, PNG overlay |
| `scenario.py` | Wires everything together from a laydown |
| `bus.py` | Qt bridge to QML: signals out, operator slots in |

Engagement states: `PROPOSED → APPROVED → ENGAGING → NEUTRALIZED`, plus `DENIED`, `ABORTED`, `LOST`.

Default laydown: **Preševo Valley**, centred on the segmented terrain of the
artemides-trax `vojsrb` deployment (lat 42.2323–42.3165, lon 21.5236–21.6891). All
positions are north/east offsets from BASE-01, so a new area is one new `Laydown`.
The UGV only drives inside that terrain box, so every route request is routable.

Default scenario (seed 42): **HOSTILE-A** fixed-wing from the west crossing the zone
(120 km/h), **HOSTILE-B** quadcopter from the south-east homing on BASE-01 (80 km/h, spawns
at T+60 s), **CIVIL-C** neutral transit south of the zone, and a **combined attack**:

* **ground, from the south** — 4 enemy trucks / UGVs assemble on the North Macedonian border
  side and drive north on the road network (one artemides A* route to an objective near the
  base, vehicles 25 s apart);
* **air, from Kosovo** — 15 attack UAVs and 2 attack helicopters launch in the west, fly to
  the convoy and take up formation: UAVs in two columns on the convoy's flanks (staggered
  ahead of and behind the lead, following its smoothed direction of advance), helicopters
  over the column.  The trucks move off once ≥ 80 % of the air element is on station
  (rendezvous, at most 15 min).  When the lead is 2.5 km out (or reaches its objective, or
  the convoy is lost) air and ground attack together: UAVs strike the base, helicopters fly to
  a 1.5 km stand-off point and fire 4 missiles each (P_hit 0.6), then egress.  Helicopters are
  manned — jammers do not affect them; radar classifies them by rotor micro-Doppler. Drones that reach the base count as **BASE HITS**, vehicles that reach their
objective as assaults.

With auto-ROE the attack is repelled (0 assaults, ≤ 3 of 17 hostile drones reach the base in
the tests); with no operator decisions at all only PVO fights and the base is hit and
assaulted. The attack size is set in the editor (**Trucks** 0–5, **UAV** 0–20, **Helo** 0–6); scenario
files saved before the convoy existed get the default attack on load.  While a hostile
ground threat exists, UGV charges are reserved for vehicles (drones get the jammer). Expected outcome: A destroyed by the interceptor, B jammed by the UGV,
C tracked as NEUTRAL and never engaged. With early operator approval A dies before
entering the zone.

## artemides-trax link (`integrations/artemides.py`)

The dashboard connects to the laydown's deployment by default
(`https://vojsrb.artemides-trax.com`, guest/demo routing — no token needed inside the
demo area; the drivability layer needs a token). `ARTEMIDES_URL` overrides it;
`ARTEMIDES_URL=""` forces offline mode, where UGVs drive straight lines (labelled
*offline straight-line*). Every call is asynchronous; while artemides A* is computing
(~9 s) a UGV keeps to its current route or holds. Status is shown in the dashboard.
Tests never touch the network.

| Variable | Meaning |
|---|---|
| `ARTEMIDES_URL` | e.g. `https://dev.artemides-trax.com` |
| `ARTEMIDES_TOKEN` | Bearer token from `api/auth.php` (`create_token`) |
| `ARTEMIDES_VEHICLE_PROFILE` | `vehicle_profiles.code` used for UGV routing |
| `ARTEMIDES_ROUTE_PROFILE` | `route_profile` for `api/route.php` (default `medium`) |
| `ARTEMIDES_TELEMETRY=1` | push UAV/UGV telemetry to `api/telemetry.php` |
| `ARTEMIDES_PUBLISH_THREATS=1` | create a `threat` manual_edit under each hostile track, deleted on neutralisation/exit |

artemides can answer a leg it cannot solve (e.g. *river without a known bridge*) with a
straight line flagged only as `no_route_found`; the client treats that as **not drivable**,
retries with the via point the server suggests, and otherwise reports NO ROUTE. Long routes
are requested with `allow_long_route`.

The two write paths are **opt-in**: simulated positions posted as real telemetry would
pollute artemides' driven-corridor statistics. Routes are requested with
`save_to_db: false`. artemides-trax needs no server-side changes — the existing
`route.php`, `telemetry.php`, `manual_edit.php` (`threat` type) and `auth.php` APIs are used.

```bash
./run.sh                                              # vojsrb, guest routing
ARTEMIDES_TOKEN=... ARTEMIDES_PUBLISH_THREATS=1 ./run.sh   # logged in, publish threat markers
ARTEMIDES_URL="" ./run.sh                             # fully offline
```

## Limits of the model

Simulation-grade physics: flat-earth ENU, constant-velocity tracker (no IMM), no
terrain masking/line-of-sight, probabilistic effect models. Seismic sensors only see
targets on the ground. The jammer beam is not identity-aware — the engagement manager
only points it at approved hostile tracks.
