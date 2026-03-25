"""
RealTerrain — SRTM-30m elevation + OSM map colours for the tactical field.

Centre   : 48.231978 °N,  11.608821 °E  (Haar, Munich, Germany)
Area     : 100 × 100 m
Elevation: OpenTopoData API  https://api.opentopodata.org  (SRTM-30m, free)
Map tiles: OpenStreetMap  https://tile.openstreetmap.org  (zoom 17, 2×2 block)
Cache dir: sim/cache/  ← persistent, no re-download after first run

Public API
──────────
get_elevation_grid()       → (101, 101) float32 relative heights [m]  or None
get_osm_colors_for_field() → (101, 101, 4) float32 RGBA map colours   or None
get_osm_tile_bytes()       → raw PNG bytes of center tile              or None
"""
from __future__ import annotations
import io
import math
from pathlib import Path
from typing  import Optional

import numpy as np

# ── Field parameters ──────────────────────────────────────────────────────────
CENTER_LAT  = 48.231978
CENTER_LON  = 11.608821
SIZE_M      = 100

FETCH_N     = 10       # 10×10 = 100 point query grid → fits in one API call
TARGET_N    = 101      # render grid  (1 m spacing)
Z_EXAG      = 5.0      # vertical exaggeration — Munich plateau is very flat

# OSM zoom 17 → ~0.794 m/pixel at lat 48° → 100 m ≈ 126 pixels
# We fetch a 2×2 tile block (512×512 px ≈ 407×407 m) for safe coverage.
OSM_ZOOM    = 17
_TILE_PX    = 256          # standard OSM tile size
_R_EARTH    = 6_378_137.0  # WGS-84 equatorial radius [m]

# ── Cache ─────────────────────────────────────────────────────────────────────
_CACHE     = Path(__file__).parent / "cache"
_ELEV_FILE = _CACHE / f"elev_{CENTER_LAT:.5f}_{CENTER_LON:.5f}.npy"
_COLS_FILE = _CACHE / f"osm_colors_{CENTER_LAT:.5f}_{CENTER_LON:.5f}_z{OSM_ZOOM}.npy"
_TILE_FILE = _CACHE / "osm_tile.png"   # single center tile for the minimap

# ── Coordinate helpers ────────────────────────────────────────────────────────

def _mpd_lat() -> float:
    return 111_320.0


def _mpd_lon(lat: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat))


def _meters_per_pixel(zoom: int, lat: float) -> float:
    """Ground resolution in metres per pixel for OSM zoom level."""
    return (2 * math.pi * _R_EARTH * math.cos(math.radians(lat))) / (_TILE_PX * (1 << zoom))


def _tile_xy(zoom: int, lat: float = CENTER_LAT,
             lon: float = CENTER_LON) -> tuple[int, int]:
    """Return (tile_x, tile_y) OSM tile index."""
    n     = 1 << zoom
    x     = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y     = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def _center_pixel_in_tile(zoom: int,
                           lat: float = CENTER_LAT,
                           lon: float = CENTER_LON) -> tuple[float, float]:
    """Return (px, py) pixel offset of the coordinate within its tile [0, 256)."""
    n     = 1 << zoom
    tx    = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    ty    = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return (tx - int(tx)) * _TILE_PX, (ty - int(ty)) * _TILE_PX


# ── Elevation ─────────────────────────────────────────────────────────────────

def _fetch_elevation_api() -> Optional[np.ndarray]:
    import requests

    half = SIZE_M / 2.0
    lats = np.linspace(CENTER_LAT - half / _mpd_lat(),
                       CENTER_LAT + half / _mpd_lat(),  FETCH_N)
    lons = np.linspace(CENTER_LON - half / _mpd_lon(CENTER_LAT),
                       CENTER_LON + half / _mpd_lon(CENTER_LAT), FETCH_N)
    LON_G, LAT_G = np.meshgrid(lons, lats)

    locations = [
        {"latitude": float(LAT_G[i, j]), "longitude": float(LON_G[i, j])}
        for i in range(FETCH_N) for j in range(FETCH_N)
    ]
    try:
        r = requests.post(
            "https://api.opentopodata.org/v1/srtm30m",
            json={"locations": locations},
            timeout=20,
            headers={"User-Agent": "field3d-gui/1.0 (educational project)"},
        )
        r.raise_for_status()
        elev = [pt["elevation"] or 0.0 for pt in r.json()["results"]]
        return np.array(elev, dtype=np.float32).reshape(FETCH_N, FETCH_N)
    except Exception as exc:
        print(f"[terrain_real] Elevation API error: {exc}")
        return None


