"""
3D terrain for the dashboard — elevation + satellite imagery around the base.

Sources (no API key):
  elevation  AWS Terrain Tiles, terrarium encoding (SRTM/ASTER-based, ~30 m)
             https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png
             height = R·256 + G + B/256 − 32768  [m]
  imagery    Esri World Imagery — the same tiles as the 2D map's SAT layer

TerrainProvider downloads on a worker thread, caches everything under the
AMCS cache dir and emits terrainUpdated({...}) with a regular elevation grid
(row 0 = north) and a stitched texture covering exactly the same box.

TerrainGeometry is a Quick3D mesh built from that grid in metres:
x = east, y = up (× exaggeration), z = south, origin at the box centre —
so QML can place anything with the same lat/lon → x/z conversion.  The
provider owns the mesh and QML uses it as the context property
`terrainMesh` (a Python QQuick3DGeometry subclass instantiated *from QML*
crashes PyQt6, created in Python it works).
"""
from __future__ import annotations
import hashlib
import json
import math
import struct
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import Qt, QObject, QTimer, QRectF, QUrl, pyqtProperty, pyqtSignal, pyqtSlot, QVariant
from PyQt6.QtGui import QImage, QPainter, QVector3D
from PyQt6.QtQuick3D import QQuick3DGeometry

from . import paths

DEM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
SAT_URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/"
           "MapServer/tile/{z}/{y}/{x}")
DEM_ZOOM = 12            # ~30 m/px at 42° N
SAT_ZOOM = 14            # ~7 m/px
GRID     = 181           # vertices per side
TEX_MAX  = 4096
_M_PER_DEG_LAT = 111_320.0
from .tiles import USER_AGENT as _UA


