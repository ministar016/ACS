"""
Map tile cache for the 2D map — tiles are fetched in Python and handed to
QML as local files.

tile.openstreetmap.org answers requests without an identifying User-Agent
with "418 — Access blocked, app is not following the tile usage policy",
and the policy asks clients to cache tiles.  Qt's own network manager sends
no such User-Agent, and a Python QQmlNetworkAccessManagerFactory deadlocks
when the QML engine shuts down — so the map asks TileCache.url(kind, z, x, y):
  • cached on disk → the file:// URL right away
  • otherwise ""   → downloaded on a worker thread (User-Agent below), then
    tileReady is emitted and the map repaints
Failed tiles (HTTP error, no network) are not retried for RETRY_S.
"""
from __future__ import annotations
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from . import paths

USER_AGENT = "AMCS-C2/1.0 (+https://github.com/ministar016/ACS; C-UAS command & control simulation)"
RETRY_S = 60.0

SOURCES = {
    "satellite": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "topo":      "https://tile.opentopomap.org/{z}/{x}/{y}.png",
    "osm":       "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
}


def _download(url: str, path: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)


class TileCache(QObject):
    tileReady = pyqtSignal(str)          # file URL of a tile that just arrived

    def __init__(self, parent: QObject | None = None, root: Path | None = None) -> None:
        super().__init__(parent)
        self._root = root or paths.cache_dir() / "tiles"
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tiles")
        self._inflight: dict[Path, object] = {}
        self._failed: dict[Path, float] = {}
        self._poll = QTimer(self)
        self._poll.setInterval(100)
        self._poll.timeout.connect(self._collect)

    @pyqtSlot(str, int, int, int, result=str)
    def url(self, kind: str, z: int, x: int, y: int) -> str:
        src = SOURCES.get(kind)
        if src is None:
            return ""
        path = self._root / kind / str(z) / str(x) / f"{y}.{'jpg' if kind == 'satellite' else 'png'}"
        if path.exists():
            return path.resolve().as_uri()
        if path in self._inflight or time.monotonic() - self._failed.get(path, -1e9) < RETRY_S:
            return ""
        self._inflight[path] = self._pool.submit(_download, src.format(z=z, x=x, y=y), path)
        if not self._poll.isActive():
            self._poll.start()
        return ""

    def _collect(self) -> None:
        for path, fut in list(self._inflight.items()):
            if not fut.done():
                continue
            del self._inflight[path]
            try:
                fut.result()
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                self._failed[path] = time.monotonic()
                print(f"[tiles] {path.relative_to(self._root)}: {e}")
                continue
            self.tileReady.emit(path.resolve().as_uri())
        if not self._inflight:
            self._poll.stop()

    def shutdown(self) -> None:
        self._poll.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)
