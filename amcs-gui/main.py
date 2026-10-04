import sys
import os
import multiprocessing
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtCore import QUrl

# Add amcs-gui to path so sim/ package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import paths


def _setup_packaged_app() -> None:
    """A Finder-launched app has no terminal and no shell environment."""
    if paths.frozen():
        log_dir = paths.log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log = open(log_dir / "amcs.log", "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = log
    cfg = paths.load_config_env()
    print(f"[amcs] config: {cfg}  scenarios: {paths.scenario_dir()}  cache: {paths.cache_dir()}")


def load_symbols() -> dict:
    """NATO symbols for the lists (symbols/*.svg) and plain map icons (icons/*.svg) for QML."""
    import json
    d = paths.resource_dir() / "symbols"
    meta = json.loads((d / "symbols.json").read_text(encoding="utf-8")) if (d / "symbols.json").exists() else {}
    icons = paths.resource_dir() / "icons"
    return {"base": d.resolve().as_uri() + "/", "meta": meta, "icons": icons.resolve().as_uri() + "/"}


def main():
    multiprocessing.freeze_support()    # packaged app: the sim worker is a re-launch of this binary
    _setup_packaged_app()
    from sim.bus import SimBus          # after config.env: SimBus reads the environment
    from sim.terrain import TerrainProvider

    app = QGuiApplication(sys.argv)
    app.setApplicationName("AMCS")
    app.setOrganizationName("AMCS C2")
    icon = paths.resource_dir() / "packaging" / "amcs.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    engine = QQmlApplicationEngine()

    # Expose simulation bus to QML before loading; the simulation itself runs
    # in its own process (sim/worker.py) so the dashboard never waits on it
    bus = SimBus(dt=0.1, parent=app)
    engine.rootContext().setContextProperty("simBus", bus)
    # 3D terrain view: elevation + imagery loader and the mesh Map3D.qml draws
    terrain = TerrainProvider(parent=app)
    engine.rootContext().setContextProperty("terrainProvider", terrain)
    engine.rootContext().setContextProperty("terrainMesh", terrain.mesh)
    engine.rootContext().setContextProperty("symbolsInfo", load_symbols())
    # 2D map tiles: fetched in Python (identifying User-Agent, disk cache) — OSM blocks Qt's default
    from sim.tiles import TileCache
    tiles = TileCache(parent=app)
    engine.rootContext().setContextProperty("tileCache", tiles)

    qml_path = paths.resource_dir() / "AMCSDashboard.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))

    if not engine.rootObjects():
        print("Error: Could not load QML file.")
        sys.exit(-1)

    # Retract threat markers published to artemides-trax before exiting
    app.aboutToQuit.connect(bus.shutdown)
    app.aboutToQuit.connect(terrain.shutdown)
    app.aboutToQuit.connect(tiles.shutdown)
    bus.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
