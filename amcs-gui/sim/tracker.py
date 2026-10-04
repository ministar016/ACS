"""
MultiTargetTracker — Kalman-filter tracking of aerial targets from
heterogeneous sensor measurements.

Model
─────
State per track, local ENU frame:   x = [px, py, vx, vy]ᵀ   (m, m/s)
Motion model: constant velocity + white-noise acceleration (q m²/s³).
Altitude is filtered separately (α-filter) — radar elevation is too noisy
to be worth a full 6-state filter at these ranges.

Measurements
────────────
PositionMeas  — radar plot (range/azimuth converted to ENU) with a full 2×2
                covariance: σ_range along the line of sight, r·σ_az across it.
BearingMeas   — acoustic line of bearing.  Used two ways:
                  • EKF update of an existing track   h(x) = atan2(px−sx, py−sy)
                  • unassociated bearings from two different sensors are
                    triangulated into a coarse PositionMeas for initiation.

Data association: global-nearest-neighbour (greedy on Mahalanobis d²)
with χ² gating.  Track life cycle uses M-of-N confirmation and time-based
deletion:

  TENTATIVE ──3 hits──▶ CONFIRMED ──no update > coast_s──▶ (deleted)
      └─ no update > 2 s ─▶ (deleted)

IFF: position plots that correlate with a known friendly asset (own
interceptor UAV, UGV) are discarded before association so our own drone
can never become a track — the classic fratricide guard.

Domain: radar plots carry the mode they came from (AIR search or GROUND
moving-target indication); a track keeps the domain it was started with and
only associates plots of the same domain.  Triangulated acoustic plots are
UNKNOWN and may start or join either.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum, auto

_GATE_POS_D2   = 13.8    # χ²(2 dof) 99.9 %
_GATE_BRG_SIG  = 3.5     # bearing gate in σ
_CONFIRM_HITS  = 3       # radar plots needed to confirm (bearings never confirm)
_TENTATIVE_TTL = 3.5     # s without update before a tentative track dies
_COAST_S       = 10.0    # s without update before a confirmed track dies
_COAST_AFTER_S = 2.5     # confirmed → COASTING after this long without update
_INIT_VEL_VAR  = 40.0 ** 2
_IFF_RADIUS_M  = 80.0     # hard radius around a friendly
_IFF_GATE_D2   = 18.4     # χ²(2 dof) 99.99 % — Mahalanobis IFF gate
_IFF_POS_VAR   = 15.0 ** 2  # friendly self-reported position uncertainty
_INIT_GATE_D2  = 30.0     # no new track inside this gate of an existing one


class TrackStatus(Enum):
    TENTATIVE = auto()
    CONFIRMED = auto()
    COASTING  = auto()   # confirmed, but no update for > 1 s


@dataclass
class PositionMeas:
    sensor_id: str
    x: float
    y: float
    R: list[list[float]]          # 2×2 covariance (m²)
    alt: float | None = None
    alt_sigma: float = 50.0
    domain: str = "AIR"           # AIR | GROUND | UNKNOWN
    radar: bool = True            # False for triangulated bearing plots


@dataclass
class BearingMeas:
    sensor_id: str
    sx: float
    sy: float
    bearing_rad: float            # 0 = north, clockwise
    sigma_rad: float
    max_range_m: float = 2_500.0
    domain: str = "UNKNOWN"       # GROUND for seismic arrays (only vehicles), UNKNOWN for acoustic


@dataclass
class _Track:
    track_id:   str
    x:          list[float]
    P:          list[list[float]]
    alt:        float
    t_created:  float
    t_update:   float            # last update of any kind
    t_pos:      float = 0.0      # last radar/position update — drives track life
    hits:       int = 1
    pos_hits:   int = 1          # radar plots only — used for confirmation
    status:     TrackStatus = TrackStatus.TENTATIVE
    sources:    dict[str, float] = field(default_factory=dict)   # sensor → last time
    obj_class:  str = "UNKNOWN"
    domain:     str = "UNKNOWN"


# ── tiny linear-algebra helpers (4×4 / 2×2, no numpy dependency) ─────────────

def _mat_mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(len(B))) for j in range(len(B[0]))]
            for i in range(len(A))]


def _inv2(S):
    a, b = S[0]
    c, d = S[1]
    det = a * d - b * c
    if abs(det) < 1e-12:
        return None
    return [[d / det, -b / det], [-c / det, a / det]]


def _symmetrize(P):
    n = len(P)
    return [[0.5 * (P[i][j] + P[j][i]) for j in range(n)] for i in range(n)]


def _wrap_pi(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


class MultiTargetTracker:
    def __init__(self, q_accel: float = 12.0, id_prefix: str = "TRK") -> None:
        self._q       = q_accel
        self._prefix  = id_prefix
        self._next_id = 1
        self._tracks: dict[str, _Track] = {}
        self._t       = 0.0
        self.iff_rejects = 0          # cumulative friendly plots discarded

    # ── public API ────────────────────────────────────────────────────────

    @property
    def tracks(self) -> list[_Track]:
        return list(self._tracks.values())

    def get(self, track_id: str) -> _Track | None:
        return self._tracks.get(track_id)

    def update(self, t: float,
               positions: list[PositionMeas],
               bearings:  list[BearingMeas],
               friendlies: list[tuple[float, float]] = (),
               classifications: list[tuple[float, float, str]] = ()) -> list[_Track]:
        """
        Run one scan: predict all tracks to t, discard friendly plots,
        associate, update, initiate, and prune.

        classifications: (x, y, class) from EO cameras — attached to the
        nearest track within 150 m.
        """
        dt = t - self._t
        self._t = t
        if dt > 0:
            for trk in self._tracks.values():
                self._predict(trk, dt)

        # IFF: drop plots that correlate with a friendly asset
        kept = []
        for m in positions:
            if any(_is_friendly(m, fx, fy) for fx, fy in friendlies):
                self.iff_rejects += 1
                continue
            kept.append(m)

        # Sequential per-sensor association: plots from different sensors of
        # the same target must all update one track, not spawn duplicates.
        by_sensor: dict[str, list[PositionMeas]] = {}
        for m in kept:
            by_sensor.setdefault(m.sensor_id, []).append(m)
        for sensor_id in sorted(by_sensor):
            for m in self._associate_positions(t, by_sensor[sensor_id]):
                if all(self._d2(trk, m) > _INIT_GATE_D2 for trk in self._tracks.values()):
                    self._initiate(t, m)

        stray_bearings = self._associate_bearings(t, bearings)

        # Initiation from triangulated acoustic bearings (only where no track exists)
        for m in self._triangulate(stray_bearings):
            if not any(math.hypot(m.x - f[0], m.y - f[1]) < _IFF_RADIUS_M * 3 for f in friendlies):
                if all(self._d2(trk, m) > _INIT_GATE_D2 for trk in self._tracks.values()):
                    self._initiate(t, m)

        # A tentative track sitting on a friendly is a leaked own-force plot
        for tid in [tid for tid, trk in self._tracks.items()
                    if trk.status == TrackStatus.TENTATIVE and any(
                        math.hypot(trk.x[0] - fx, trk.x[1] - fy) < 2 * _IFF_RADIUS_M
                        for fx, fy in friendlies)]:
            del self._tracks[tid]

        for cx, cy, cls in classifications:
            best = min(self._tracks.values(),
                       key=lambda tr: math.hypot(tr.x[0] - cx, tr.x[1] - cy),
                       default=None)
            if best and math.hypot(best.x[0] - cx, best.x[1] - cy) < 150.0:
                best.obj_class = cls

        self._prune(t)
        return self.tracks

    # ── Kalman steps ──────────────────────────────────────────────────────

    def _predict(self, trk: _Track, dt: float) -> None:
        px, py, vx, vy = trk.x
        trk.x = [px + vx * dt, py + vy * dt, vx, vy]
        # P' = F P Fᵀ + Q for the CV model, written out (F = [[I, dt·I], [0, I]])
        P = trk.P
        q = self._q
        qa, qb, qc = dt ** 4 / 4 * q, dt ** 3 / 2 * q, dt * dt * q
        # A = F P
        A = [[P[0][j] + dt * P[2][j] for j in range(4)],
             [P[1][j] + dt * P[3][j] for j in range(4)],
             list(P[2]), list(P[3])]
        # A Fᵀ: columns 0,1 pick up dt × columns 2,3
        N = [[A[i][0] + dt * A[i][2], A[i][1] + dt * A[i][3], A[i][2], A[i][3]] for i in range(4)]
        N[0][0] += qa; N[1][1] += qa; N[2][2] += qc; N[3][3] += qc
        N[0][2] += qb; N[2][0] += qb; N[1][3] += qb; N[3][1] += qb
        trk.P = N

    def _innovation(self, trk: _Track, m: PositionMeas):
        y = [m.x - trk.x[0], m.y - trk.x[1]]
        S = [[trk.P[0][0] + m.R[0][0], trk.P[0][1] + m.R[0][1]],
             [trk.P[1][0] + m.R[1][0], trk.P[1][1] + m.R[1][1]]]
        return y, S

    def _d2(self, trk: _Track, m: PositionMeas) -> float:
        if m.domain != "UNKNOWN" and trk.domain != "UNKNOWN" and m.domain != trk.domain:
            return float("inf")
        # Cheap Euclidean pre-gate before the Mahalanobis test
        dx, dy = m.x - trk.x[0], m.y - trk.x[1]
        if dx * dx + dy * dy > 16.0 * (trk.P[0][0] + trk.P[1][1] + m.R[0][0] + m.R[1][1]):
            return float("inf")
        y, S = self._innovation(trk, m)
        Si = _inv2(S)
        if Si is None:
            return float("inf")
        return (y[0] * (Si[0][0] * y[0] + Si[0][1] * y[1]) +
                y[1] * (Si[1][0] * y[0] + Si[1][1] * y[1]))

    def _update_position(self, t: float, trk: _Track, m: PositionMeas) -> None:
        y, S = self._innovation(trk, m)
        Si = _inv2(S)
        if Si is None:
            return
        # K = P Hᵀ S⁻¹, with H selecting the position rows
        PHt = [[trk.P[i][0], trk.P[i][1]] for i in range(4)]
        K = _mat_mul(PHt, Si)
        trk.x = [trk.x[i] + K[i][0] * y[0] + K[i][1] * y[1] for i in range(4)]
        # P = (I − K H) P
        KH = [[K[i][0] if j == 0 else K[i][1] if j == 1 else 0.0 for j in range(4)]
              for i in range(4)]
        IKH = [[(1.0 if i == j else 0.0) - KH[i][j] for j in range(4)] for i in range(4)]
        trk.P = _symmetrize(_mat_mul(IKH, trk.P))
        if m.alt is not None:
            trk.alt += 0.2 * (m.alt - trk.alt)
        if trk.domain == "UNKNOWN" and m.domain != "UNKNOWN":
            trk.domain = m.domain
        if m.radar:
            trk.pos_hits += 1
        trk.t_pos = t
        self._mark_hit(t, trk, m.sensor_id)

    def _bearing_innov(self, trk: _Track, b: BearingMeas):
        dx, dy = trk.x[0] - b.sx, trk.x[1] - b.sy
        r2 = max(dx * dx + dy * dy, 1.0)
        H = [dy / r2, -dx / r2, 0.0, 0.0]
        pred = math.atan2(dx, dy)
        innov = _wrap_pi(b.bearing_rad - pred)
        PHt = [sum(trk.P[i][k] * H[k] for k in range(4)) for i in range(4)]
        S = sum(H[i] * PHt[i] for i in range(4)) + b.sigma_rad ** 2
        return innov, S, H, PHt, math.sqrt(r2)

    def _update_bearing(self, t: float, trk: _Track, b: BearingMeas) -> None:
        innov, S, H, PHt, _ = self._bearing_innov(trk, b)
        K = [p / S for p in PHt]
        trk.x = [trk.x[i] + K[i] * innov for i in range(4)]
        trk.P = _symmetrize([[trk.P[i][j] - K[i] * PHt[j] for j in range(4)] for i in range(4)])
        self._mark_hit(t, trk, b.sensor_id)

    def _mark_hit(self, t: float, trk: _Track, sensor_id: str) -> None:
        trk.t_update = t
        trk.hits += 1
        trk.sources[sensor_id] = t
        if trk.pos_hits >= _CONFIRM_HITS:
            trk.status = TrackStatus.CONFIRMED

    # ── association ───────────────────────────────────────────────────────

    def _associate_positions(self, t: float, meas: list[PositionMeas]) -> list[PositionMeas]:
        pairs = []
        for mi, m in enumerate(meas):
            for trk in self._tracks.values():
                d2 = self._d2(trk, m)
                if d2 < _GATE_POS_D2:
                    pairs.append((d2, mi, trk.track_id))
        pairs.sort()
        used_m: set[int] = set()
        used_t: set[str] = set()
        for _, mi, tid in pairs:
            if mi in used_m or tid in used_t:
                continue
            used_m.add(mi)
            used_t.add(tid)
            self._update_position(t, self._tracks[tid], meas[mi])
        return [m for i, m in enumerate(meas) if i not in used_m]

    def _associate_bearings(self, t: float, bearings: list[BearingMeas]) -> list[BearingMeas]:
        stray = []
        for b in bearings:
            best, best_n = None, _GATE_BRG_SIG
            for trk in self._tracks.values():
                if b.domain != "UNKNOWN" and trk.domain not in ("UNKNOWN", b.domain):
                    continue
                dx, dy = trk.x[0] - b.sx, trk.x[1] - b.sy
                r2 = dx * dx + dy * dy
                if r2 > (b.max_range_m * 1.3) ** 2:
                    continue
                # Cheap angular pre-gate before the full EKF innovation
                ang = abs(_wrap_pi(b.bearing_rad - math.atan2(dx, dy)))
                s_approx = (trk.P[0][0] + trk.P[1][1]) / max(r2, 1.0) + b.sigma_rad ** 2
                if ang > _GATE_BRG_SIG * math.sqrt(s_approx) * 1.5:
                    continue
                innov, S, _, _, rng = self._bearing_innov(trk, b)
                n = abs(innov) / math.sqrt(S)
                if n < best_n:
                    best, best_n = trk, n
            if best is not None:
                self._update_bearing(t, best, b)
            else:
                stray.append(b)
        return stray

    @staticmethod
    def _triangulate(bearings: list[BearingMeas]) -> list[PositionMeas]:
        out = []
        for i in range(len(bearings)):
            for j in range(i + 1, len(bearings)):
                a, b = bearings[i], bearings[j]
                if a.sensor_id == b.sensor_id:
                    continue
                dxa, dya = math.sin(a.bearing_rad), math.cos(a.bearing_rad)
                dxb, dyb = math.sin(b.bearing_rad), math.cos(b.bearing_rad)
                det = -dxa * dyb + dya * dxb
                if abs(det) < 0.17:         # < ~10° crossing angle → ill-conditioned
                    continue
                ex, ey = b.sx - a.sx, b.sy - a.sy
                ta = (-ex * dyb + ey * dxb) / det
                tb = (dxa * ey - dya * ex) / det
                if ta <= 0 or tb <= 0 or ta > a.max_range_m or tb > b.max_range_m:
                    continue
                x, y = a.sx + ta * dxa, a.sy + ta * dya
                s = max(ta * a.sigma_rad, tb * b.sigma_rad) / abs(det)
                # Triangulated plots never confirm a track on their own (domain UNKNOWN
                # does not count as a radar hit); a seismic pair is at least ground.
                dom = "GROUND" if a.domain == b.domain == "GROUND" else "UNKNOWN"
                out.append(PositionMeas(f"{a.sensor_id}+{b.sensor_id}", x, y,
                                        [[s * s, 0.0], [0.0, s * s]], domain=dom, radar=False))
        return out

    # ── life cycle ────────────────────────────────────────────────────────

    def _initiate(self, t: float, m: PositionMeas) -> None:
        tid = f"{self._prefix}-{self._next_id:03d}"
        self._next_id += 1
        P = [[m.R[0][0], m.R[0][1], 0, 0],
             [m.R[1][0], m.R[1][1], 0, 0],
             [0, 0, _INIT_VEL_VAR, 0],
             [0, 0, 0, _INIT_VEL_VAR]]
        self._tracks[tid] = _Track(
            track_id=tid, x=[m.x, m.y, 0.0, 0.0], P=P,
            alt=m.alt if m.alt is not None else 100.0,
            t_created=t, t_update=t, t_pos=t, sources={m.sensor_id: t}, domain=m.domain,
            pos_hits=1 if m.radar else 0,
        )

    def _prune(self, t: float) -> None:
        for tid in list(self._tracks):
            trk = self._tracks[tid]
            # Bearings refine a track but never keep it alive: a track that has
            # lost its position updates would otherwise drift along a bearing line.
            age = t - trk.t_pos
            if trk.status == TrackStatus.TENTATIVE:
                if age > _TENTATIVE_TTL:
                    del self._tracks[tid]
            elif age > _COAST_S:
                del self._tracks[tid]
            elif age > _COAST_AFTER_S:
                trk.status = TrackStatus.COASTING
            elif trk.status == TrackStatus.COASTING:
                trk.status = TrackStatus.CONFIRMED
            # sources older than 4 s no longer count as contributing
            trk.sources = {s: ts for s, ts in trk.sources.items() if t - ts <= 4.0}


def _is_friendly(m: PositionMeas, fx: float, fy: float) -> bool:
    dx, dy = m.x - fx, m.y - fy
    if math.hypot(dx, dy) < _IFF_RADIUS_M:
        return True
    Si = _inv2([[m.R[0][0] + _IFF_POS_VAR, m.R[0][1]],
                [m.R[1][0], m.R[1][1] + _IFF_POS_VAR]])
    if Si is None:
        return False
    d2 = dx * (Si[0][0] * dx + Si[0][1] * dy) + dy * (Si[1][0] * dx + Si[1][1] * dy)
    return d2 < _IFF_GATE_D2


def radar_to_meas(sensor_id: str, sx: float, sy: float, s_alt: float,
                  range_m: float, abs_az_deg: float, el_deg: float,
                  sigma_r: float = 30.0, sigma_az_deg: float = 0.5,
                  domain: str = "AIR") -> PositionMeas:
    """Convert a radar plot (slant range, absolute azimuth, elevation) to ENU."""
    b  = math.radians(abs_az_deg)
    el = math.radians(el_deg)
    r_h = range_m * math.cos(el)
    x = sx + r_h * math.sin(b)
    y = sy + r_h * math.cos(b)
    ux, uy = math.sin(b), math.cos(b)            # line of sight
    cx, cy = math.cos(b), -math.sin(b)           # cross range
    sc = max(r_h, 1.0) * math.radians(sigma_az_deg)
    R = [[sigma_r ** 2 * ux * ux + sc ** 2 * cx * cx, sigma_r ** 2 * ux * uy + sc ** 2 * cx * cy],
         [sigma_r ** 2 * ux * uy + sc ** 2 * cx * cy, sigma_r ** 2 * uy * uy + sc ** 2 * cy * cy]]
    return PositionMeas(sensor_id, x, y, R,
                        alt=s_alt + range_m * math.sin(el) if domain != "GROUND" else 0.0,
                        alt_sigma=range_m * math.radians(0.3), domain=domain)
