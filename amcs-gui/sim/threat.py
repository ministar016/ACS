"""
Threat evaluation — turns a kinematic track into a threat level, an
identity declaration and an engagement priority.

Rules (evaluated on the tracker's estimate, never on ground truth)
──────────────────────────────────────────────────────────────────
  inside restricted zone                         → HIGH,   HOSTILE
  predicted zone entry ≤ HIGH_TTE_S              → HIGH,   HOSTILE
  predicted zone entry ≤ MEDIUM_TTE_S            → MEDIUM, SUSPECT
  inside warning buffer (not inbound)            → MEDIUM, SUSPECT
  loitering (< 3 m/s) inside buffer              → MEDIUM, SUSPECT
  anything else                                  → LOW,    NEUTRAL (transit)

Ground tracks (vehicles on winding roads) use closing geometry instead of a
straight-line extrapolation alone:
  inside zone, or entry ≤ GROUND_HIGH_TTE_S, or closing on the asset
  within GROUND_HIGH_DIST_M                      → HIGH,   HOSTILE
  closing on the asset within GROUND_MEDIUM_DIST_M → MEDIUM, SUSPECT

Tentative (unconfirmed) tracks are capped at LOW / UNKNOWN — a single
sensor plot is never enough to declare hostile intent.

Escort rule: an air track that stays within ESCORT_ASSOC_M of a HOSTILE
ground track for ESCORT_DWELL_S is part of that force (drones weaving
alongside a convoy never point at the zone) → HIGH, HOSTILE "escorting
hostile convoy".  The dwell keeps a passing civil aircraft out of it.

Declared HOSTILE is sticky for the life of the track: a drone that turns
away after entering the zone does not get cleared by one good update.

Priority is "seconds of margin": smaller = more urgent.  Inside the zone the
margin is the time to reach the protected asset.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from enum import Enum, auto
from .models import ThreatLevel
from .zone import RestrictedZone

HIGH_TTE_S   = 90.0
MEDIUM_TTE_S = 240.0
GROUND_HIGH_TTE_S    = 600.0
GROUND_HIGH_DIST_M   = 8_000.0
GROUND_MEDIUM_DIST_M = 15_000.0
GROUND_CLOSING_MS    = 2.0
ESCORT_ASSOC_M       = 2_000.0
ESCORT_DWELL_S       = 60.0


class Identity(Enum):
    UNKNOWN = auto()
    NEUTRAL = auto()
    SUSPECT = auto()
    HOSTILE = auto()


@dataclass
class ThreatAssessment:
    level:          ThreatLevel
    identity:       Identity
    inside_zone:    bool
    time_to_entry:  float | None     # s, 0 if inside, None if not inbound
    dist_to_zone_m: float            # negative inside
    cpa_asset_m:    float
    cpa_time_s:     float
    priority:       float            # seconds of margin — lower = more urgent
    reason:         str


class ThreatEvaluator:
    def __init__(self, zone: RestrictedZone) -> None:
        self.zone = zone
        self._hostile: set[str] = set()

    def forget(self, track_id: str) -> None:
        self._hostile.discard(track_id)

    def as_escort(self, track_id: str, ta: ThreatAssessment, dist_to_convoy_m: float) -> ThreatAssessment:
        """Upgrade an air track that flies with a hostile ground force."""
        self._hostile.add(track_id)
        return ThreatAssessment(ThreatLevel.HIGH, Identity.HOSTILE, ta.inside_zone, ta.time_to_entry,
                                ta.dist_to_zone_m, ta.cpa_asset_m, ta.cpa_time_s,
                                min(ta.priority, 300.0 + ta.dist_to_zone_m / 30.0),
                                f"escorting hostile convoy ({dist_to_convoy_m / 1000:.1f} km)")

    def assess(self, track_id: str, x: float, y: float, vx: float, vy: float,
               confirmed: bool, domain: str = "AIR") -> ThreatAssessment:
        z = self.zone
        inside = z.contains(x, y)
        dist   = z.distance_to_boundary(x, y)
        ground = domain == "GROUND"
        tte    = z.time_to_entry(x, y, vx, vy,
                                 horizon_s=GROUND_HIGH_TTE_S if ground else MEDIUM_TTE_S)
        cpa_m, cpa_t = z.cpa_to_asset(x, y, vx, vy)
        speed  = math.hypot(vx, vy)

        if not confirmed:
            return ThreatAssessment(ThreatLevel.LOW, Identity.UNKNOWN, inside, tte,
                                    dist, cpa_m, cpa_t, 1e6, "tentative track")

        ax, ay = z.asset_xy
        d_asset = math.hypot(x - ax, y - ay)
        closing = -((x - ax) * vx + (y - ay) * vy) / max(d_asset, 1.0)

        if inside:
            t_asset = d_asset / max(speed, 1.0)
            level, ident, prio, why = ThreatLevel.HIGH, Identity.HOSTILE, t_asset, "inside restricted zone"
        elif ground:
            t_asset = d_asset / max(closing, 1.0)
            if (tte is not None and tte <= GROUND_HIGH_TTE_S) or \
                    (closing > GROUND_CLOSING_MS and d_asset <= GROUND_HIGH_DIST_M):
                level, ident, prio = ThreatLevel.HIGH, Identity.HOSTILE, t_asset
                why = f"vehicle closing {closing * 3.6:.0f} km/h, {d_asset / 1000:.1f} km"
            elif closing > GROUND_CLOSING_MS and d_asset <= GROUND_MEDIUM_DIST_M:
                level, ident, prio = ThreatLevel.MEDIUM, Identity.SUSPECT, t_asset
                why = f"vehicle approaching, {d_asset / 1000:.1f} km"
            elif 0 < dist <= z.buffer_m:
                level, ident, prio, why = ThreatLevel.MEDIUM, Identity.SUSPECT, t_asset, "vehicle in warning buffer"
            else:
                level, ident, prio, why = ThreatLevel.LOW, Identity.NEUTRAL, 1e5 + dist, "vehicle, not closing"
        elif tte is not None and tte <= HIGH_TTE_S:
            level, ident, prio, why = ThreatLevel.HIGH, Identity.HOSTILE, tte, f"zone entry in {tte:.0f}s"
        elif tte is not None:
            level, ident, prio, why = ThreatLevel.MEDIUM, Identity.SUSPECT, tte, f"inbound, entry in {tte:.0f}s"
        elif 0 < dist <= z.buffer_m:
            why = "loitering in buffer" if speed < 3.0 else "inside warning buffer"
            level, ident, prio = ThreatLevel.MEDIUM, Identity.SUSPECT, MEDIUM_TTE_S + dist / 10
        else:
            level, ident, prio, why = ThreatLevel.LOW, Identity.NEUTRAL, 1e5 + dist, "transit, not inbound"

        if ident == Identity.HOSTILE:
            self._hostile.add(track_id)
        elif track_id in self._hostile:
            # Sticky hostile declaration — keep at least MEDIUM
            ident = Identity.HOSTILE
            if level == ThreatLevel.LOW:
                level = ThreatLevel.MEDIUM
            why += " (previously declared hostile)"

        return ThreatAssessment(level, ident, inside, tte, dist, cpa_m, cpa_t, prio, why)