def _bilinear_upsample(Z: np.ndarray, n: int) -> np.ndarray:
    """Upsample (k, k) → (n, n) using bilinear interpolation (numpy only)."""
    k  = Z.shape[0]
    xi = np.linspace(0, k - 1, n)
    Z1 = np.array([np.interp(xi, np.arange(k), row) for row in Z], dtype=np.float32)
    Z2 = np.array([np.interp(xi, np.arange(k), Z1[:, j]) for j in range(n)],
                  dtype=np.float32).T
    return Z2


def get_elevation_grid() -> Optional[np.ndarray]:
    """Return (TARGET_N, TARGET_N) float32 relative heights [m] (cached)."""
    _CACHE.mkdir(parents=True, exist_ok=True)

    if _ELEV_FILE.exists():
        print(f"[terrain_real] Using cached elevation ({_ELEV_FILE.name})")
        Z_raw = np.load(str(_ELEV_FILE))
    else:
        print("[terrain_real] Fetching SRTM-30m elevation …")
        Z_raw = _fetch_elevation_api()
        if Z_raw is None:
            return None
        np.save(str(_ELEV_FILE), Z_raw)
        print(f"[terrain_real] Cached → {_ELEV_FILE.name}")

    Z_fine = _bilinear_upsample(Z_raw, TARGET_N)
    Z_rel  = (Z_fine - Z_fine.mean()) * Z_EXAG
    Z_rel -= Z_rel.min()
    Z_rel += 0.10
    return Z_rel.astype(np.float32)


# ── OSM map colours ───────────────────────────────────────────────────────────

def _fetch_tile_bytes(zoom: int, tx: int, ty: int,
                      cache_file: Optional[Path] = None) -> Optional[bytes]:
    """Download one OSM tile PNG with optional file cache."""
    if cache_file and cache_file.exists():
        return cache_file.read_bytes()
    try:
        import requests
        url = f"https://tile.openstreetmap.org/{zoom}/{tx}/{ty}.png"
        r = requests.get(url, timeout=10,
                         headers={"User-Agent": "field3d-gui/1.0 (educational project)"})
        r.raise_for_status()
        if cache_file:
            cache_file.write_bytes(r.content)
        return r.content
    except Exception as exc:
        print(f"[terrain_real] Tile ({zoom}/{tx}/{ty}) error: {exc}")
        return None


