import sys
import os
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtCore import QUrl

# Add amcs-gui to path so sim/ package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim.bus import SimBus


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("AMCS")
    app.setOrganizationName("AMCS C2")

    engine = QQmlApplicationEngine()

    # Expose simulation bus to QML before loading
    bus = SimBus(dt=0.1, parent=app)
    engine.rootContext().setContextProperty("simBus", bus)

    qml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "AMCSDashboard.qml")
    engine.load(QUrl.fromLocalFile(qml_path))

    if not engine.rootObjects():
        print("Error: Could not load QML file.")
        sys.exit(-1)

    bus.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