def _tile_xy(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    y = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    return x, y


def _fetch(url: str, path: Path) -> bytes:
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def build_terrain(lat0: float, lon0: float, half_m: float, cache: Path, progress=None) -> dict:
    """Elevation grid + texture for the square ±half_m around (lat0, lon0)."""
    dlat = half_m / _M_PER_DEG_LAT
    dlon = half_m / (_M_PER_DEG_LAT * math.cos(math.radians(lat0)))
    lat_min, lat_max, lon_min, lon_max = lat0 - dlat, lat0 + dlat, lon0 - dlon, lon0 + dlon
    key = hashlib.sha1(f"{lat0:.5f}|{lon0:.5f}|{half_m:.0f}|{GRID}|{SAT_ZOOM}".encode()).hexdigest()[:12]
    meta_path = cache / f"terrain_{key}.json"
    tex_path = cache / f"terrain_{key}.jpg"
    if meta_path.exists() and tex_path.exists():
        return json.loads(meta_path.read_text())

    tiles_dir = cache / "tiles"
    pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="terrain")

    def tile_range(z):
        x0, y0 = _tile_xy(lat_max, lon_min, z)
        x1, y1 = _tile_xy(lat_min, lon_max, z)
        return (x0, y0, x1, y1), [(x, y) for y in range(int(y0), int(y1) + 1)
                                  for x in range(int(x0), int(x1) + 1)]

    # ── elevation ────────────────────────────────────────────────────────
    _, dem_tiles = tile_range(DEM_ZOOM)
    sat_box, sat_tiles = tile_range(SAT_ZOOM)
    total = len(dem_tiles) + len(sat_tiles)
    done = [0]

    def get(url_fmt, z, x, y, sub):
        data = _fetch(url_fmt.format(z=z, x=x, y=y), tiles_dir / sub / f"{z}_{x}_{y}")
        done[0] += 1
        if progress:
            progress(done[0], total)
        return (x, y), data

    dem_imgs = {}
    for (x, y), data in pool.map(lambda t: get(DEM_URL, DEM_ZOOM, t[0], t[1], "dem"), dem_tiles):
        img = QImage()
        img.loadFromData(data)
        dem_imgs[(x, y)] = img.convertToFormat(QImage.Format.Format_RGB32)

    def elev_at(lat, lon):
        fx, fy = _tile_xy(lat, lon, DEM_ZOOM)
        px, py = fx * 256 - 0.5, fy * 256 - 0.5
        ix, iy = math.floor(px), math.floor(py)
        ax, ay = px - ix, py - iy

        def h(gx, gy):
            img = dem_imgs.get((gx // 256, gy // 256))
            if img is None:
                return 0.0
            c = img.pixel(gx % 256, gy % 256)
            return ((c >> 16) & 255) * 256 + ((c >> 8) & 255) + (c & 255) / 256 - 32768
        return ((h(ix, iy) * (1 - ax) + h(ix + 1, iy) * ax) * (1 - ay) +
                (h(ix, iy + 1) * (1 - ax) + h(ix + 1, iy + 1) * ax) * ay)

    heights = []
    for r in range(GRID):
        lat = lat_max - (lat_max - lat_min) * r / (GRID - 1)
        for c in range(GRID):
            lon = lon_min + (lon_max - lon_min) * c / (GRID - 1)
            heights.append(round(elev_at(lat, lon), 1))

    # ── imagery: stitch, crop to the box, save as one texture ───────────
    (x0, y0, x1, y1) = sat_box
    tx0, ty0 = int(x0), int(y0)
    mosaic = QImage((int(x1) - tx0 + 1) * 256, (int(y1) - ty0 + 1) * 256, QImage.Format.Format_RGB32)
    mosaic.fill(0x1A2A3A)
    painter = QPainter(mosaic)
    for (x, y), data in pool.map(lambda t: get(SAT_URL, SAT_ZOOM, t[0], t[1], "sat"), sat_tiles):
        img = QImage()
        if img.loadFromData(data):
            painter.drawImage((x - tx0) * 256, (y - ty0) * 256, img)
    painter.end()
    pool.shutdown()
    crop = QRectF((x0 - tx0) * 256, (y0 - ty0) * 256, (x1 - x0) * 256, (y1 - y0) * 256).toRect()
    tex = mosaic.copy(crop)
    if max(tex.width(), tex.height()) > TEX_MAX:
        tex = tex.scaled(TEX_MAX, TEX_MAX)
    tex.save(str(tex_path), "JPG", 90)

    meta = {
        "status": "ready", "ready": True,
        "centerLat": lat0, "centerLon": lon0,
        "bbox": {"latMin": lat_min, "latMax": lat_max, "lonMin": lon_min, "lonMax": lon_max},
        "widthM": 2 * half_m, "depthM": 2 * half_m,
        "cols": GRID, "rows": GRID, "heights": heights,
        "minM": min(heights), "maxM": max(heights),
        "textureUrl": tex_path.resolve().as_uri(),
        "source": "AWS Terrain Tiles (terrarium) + Esri World Imagery",
    }
    meta_path.write_text(json.dumps(meta))
    return meta


class TerrainProvider(QObject):
    """Loads terrain off the GUI thread; QML calls load() and binds to terrainUpdated."""
    terrainUpdated = pyqtSignal(QVariant)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.mesh = TerrainGeometry()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="terrain-build")
        self._future = None
        self._progress = (0, 0)
        self._key = None
        self._poll = QTimer(self)
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._check)

    @pyqtSlot(float, float, float)
    def load(self, lat: float, lon: float, half_m: float) -> None:
        key = (round(lat, 5), round(lon, 5), round(half_m))
        if key == self._key or (self._future is not None and not self._future.done()):
            return
        self._key = key
        self._progress = (0, 0)

        def progress(i, n):
            self._progress = (i, n)
        self._future = self._pool.submit(build_terrain, lat, lon, half_m,
                                         paths.cache_dir() / "terrain", progress)
        self.terrainUpdated.emit({"status": "loading…", "ready": False})
        self._poll.start()

    def _check(self) -> None:
        fut = self._future
        if fut is None:
            return
        if not fut.done():
            i, n = self._progress
            if n:
                self.terrainUpdated.emit({"status": f"loading tiles {i}/{n}", "ready": False})
            return
        self._poll.stop()
        self._future = None
        try:
            meta = fut.result()
            self.mesh.terrain = meta
            self.terrainUpdated.emit(meta)
        except Exception as e:
            self._key = None
            self.terrainUpdated.emit({"status": f"unavailable: {e}", "ready": False})

    @pyqtSlot(str, result=str)
    def smooth(self, url: str) -> str:
        """
        A coarse grid overlay (one pixel per cell, e.g. the drivability layer)
        upscaled with bilinear interpolation, so cell edges blend into each
        other instead of showing as blocks when the map is zoomed in.
        """
        if not url:
            return ""
        path = paths.cache_dir() / "terrain" / f"smooth_{hashlib.sha1(url.encode()).hexdigest()[:12]}.png"
        if not path.exists():
            src = QImage(QUrl(url).toLocalFile())
            if src.isNull():
                return ""
            k = max(1, min(8, 4096 // max(src.width(), src.height())))
            big = src.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied).scaled(
                src.width() * k, src.height() * k,
                Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            path.parent.mkdir(parents=True, exist_ok=True)
            big.save(str(path), "PNG")
        return path.resolve().as_uri()

    @pyqtSlot(str, QVariant, result=str)
    def drape(self, url: str, bbox) -> str:
        """
        An overlay PNG with its own lat/lon box (e.g. the drivability layer)
        re-mapped onto the terrain box, so it can use the terrain mesh's UVs.
        Transparent outside the overlay.  Returns a file URL ("" if no terrain).
        """
        t = self.mesh.terrain
        if not t or not t.get("ready") or not url:
            return ""
        if hasattr(bbox, "toVariant"):
            bbox = bbox.toVariant()
        src = QImage(QUrl(url).toLocalFile())
        if src.isNull():
            return ""
        tb, n = t["bbox"], 2048
        out = QImage(n, n, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(0)
        w_t, h_t = tb["lonMax"] - tb["lonMin"], tb["latMax"] - tb["latMin"]
        rect = QRectF((bbox["lonMin"] - tb["lonMin"]) / w_t * n, (tb["latMax"] - bbox["latMax"]) / h_t * n,
                      (bbox["lonMax"] - bbox["lonMin"]) / w_t * n, (bbox["latMax"] - bbox["latMin"]) / h_t * n)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)   # cells blend, no blocks
        painter.drawImage(rect, src)
        painter.end()
        key = hashlib.sha1(f"{url}|{tb}".encode()).hexdigest()[:12]
        path = paths.cache_dir() / "terrain" / f"drape_{key}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        out.save(str(path), "PNG")
        return path.resolve().as_uri()

    @pyqtSlot(QVariant, result=str)
    def drapeLines(self, lines) -> str:
        """Border lines [[{lat, lon}]] drawn into a transparent texture over the terrain box."""
        t = self.mesh.terrain
        if not t or not t.get("ready"):
            return ""
        if hasattr(lines, "toVariant"):
            lines = lines.toVariant()
        if not lines:
            return ""
        from PyQt6.QtGui import QPen, QColor, QPainterPath
        tb, n = t["bbox"], 2048
        w_t, h_t = tb["lonMax"] - tb["lonMin"], tb["latMax"] - tb["latMin"]
        out = QImage(n, n, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(0)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for ln in lines:
            path = QPainterPath()
            for k, pt in enumerate(ln):
                x = (pt["lon"] - tb["lonMin"]) / w_t * n
                y = (tb["latMax"] - pt["lat"]) / h_t * n
                path.moveTo(x, y) if k == 0 else path.lineTo(x, y)
            painter.setPen(QPen(QColor(0, 0, 0, 150), 9))
            painter.drawPath(path)
            pen = QPen(QColor(255, 82, 82, 240), 5)
            pen.setDashPattern([4, 2])
            painter.setPen(pen)
            painter.drawPath(path)
        painter.end()
        key = hashlib.sha1(f"{json.dumps(lines)}|{tb}".encode()).hexdigest()[:12]
        path = paths.cache_dir() / "terrain" / f"border_{key}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        out.save(str(path), "PNG")
        return path.resolve().as_uri()

    def shutdown(self) -> None:
        self._poll.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)


class TerrainGeometry(QQuick3DGeometry):
    """Triangle mesh of the elevation grid (positions, normals, UVs) in metres."""
    terrainChanged = pyqtSignal()
    exaggerationChanged = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._terrain = None
        self._exaggeration = 1.5

    @pyqtProperty(QVariant, notify=terrainChanged)
    def terrain(self):
        return self._terrain

    @terrain.setter
    def terrain(self, t) -> None:
        if hasattr(t, "toVariant"):
            t = t.toVariant()
        self._terrain = t
        self.terrainChanged.emit()
        self._rebuild()

    @pyqtProperty(float, notify=exaggerationChanged)
    def exaggeration(self) -> float:
        return self._exaggeration

    @exaggeration.setter
    def exaggeration(self, v: float) -> None:
        if v != self._exaggeration:
            self._exaggeration = v
            self.exaggerationChanged.emit()
            self._rebuild()

    def _rebuild(self) -> None:
        t = self._terrain
        if not t or not t.get("ready"):
            return
        cols, rows = int(t["cols"]), int(t["rows"])
        w, d = float(t["widthM"]), float(t["depthM"])
        base = float(t["minM"])
        k = self._exaggeration
        hs = t["heights"]
        dx, dz = w / (cols - 1), d / (rows - 1)
        ys = [(h - base) * k for h in hs]
        verts = bytearray()
        pack = struct.Struct("<8f").pack
        for r in range(rows):
            z = -d / 2 + r * dz
            for c in range(cols):
                i = r * cols + c
                # central-difference normal
                hl = ys[i - 1] if c > 0 else ys[i]
                hr = ys[i + 1] if c < cols - 1 else ys[i]
                hu = ys[i - cols] if r > 0 else ys[i]
                hd = ys[i + cols] if r < rows - 1 else ys[i]
                nx, ny, nz = (hl - hr) / (2 * dx), 1.0, (hu - hd) / (2 * dz)
                inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
                verts += pack(-w / 2 + c * dx, ys[i], z, nx * inv, ny * inv, nz * inv,
                              c / (cols - 1), 1.0 - r / (rows - 1))
        idx = bytearray()
        ipack = struct.Struct("<6I").pack
        for r in range(rows - 1):
            for c in range(cols - 1):
                a = r * cols + c
                b, cc, dd = a + 1, a + cols, a + cols + 1
                idx += ipack(a, cc, b, b, cc, dd)
        self.clear()
        self.setStride(32)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        A = QQuick3DGeometry.Attribute
        self.addAttribute(A.Semantic.PositionSemantic, 0, A.ComponentType.F32Type)
        self.addAttribute(A.Semantic.NormalSemantic, 12, A.ComponentType.F32Type)
        self.addAttribute(A.Semantic.TexCoord0Semantic, 24, A.ComponentType.F32Type)
        self.addAttribute(A.Semantic.IndexSemantic, 0, A.ComponentType.U32Type)
        self.setVertexData(bytes(verts))
        self.setIndexData(bytes(idx))
        self.setBounds(QVector3D(-w / 2, 0, -d / 2), QVector3D(w / 2, max(ys), d / 2))
        self.update()
