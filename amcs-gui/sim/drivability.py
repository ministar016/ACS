"""
Drivability — where a UGV can go and how fast.

Built from the artemides-trax traversability grid (api/traversability.php):
each cell carries a combined cost 0..1 from satellite segmentation, driven
telemetry, route blocks and manual edits.  Cost maps to a drivability class
and a UGV speed:

    cost ≤ 0.12  ROAD       80 km/h
    cost ≤ 0.20  TRACK      50 km/h
    cost ≤ 0.35  OPEN       35 km/h
    cost ≤ 0.50  ROUGH      25 km/h
    cost ≤ 0.70  DIFFICULT  15 km/h
    cost  > 0.70 NO-GO      impassable (placement refused, router avoids)

Cells without data are "unknown": placement is allowed with a warning and
the UGV moves at UNKNOWN_SPEED_KMH.
"""
from __future__ import annotations
import math
import struct
import zlib
from dataclasses import dataclass

UNKNOWN_SPEED_KMH = 20.0

# (max cost, label, speed km/h, RGBA)
CLASSES = (
    (0.12, "ROAD",      80.0, (46, 204, 113, 170)),
    (0.20, "TRACK",     50.0, (163, 228, 55, 160)),
    (0.35, "OPEN",      35.0, (241, 196, 15, 150)),
    (0.50, "ROUGH",     25.0, (243, 156, 18, 150)),
    (0.70, "DIFFICULT", 15.0, (230, 126, 34, 150)),
    (9.99, "NO-GO",      0.0, (192, 57, 43, 160)),
)
NO_GO_COST = 0.70


def classify(cost: float | None) -> tuple[str, float]:
    """(label, speed km/h) for a cell cost; None → unknown."""
    if cost is None:
        return "UNKNOWN", UNKNOWN_SPEED_KMH
    for max_cost, label, speed, _ in CLASSES:
        if cost <= max_cost:
            return label, speed
    return "NO-GO", 0.0


@dataclass
class DrivabilityGrid:
    lat0: float          # south edge
    lon0: float          # west edge
    res:  float          # cell size, degrees
    rows: int
    cols: int
    costs: list          # row-major, None = no data

    # ── construction ──────────────────────────────────────────────────────

    @classmethod
    def from_cells(cls, cells: list[dict], bbox: tuple[float, float, float, float],
                   res: float) -> "DrivabilityGrid":
        lat_min, lat_max, lon_min, lon_max = bbox
        rows = max(1, int(math.ceil((lat_max - lat_min) / res)))
        cols = max(1, int(math.ceil((lon_max - lon_min) / res)))
        costs: list = [None] * (rows * cols)
        for c in cells:
            r = int((float(c["lat"]) - lat_min) / res)
            k = int((float(c["lon"]) - lon_min) / res)
            if 0 <= r < rows and 0 <= k < cols:
                cost = float(c["cost"])
                i = r * cols + k
                # overlapping tiles: keep the more conservative (higher) cost
                costs[i] = cost if costs[i] is None else max(costs[i], cost)
        return cls(lat_min, lon_min, res, rows, cols, costs)

    def to_dict(self) -> dict:
        return {"lat0": self.lat0, "lon0": self.lon0, "res": self.res,
                "rows": self.rows, "cols": self.cols, "costs": self.costs}

    @classmethod
    def from_dict(cls, d: dict) -> "DrivabilityGrid":
        return cls(d["lat0"], d["lon0"], d["res"], d["rows"], d["cols"], d["costs"])

    # ── queries ───────────────────────────────────────────────────────────

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.lat0, self.lat0 + self.rows * self.res,
                self.lon0, self.lon0 + self.cols * self.res)

    def _index(self, lat: float, lon: float) -> tuple[int, int] | None:
        r = int((lat - self.lat0) / self.res)
        k = int((lon - self.lon0) / self.res)
        if 0 <= r < self.rows and 0 <= k < self.cols:
            return r, k
        return None

    def cost_at(self, lat: float, lon: float) -> float | None:
        idx = self._index(lat, lon)
        return None if idx is None else self.costs[idx[0] * self.cols + idx[1]]

    def classify_at(self, lat: float, lon: float) -> tuple[str, float]:
        return classify(self.cost_at(lat, lon))

    def speed_ms_at(self, lat: float, lon: float) -> float:
        label, kmh = self.classify_at(lat, lon)
        # A vehicle already standing on a NO-GO cell (edge of a route) crawls
        return max(kmh, 15.0) / 3.6 if label == "NO-GO" else kmh / 3.6

    def is_drivable(self, lat: float, lon: float) -> bool | None:
        cost = self.cost_at(lat, lon)
        return None if cost is None else cost <= NO_GO_COST

    def nearest_drivable(self, lat: float, lon: float,
                         max_m: float = 1_000.0) -> tuple[float, float] | None:
        """Centre of the nearest drivable cell within max_m (spiral search)."""
        idx = self._index(lat, lon)
        if idx is None:
            return None
        r0, k0 = idx
        max_ring = int(max_m / (self.res * 111_320)) + 1
        for ring in range(max_ring + 1):
            best = None
            for r in range(r0 - ring, r0 + ring + 1):
                for k in range(k0 - ring, k0 + ring + 1):
                    if max(abs(r - r0), abs(k - k0)) != ring:
                        continue
                    if 0 <= r < self.rows and 0 <= k < self.cols:
                        c = self.costs[r * self.cols + k]
                        if c is not None and c <= NO_GO_COST:
                            d = (r - r0) ** 2 + (k - k0) ** 2
                            if best is None or d < best[0]:
                                best = (d, r, k)
            if best:
                _, r, k = best
                return (self.lat0 + (r + 0.5) * self.res, self.lon0 + (k + 0.5) * self.res)
        return None

    def stats(self) -> dict:
        out: dict[str, int] = {}
        for c in self.costs:
            label = classify(c)[0]
            out[label] = out.get(label, 0) + 1
        return out

    # ── rendering ─────────────────────────────────────────────────────────

    def to_png(self) -> bytes:
        """RGBA PNG, north-up (row 0 = north edge), one pixel per cell."""
        raw = bytearray()
        for r in range(self.rows - 1, -1, -1):
            raw.append(0)                                  # filter type: none
            for k in range(self.cols):
                c = self.costs[r * self.cols + k]
                if c is None:
                    raw += b"\x00\x00\x00\x00"
                    continue
                for max_cost, _, _, rgba in CLASSES:
                    if c <= max_cost:
                        raw += bytes(rgba)
                        break
        return _png(self.cols, self.rows, bytes(raw))


def _png(width: int, height: int, raw_rgba_rows: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)   # 8-bit RGBA
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw_rgba_rows, 9)) + chunk(b"IEND", b""))
