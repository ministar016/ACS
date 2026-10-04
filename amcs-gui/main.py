import sys
import os
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


def main():
    _setup_packaged_app()
    from sim.bus import SimBus          # after config.env: SimBus reads the environment

    app = QGuiApplication(sys.argv)
    app.setApplicationName("AMCS")
    app.setOrganizationName("AMCS C2")
    icon = paths.resource_dir() / "packaging" / "amcs.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    engine = QQmlApplicationEngine()

    # Expose simulation bus to QML before loading
    bus = SimBus(dt=0.1, parent=app)
    engine.rootContext().setContextProperty("simBus", bus)

    qml_path = paths.resource_dir() / "AMCSDashboard.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))

    if not engine.rootObjects():
        print("Error: Could not load QML file.")
        sys.exit(-1)

    # Retract threat markers published to artemides-trax before exiting
    app.aboutToQuit.connect(bus.shutdown)
    bus.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
