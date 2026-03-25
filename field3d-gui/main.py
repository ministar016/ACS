"""
Field-3D GUI — entry point.

Usage
─────
    python main.py
    # or
    ./run.sh
"""
import sys
import os

# Ensure 'sim' and 'gui' packages are importable from this directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui     import QSurfaceFormat

from sim.terrain      import TerrainMap
from sim.terrain_real import get_elevation_grid, get_osm_colors_for_field
from sim.bus          import SimBus
from gui.main_window  import MainWindow


def main() -> None:
    # ── OpenGL quality: MSAA 8×, 24-bit depth, vsync — MUST be before QApplication
    fmt = QSurfaceFormat()
    fmt.setSamples(8)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(fmt)

    pg.setConfigOptions(antialias=True)

    app = QApplication(sys.argv)
    app.setApplicationName("Field-3D")
    app.setOrganizationName("ACS Lab")

    # Build shared objects
    # Fetch real terrain data (loads from cache if already downloaded)
    elev_data  = get_elevation_grid()        # None → procedural fallback in TerrainMap
    map_colors = get_osm_colors_for_field()  # None → height colormap fallback
    terrain    = TerrainMap(seed=42, elev_data=elev_data, map_colors=map_colors)
    texture_src = "OSM z17" if map_colors is not None else "height colormap"
    print(f"[main] Terrain: {terrain.height_label()}  |  texture: {texture_src}")

    bus     = SimBus(dt=0.1, emit_every=3, parent=app)

    window  = MainWindow(bus, terrain)
    window.show()

    bus.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
