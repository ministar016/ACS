"""
Generate sim/data/border_presevo.json — Serbia's state border with North
Macedonia and the administrative line with Kosovo around the Preševo
valley, from OpenStreetMap (© OpenStreetMap contributors, ODbL).

The outer ways of OSM relation 1741311 (Serbia) inside the scenario region
are stitched into one line, simplified to SIMPLIFY_M, clipped to REGION and
closed along the region edge on the side of the base — that polygon is the
territory for the simulation's border rules.

    cd amcs-gui && .venv/bin/python packaging/make_border.py
"""
from __future__ import annotations
import json
import math
import os
import urllib.parse
import urllib.request
from pathlib import Path

OVERPASS = "https://overpass-api.de/api/interpreter"
RELATION = 1741311                                   # Serbia
REGION = (41.95, 42.65, 21.10, 22.15)                # lat_min, lat_max, lon_min, lon_max
INSIDE_REF = (42.27442, 21.606345)                   # a point known to be in Serbia (the scenario base)
SIMPLIFY_M = 15.0
OUT = Path(__file__).resolve().parent.parent / "sim" / "data" / "border_presevo.json"


def fetch_ways() -> list[dict]:
    """Overpass answer, cached in $TMPDIR (the public server is often busy — 504)."""
    cache = Path(os.environ.get("TMPDIR", "/tmp")) / f"osm_border_{RELATION}.json"
    if not cache.exists():
        la0, la1, lo0, lo1 = REGION
        q = f"[out:json][timeout:120];relation({RELATION});way(r)({la0},{lo0},{la1},{lo1});out geom tags;"
        req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(),
                                     headers={"User-Agent": "AMCS-C2/1.0 (border data)", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            cache.write_bytes(resp.read())
    return [e for e in json.loads(cache.read_text())["elements"] if e["type"] == "way"]


def stitch(ways: list[dict]) -> list[list[tuple[float, float]]]:
    """Join ways that share end points into chains of (lat, lon)."""
    def key(p):
        return (round(p[0], 7), round(p[1], 7))
    segs = [[(g["lat"], g["lon"]) for g in w["geometry"]] for w in ways]
    chains: list[list[tuple[float, float]]] = []
    while segs:
        chain = segs.pop(0)
        grown = True
        while grown:
            grown = False
            for i, s in enumerate(segs):
                if key(s[0]) == key(chain[-1]):
                    chain += s[1:]
                elif key(s[-1]) == key(chain[-1]):
                    chain += s[::-1][1:]
                elif key(s[-1]) == key(chain[0]):
                    chain = s[:-1] + chain
                elif key(s[0]) == key(chain[0]):
                    chain = s[::-1][:-1] + chain
                else:
                    continue
                segs.pop(i)
                grown = True
                break
        chains.append(chain)
    return chains


def _xy(p, lat0):
    return (p[1] * 111320.0 * math.cos(math.radians(lat0)), p[0] * 111320.0)


def simplify(line, tol_m):
    """Douglas–Peucker in metres."""
    if len(line) < 3:
        return line
    lat0 = line[0][0]
    pts = [_xy(p, lat0) for p in line]
    keep = [False] * len(line)
    keep[0] = keep[-1] = True
    stack = [(0, len(line) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-9
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            d = abs(dy * (pts[i][0] - ax) - dx * (pts[i][1] - ay)) / L
            if d > best:
                best, bi = d, i
        if best > tol_m:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(line, keep) if k]


def _inside_region(p):
    return REGION[0] <= p[0] <= REGION[1] and REGION[2] <= p[1] <= REGION[3]


def _cut(a, b):
    """Point where segment a→b (one end inside, one outside) crosses the region edge."""
    lo, hi = 0.0, 1.0
    ina = _inside_region(a)
    for _ in range(40):
        m = (lo + hi) / 2
        p = (a[0] + (b[0] - a[0]) * m, a[1] + (b[1] - a[1]) * m)
        if _inside_region(p) == ina:
            lo = m
        else:
            hi = m
    m = lo if ina else hi
    return (a[0] + (b[0] - a[0]) * m, a[1] + (b[1] - a[1]) * m)


def clip(chain):
    """Pieces of the chain inside the region, each starting / ending on its edge."""
    pieces, cur = [], []
    for a, b in zip(chain, chain[1:]):
        ia, ib = _inside_region(a), _inside_region(b)
        if ia and not cur:
            cur = [a]
        if ia and ib:
            cur.append(b)
        elif ia and not ib:
            cur.append(_cut(a, b))
            pieces.append(cur)
            cur = []
        elif not ia and ib:
            cur = [_cut(a, b), b]
    if len(cur) > 1:
        pieces.append(cur)
    return pieces


def _perimeter_pos(p):
    """Position along the region boundary, counter-clockwise from the SW corner (0…4)."""
    la0, la1, lo0, lo1 = REGION
    eps = 1e-7
    if abs(p[0] - la0) < eps:
        return (p[1] - lo0) / (lo1 - lo0)                 # south edge, west → east
    if abs(p[1] - lo1) < eps:
        return 1 + (p[0] - la0) / (la1 - la0)             # east edge, south → north
    if abs(p[0] - la1) < eps:
        return 2 + (lo1 - p[1]) / (lo1 - lo0)             # north edge, east → west
    return 3 + (la1 - p[0]) / (la1 - la0)                 # west edge, north → south


_CORNERS = [(1, (REGION[0], REGION[3])), (2, (REGION[1], REGION[3])),
            (3, (REGION[1], REGION[2])), (4, (REGION[0], REGION[2]))]


def _walk(frm, to, ccw):
    """Region corners passed going from perimeter position frm to to."""
    out = []
    if ccw:
        t = to if to >= frm else to + 4
        for c, p in _CORNERS + [(c + 4, p) for c, p in _CORNERS]:
            if frm < c < t:
                out.append(p)
    else:
        t = to if to <= frm else to - 4
        for c, p in sorted(_CORNERS + [(c - 4, p) for c, p in _CORNERS], reverse=True):
            if t < c < frm:
                out.append(p)
    return out


def _pip(pt, ring):
    y, x = pt
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def main() -> None:
    ways = fetch_ways()
    chains = stitch(ways)
    pieces = [p for c in chains for p in clip(c)]
    if len(pieces) != 1:
        raise SystemExit(f"expected the border to cross the region once, got {len(pieces)} pieces — adjust REGION")
    line = simplify(pieces[0], SIMPLIFY_M)
    a, b = _perimeter_pos(line[0]), _perimeter_pos(line[-1])
    ring = None
    for ccw in (True, False):
        cand = line + _walk(b, a, ccw)
        if _pip(INSIDE_REF, cand):
            ring = cand
            break
    if ring is None:
        raise SystemExit("reference point not inside either side of the border")
    doc = {
        "source": "© OpenStreetMap contributors (ODbL) — relation 1741311 outer ways: "
                  "North Macedonia–Serbia border and Serbia–Kosovo line",
        "accuracy_m": SIMPLIFY_M,
        "region": REGION,
        "ways": len(ways),
        "territory": [[[round(lat, 6), round(lon, 6)] for lat, lon in ring]],
        "lines": [[[round(lat, 6), round(lon, 6)] for lat, lon in line]],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc), encoding="utf-8")
    print(f"{OUT}: {len(ways)} OSM ways → border line {len(line)} vertices, territory ring {len(ring)}")


if __name__ == "__main__":
    main()
