"""
Territory — where Serbia's border / administrative line runs around the
scenario (sim/data/border_presevo.json, built from OpenStreetMap by
packaging/make_border.py).

Used for three rules:
  • the war starts when the first enemy crosses into the territory;
  • before it, the enemy's coordinated force keeps out;
  • our weapons engage only targets inside it (sovereign air / ground space).

The OSM line has ~1200 vertices, so tests are answered from a raster in
the local ENU frame (CELL_M cells, ±GRID_HALF_M around the base) built once
per base position: scan-line fill for inside / outside, and a breadth-first
band of MARGIN_M along the line for "close to the border".  Points outside
the raster fall back to the exact polygon test.
"""
from __future__ import annotations
import json
import math
from collections import deque
from pathlib import Path

from .zone import LocalFrame

DATA = Path(__file__).resolve().parent / "data" / "border_presevo.json"
CELL_M = 50.0
GRID_HALF_M = 30_000.0
MARGIN_M = 300.0

_OUT, _INSIDE, _NEAR = 0, 1, 2          # raster values: outside / inside / inside within MARGIN_M
_CACHE: dict[tuple, tuple] = {}


class Territory:
    def __init__(self, rings_latlon: list[list[tuple[float, float]]],
                 lines_latlon: list[list[tuple[float, float]]], frame: LocalFrame,
                 source: str = "") -> None:
        self.frame = frame
        self.source = source
        self.rings = [[frame.to_xy(lat, lon) for lat, lon in r] for r in rings_latlon]
        self.lines = [[frame.to_xy(lat, lon) for lat, lon in ln] for ln in lines_latlon]
        self.lines_latlon = lines_latlon
        key = (round(frame.ref_lat, 6), round(frame.ref_lon, 6), len(self.rings[0]) if self.rings else 0, source)
        if key not in _CACHE:
            _CACHE[key] = self._rasterise()
        self._n, self._grid = _CACHE[key]

    @classmethod
    def load(cls, frame: LocalFrame, path: Path = DATA) -> "Territory | None":
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return cls([[tuple(p) for p in r] for r in d["territory"]],
                   [[tuple(p) for p in ln] for ln in d["lines"]], frame, d.get("source", ""))

    # ── raster ────────────────────────────────────────────────────────────

    def _rasterise(self) -> tuple[int, bytearray]:
        n = int(2 * GRID_HALF_M / CELL_M)
        grid = bytearray(n * n)
        # scan-line fill: per row, the x where polygon edges cross the row centre
        rows: list[list[float]] = [[] for _ in range(n)]
        for ring in self.rings:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
                if y1 == y2:
                    continue
                lo, hi = min(y1, y2), max(y1, y2)
                r0 = max(0, math.ceil((lo + GRID_HALF_M) / CELL_M - 0.5))
                r1 = min(n - 1, math.floor((hi + GRID_HALF_M) / CELL_M - 0.5))
                for r in range(r0, r1 + 1):
                    y = -GRID_HALF_M + (r + 0.5) * CELL_M
                    if lo <= y < hi:
                        rows[r].append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        for r, xs in enumerate(rows):
            xs.sort()
            for a, b in zip(xs[0::2], xs[1::2]):
                c0 = max(0, math.ceil((a + GRID_HALF_M) / CELL_M - 0.5))
                c1 = min(n - 1, math.floor((b + GRID_HALF_M) / CELL_M - 0.5))
                if c1 >= c0:
                    grid[r * n + c0:r * n + c1 + 1] = b"\x01" * (c1 - c0 + 1)
        # band along the border line: cells on the line, then breadth-first MARGIN_M deep
        q: deque = deque()
        for ln in self.lines:
            for (x1, y1), (x2, y2) in zip(ln, ln[1:]):
                steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / (CELL_M / 2)))
                for k in range(steps + 1):
                    c, r = self._cell(x1 + (x2 - x1) * k / steps, y1 + (y2 - y1) * k / steps, n)
                    if c is not None:
                        q.append((r, c, 0))
        depth = int(MARGIN_M / CELL_M)
        seen = set()
        while q:
            r, c, d = q.popleft()
            if (r, c) in seen:
                continue
            seen.add((r, c))
            if grid[r * n + c] == _INSIDE:
                grid[r * n + c] = _NEAR
            if d < depth:
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < n and 0 <= cc < n and (rr, cc) not in seen:
                        q.append((rr, cc, d + 1))
        return n, grid

    @staticmethod
    def _cell(x: float, y: float, n: int):
        c = int((x + GRID_HALF_M) // CELL_M)
        r = int((y + GRID_HALF_M) // CELL_M)
        if 0 <= c < n and 0 <= r < n:
            return c, r
        return None, None

    def _value(self, x: float, y: float) -> int | None:
        c, r = self._cell(x, y, self._n)
        return None if c is None else self._grid[r * self._n + c]

    # ── queries ───────────────────────────────────────────────────────────

    def contains_xy(self, x: float, y: float) -> bool:
        v = self._value(x, y)
        return self._pip(x, y) if v is None else v != _OUT

    def contains(self, lat: float, lon: float) -> bool:
        return self.contains_xy(*self.frame.to_xy(lat, lon))

    def deep_inside_xy(self, x: float, y: float) -> bool:
        """Inside and at least MARGIN_M from the border line."""
        v = self._value(x, y)
        if v is None:
            return self._pip(x, y) and self.border_distance_m(x, y) >= MARGIN_M
        return v == _INSIDE

    def _pip(self, x: float, y: float) -> bool:
        inside = False
        for ring in self.rings:
            j = len(ring) - 1
            for i in range(len(ring)):
                xi, yi = ring[i]
                xj, yj = ring[j]
                if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
        return inside

    def border_distance_m(self, x: float, y: float) -> float:
        """Distance to the nearest border line (not to the region cut)."""
        best = math.inf
        for ln in self.lines:
            for (ax, ay), (bx, by) in zip(ln, ln[1:]):
                dx, dy = bx - ax, by - ay
                L2 = dx * dx + dy * dy
                t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
                best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
        return best

    def pull_inside(self, x: float, y: float, toward: tuple[float, float] = (0.0, 0.0),
                    margin_m: float = 300.0) -> tuple[float, float]:
        """Move (x, y) toward `toward` until it is inside with `margin_m` to the border."""
        tx, ty = toward
        for k in range(41):
            f = k / 40
            px, py = x + (tx - x) * f, y + (ty - y) * f
            if self.contains_xy(px, py) and self.border_distance_m(px, py) >= margin_m:
                return px, py
        return tx, ty

    def to_view(self) -> dict:
        return {"lines": [[{"lat": la, "lon": lo} for la, lo in ln] for ln in self.lines_latlon],
                "source": self.source}
