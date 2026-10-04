"""
RestrictedZone — geofence of the protected area plus a warning buffer.

All geometry is done in a flat local ENU frame (metres east / north of a
reference point).  Over the ~40 km operating area the flat-earth error is
well below sensor noise, and it keeps the polygon maths trivial.

Threat questions answered here
──────────────────────────────
contains(x, y)            — is a point inside the restricted zone?
distance_to_boundary(x,y) — metres to the zone edge (negative = inside)
time_to_entry(p, v)       — seconds until a constant-velocity track crosses
                            into the zone (0 if already inside, None if never
                            within the look-ahead horizon)
"""
from __future__ import annotations
import math
from dataclasses import dataclass

_M_PER_DEG_LAT = 111_320.0


class LocalFrame:
    """Equirectangular lat/lon ↔ local ENU metres around a reference point."""

    def __init__(self, ref_lat: float, ref_lon: float) -> None:
        self.ref_lat = ref_lat
        self.ref_lon = ref_lon
        self._m_per_deg_lon = _M_PER_DEG_LAT * math.cos(math.radians(ref_lat))

    def to_xy(self, lat: float, lon: float) -> tuple[float, float]:
        return ((lon - self.ref_lon) * self._m_per_deg_lon,
                (lat - self.ref_lat) * _M_PER_DEG_LAT)

    def to_latlon(self, x: float, y: float) -> tuple[float, float]:
        return (self.ref_lat + y / _M_PER_DEG_LAT,
                self.ref_lon + x / self._m_per_deg_lon)


@dataclass
class ProtectedAsset:
    asset_id: str
    lat: float
    lon: float


class RestrictedZone:
    """
    Polygonal no-fly zone around a protected asset.

    vertices are (lat, lon) in order (either winding).  The warning buffer
    is an outward offset of `buffer_m`, approximated by distance-to-edge.
    """

    def __init__(self, zone_id: str, vertices: list[tuple[float, float]],
                 frame: LocalFrame, asset: ProtectedAsset,
                 buffer_m: float = 1_500.0) -> None:
        if len(vertices) < 3:
            raise ValueError("zone needs at least 3 vertices")
        self.zone_id  = zone_id
        self.vertices = list(vertices)
        self.frame    = frame
        self.asset    = asset
        self.buffer_m = buffer_m
        self._poly    = [frame.to_xy(lat, lon) for lat, lon in vertices]
        self.asset_xy = frame.to_xy(asset.lat, asset.lon)

    # ── point queries ─────────────────────────────────────────────────────

    def contains(self, x: float, y: float) -> bool:
        """Ray-casting point-in-polygon test."""
        inside = False
        n = len(self._poly)
        for i in range(n):
            x1, y1 = self._poly[i]
            x2, y2 = self._poly[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if x < x_cross:
                    inside = not inside
        return inside

    def distance_to_boundary(self, x: float, y: float) -> float:
        """Metres to the nearest edge; negative when inside the zone."""
        d = min(_seg_dist(x, y, *self._poly[i], *self._poly[(i + 1) % len(self._poly)])
                for i in range(len(self._poly)))
        return -d if self.contains(x, y) else d

    def in_buffer(self, x: float, y: float) -> bool:
        d = self.distance_to_boundary(x, y)
        return 0.0 < d <= self.buffer_m

    # ── trajectory queries ────────────────────────────────────────────────

    def time_to_entry(self, x: float, y: float, vx: float, vy: float,
                      horizon_s: float = 300.0) -> float | None:
        """
        Seconds until a constant-velocity trajectory enters the zone: the
        earliest crossing of the ray p + v·t with any polygon edge (works for
        any simple polygon, convex or not).
        """
        if self.contains(x, y):
            return 0.0
        best = None
        n = len(self._poly)
        for i in range(n):
            x1, y1 = self._poly[i]
            x2, y2 = self._poly[(i + 1) % n]
            ex, ey = x2 - x1, y2 - y1
            den = vx * ey - vy * ex
            if abs(den) < 1e-12:
                continue                                  # parallel to the edge
            qx, qy = x1 - x, y1 - y
            t = (qx * ey - qy * ex) / den                 # along the ray
            u = (qx * vy - qy * vx) / den                 # along the edge
            if t > 0 and 0.0 <= u <= 1.0 and (best is None or t < best):
                best = t
        return best if best is not None and best <= horizon_s else None

    def cpa_to_asset(self, x: float, y: float, vx: float, vy: float) -> tuple[float, float]:
        """(closest-approach distance m, time s ≥ 0) to the protected asset."""
        ax, ay = self.asset_xy
        rx, ry = x - ax, y - ay
        v2 = vx * vx + vy * vy
        t = 0.0 if v2 < 1e-9 else max(0.0, -(rx * vx + ry * vy) / v2)
        return math.hypot(rx + vx * t, ry + vy * t), t

    # ── serialisation for the GUI / artemides bridge ──────────────────────

    def to_dict(self) -> dict:
        return {
            "zoneId":   self.zone_id,
            "vertices": [{"lat": lat, "lon": lon} for lat, lon in self.vertices],
            "bufferM":  self.buffer_m,
            "asset":    {"id": self.asset.asset_id,
                         "lat": self.asset.lat, "lon": self.asset.lon},
        }


def _seg_dist(px: float, py: float,
              x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
