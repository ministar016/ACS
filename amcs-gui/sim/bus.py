"""
SimBus — Qt signal bridge between the Scenario and the QML dashboard.

Architecture
────────────
SimBus (QObject)
  ├── QTimer (10 Hz) → calls _tick()
  ├── _tick() runs Scenario.step() in the Qt event loop
  └── emits typed pyqtSignals → QML binds via setContextProperty

Each signal carries a Python dict of JSON-serialisable values that
QML maps to its properties.  This keeps the QML layer loosely coupled
from the Python model classes.

Usage
─────
    bus = SimBus()
    engine.rootContext().setContextProperty("simBus", bus)
    bus.start()
"""
from __future__ import annotations
import json
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot, QVariant
from .scenario import Scenario
from .models   import ThreatLevel


class SimBus(QObject):
    # ── Signals ───────────────────────────────────────────────────────────
    # Each signal carries a QVariant (Python dict) for easy QML consumption.

    # UAV / UGV telemetry
    uavUpdated = pyqtSignal(QVariant)   # UAVTelemetry as dict
    ugvUpdated = pyqtSignal(QVariant)   # UGVTelemetry as dict

    # Acoustic x3 and Seismic x3  (list of dicts)
    acousticUpdated = pyqtSignal(QVariant)
    seismicUpdated  = pyqtSignal(QVariant)

    # Fused track (list of dicts — typically 0 or 1 entries)
    tracksUpdated = pyqtSignal(QVariant)

    # Threat level (int 0–3)
    threatUpdated = pyqtSignal(int)

    # Target ground truth — useful for debugging / map overlay
    targetUpdated = pyqtSignal(QVariant)

    # ── Construction ──────────────────────────────────────────────────────

    def __init__(self, dt: float = 0.1, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._scenario = Scenario(dt=dt)
        self._timer    = QTimer(self)
        self._timer.setInterval(int(dt * 1000))  # ms
        self._timer.timeout.connect(self._tick)

    # ── Public slots (callable from QML) ─────────────────────────────────

    @pyqtSlot()
    def start(self) -> None:
        self._timer.start()

    @pyqtSlot()
    def stop(self) -> None:
        self._timer.stop()

    @pyqtSlot()
    def reset(self) -> None:
        self._timer.stop()
        self._scenario = Scenario(dt=self._scenario._dt)
        self._timer.start()

    # ── Private tick ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        snap = self._scenario.step()

        # UAV
        uav = snap.uav_telemetry
        uav_d: dict = {
            "deviceId":   uav.device_id,
            "timestamp":  uav.timestamp,
            "lat":        round(uav.position.lat, 6),
            "lon":        round(uav.position.lon, 6),
            "altitudeM":  round(uav.altitude_m, 1),
            "speedMs":    round(uav.speed_ms, 2),
            "headingDeg": uav.heading_deg,
            "batteryPct": uav.battery_pct,
            "status":     uav.status.name,
            "radar": {
                "detected":    uav.radar.target_detected if uav.radar else False,
                "distanceM":   uav.radar.distance_m      if uav.radar else 0.0,
                "azimuth":     uav.radar.azimuth_deg      if uav.radar else 0.0,
                "velocity":    uav.radar.radial_velocity_ms if uav.radar else 0.0,
                "confidence":  uav.radar.detection_confidence if uav.radar else 0.0,
            } if uav.radar else {},
            "camera": {
                "detected":    uav.camera.target_detected if uav.camera else False,
                "class":       uav.camera.object_class     if uav.camera else "",
                "distanceM":   uav.camera.estimated_distance_m if uav.camera else 0.0,
                "confidence":  uav.camera.confidence       if uav.camera else 0.0,
            } if uav.camera else {},
        }
        self.uavUpdated.emit(uav_d)

        # UGV
        ugv = snap.ugv_telemetry
        ugv_d: dict = {
            "deviceId":   ugv.device_id,
            "timestamp":  ugv.timestamp,
            "lat":        round(ugv.position.lat, 6),
            "lon":        round(ugv.position.lon, 6),
            "speedMs":    round(ugv.speed_ms, 2),
            "headingDeg": ugv.heading_deg,
            "batteryPct": ugv.battery_pct,
            "status":     ugv.status.name,
            "terrainMode":ugv.terrain_mode,
            "radar": {
                "detected":   ugv.radar.target_detected  if ugv.radar else False,
                "distanceM":  ugv.radar.distance_m       if ugv.radar else 0.0,
                "azimuth":    ugv.radar.azimuth_deg       if ugv.radar else 0.0,
                "velocity":   ugv.radar.radial_velocity_ms if ugv.radar else 0.0,
                "confidence": ugv.radar.detection_confidence if ugv.radar else 0.0,
            } if ugv.radar else {},
        }
        self.ugvUpdated.emit(ugv_d)

        # Acoustic x3
        self.acousticUpdated.emit([
            {
                "sensorId":    r.sensor_id,
                "amplitudeDb": r.amplitude_db,
                "bearing":     r.estimated_bearing,
                "freqHz":      round(r.frequency_hz, 1),
                "confidence":  r.detection_confidence,
                "detected":    r.target_detected,
            }
            for r in snap.acoustic_readings
        ])

        # Seismic x3
        self.seismicUpdated.emit([
            {
                "sensorId":   r.sensor_id,
                "amplitudeG": r.amplitude_g,
                "bearing":    r.estimated_bearing,
                "confidence": r.detection_confidence,
                "detected":   r.target_detected,
            }
            for r in snap.seismic_readings
        ])

        # Fused tracks
        self.tracksUpdated.emit([
            {
                "trackId":    t.track_id,
                "lat":        round(t.position.lat, 6),
                "lon":        round(t.position.lon, 6),
                "speedMs":    round(t.velocity.speed_ms, 2),
                "headingDeg": round(t.velocity.heading_deg, 1),
                "confidence": t.confidence,
                "threatLevel":t.threat_level.name,
                "sources":    t.sensor_sources,
            }
            for t in snap.tracks
        ])

        # Threat level
        self.threatUpdated.emit(snap.threat_level.value)

        # Ground truth (debug)
        self.targetUpdated.emit({
            "lat": round(snap.target_position.lat, 6),
            "lon": round(snap.target_position.lon, 6),
            "alive": self._scenario.target.alive,
        })