def get_osm_colors_for_field() -> Optional[np.ndarray]:
    """
    Return (TARGET_N, TARGET_N, 4) float32 RGBA array of OSM map colours
    covering the SIZE_M × SIZE_M field.

    Approach
    ────────
    1. Fetch a 2×2 block of tiles at OSM_ZOOM centred near CENTER_LAT/LON.
    2. Stitch into a 512×512 RGBA image.
    3. Crop the rectangle corresponding to SIZE_M × SIZE_M metres.
    4. Flip vertically so OSM-north aligns with terrain Y-max (North).
    5. Resample to TARGET_N × TARGET_N and transpose axes to match
       GLSurfacePlotItem colors[i,j] = colour at xs[i], ys[j].
    6. Cache result as .npy for instant reuse.
    """
    _CACHE.mkdir(parents=True, exist_ok=True)

    if _COLS_FILE.exists():
        print(f"[terrain_real] Using cached OSM colours ({_COLS_FILE.name})")
        return np.load(str(_COLS_FILE))

    print(f"[terrain_real] Fetching OSM tiles z{OSM_ZOOM} (2×2 block) …")
    try:
        from PIL import Image
    except ImportError:
        print("[terrain_real] Pillow not installed — run:  pip install Pillow")
        return None

    # ── choose 2×2 tile block so center has ≥ half-tile margin ──────────
    tx_c, ty_c = _tile_xy(OSM_ZOOM)
    px_c, py_c = _center_pixel_in_tile(OSM_ZOOM)

    tx_start = tx_c if px_c >= _TILE_PX // 2 else tx_c - 1
    ty_start = ty_c if py_c >= _TILE_PX // 2 else ty_c - 1

    # center pixel within the 512×512 stitched image
    cx_stitch = int(px_c + (tx_c - tx_start) * _TILE_PX)
    cy_stitch = int(py_c + (ty_c - ty_start) * _TILE_PX)

    # ── fetch and stitch ─────────────────────────────────────────────────
    canvas = Image.new("RGBA", (_TILE_PX * 2, _TILE_PX * 2), (0, 0, 0, 0))
    ok = False
    for dy in range(2):
        for dx in range(2):
            ttx, tty = tx_start + dx, ty_start + dy
            cf   = _CACHE / f"tile_z{OSM_ZOOM}_{ttx}_{tty}.png"
            data = _fetch_tile_bytes(OSM_ZOOM, ttx, tty, cache_file=cf)
            if data:
                tile_img = Image.open(io.BytesIO(data)).convert("RGBA")
                canvas.paste(tile_img, (dx * _TILE_PX, dy * _TILE_PX))
                ok = True
    if not ok:
        print("[terrain_real] Could not fetch any OSM tiles.")
        return None

    # ── also save centre tile for the minimap widget ─────────────────────
    cf_center = _CACHE / f"tile_z{OSM_ZOOM}_{tx_c}_{ty_c}.png"
    if cf_center.exists() and not _TILE_FILE.exists():
        _TILE_FILE.write_bytes(cf_center.read_bytes())

    # ── crop SIZE_M × SIZE_M centred at (cx_stitch, cy_stitch) ──────────
    mpp     = _meters_per_pixel(OSM_ZOOM, CENTER_LAT)
    half_px = SIZE_M / mpp / 2.0          # half-width in pixels
    x0 = max(0, int(cx_stitch - half_px))
    y0 = max(0, int(cy_stitch - half_px))
    x1 = min(_TILE_PX * 2, int(cx_stitch + half_px))
    y1 = min(_TILE_PX * 2, int(cy_stitch + half_px))
    crop = canvas.crop((x0, y0, x1, y1))

    # ── resize and orient ────────────────────────────────────────────────
    # PIL stores rows top→bottom (y=0 = North in OSM).
    # Terrain ys go 0→100 = South→North, so flip vertically.
    crop_resized = crop.resize((TARGET_N, TARGET_N), Image.LANCZOS)
    crop_flipped = crop_resized.transpose(Image.FLIP_TOP_BOTTOM)

    # GLSurfacePlotItem colors[i, j] = colour at xs[i], ys[j].
    # numpy image arr[row, col] = pixel at (y=row, x=col).
    # After flip: row=0 → South, row=TARGET_N-1 → North.
    # We need arr[col, row] so that arr[i, j] = colour at xs[i], ys[j].
    arr = np.array(crop_flipped, dtype=np.float32) / 255.0  # (T, T, 4)
    arr = arr.transpose(1, 0, 2)                            # (T, T, 4)

    np.save(str(_COLS_FILE), arr)
    print(f"[terrain_real] OSM colours cached → {_COLS_FILE.name}")
    return arr


# ── Minimap tile bytes (for gui/minimap.py) ───────────────────────────────────

def get_osm_tile_bytes() -> Optional[bytes]:
    """Return PNG bytes of the OSM center tile at OSM_ZOOM for the minimap."""
    _CACHE.mkdir(parents=True, exist_ok=True)
    if _TILE_FILE.exists():
        return _TILE_FILE.read_bytes()
    tx, ty = _tile_xy(OSM_ZOOM)
    return _fetch_tile_bytes(OSM_ZOOM, tx, ty, cache_file=_TILE_FILE)
