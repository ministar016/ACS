"""
SimBus — Qt signal bridge between the Scenario and the QML dashboard.

Architecture
────────────
SimBus (QObject)
  ├── QTimer (10 Hz) → calls _tick()
  ├── _tick() runs Scenario.step() every physics tick
  │     ├── accumulates velocity into a 3-sample rolling buffer
  │     └── emits GUI signals every 5 ticks (≈ 2 Hz) to reduce churn
  └── emits typed pyqtSignals → QML binds via setContextProperty

Velocity smoothing
──────────────────
heading_deg: circular mean over the last 3 track samples — avoids
             the 0°/360° wraparound artefact of a plain arithmetic mean.
speed_ms:    arithmetic mean over the same window.

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
import math
from collections import deque
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

    def __init__(self, dt: float = 0.1, emit_every: int = 5,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._scenario  = Scenario(dt=dt)
        self._timer     = QTimer(self)
        self._timer.setInterval(int(dt * 1000))  # ms
        self._timer.timeout.connect(self._tick)
        # GUI throttle: emit signals every `emit_every` physics ticks
        self._emit_every = emit_every
        self._tick_n     = 0
        # Rolling velocity buffer — smooths heading/speed over last 3 tracks
        self._vel_buf: deque[tuple[float, float]] = deque(maxlen=3)
        # Time acceleration: run this many physics steps per timer fire
        self._time_scale: int = 1

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
        self._tick_n   = 0
        self._vel_buf.clear()
        self._timer.start()

    @pyqtSlot()
    def acceptMission(self) -> None:
        """Operator accepted intercept mission — send UAV toward target."""
        self._scenario.uav.start_intercept()

    @pyqtSlot(int)
    def setTimeScale(self, scale: int) -> None:
        """Set simulation time multiplier (1×, 2×, 5×, 10×, 20×, 50×, …)."""
        self._time_scale = max(1, min(50, scale))

    # ── Private helpers ───────────────────────────────────────────────────

    def _smooth_velocity(self) -> tuple[float, float] | None:
        """
        Returns (speed_ms, heading_deg) averaged over the velocity buffer.
        Heading uses circular mean to avoid 0°/360° wraparound artefacts.
        Returns None if buffer is empty.
        """
        if not self._vel_buf:
            return None
        speeds   = [v[0] for v in self._vel_buf]
        headings = [v[1] for v in self._vel_buf]
        avg_speed = sum(speeds) / len(speeds)
        sin_sum = sum(math.sin(math.radians(h)) for h in headings)
        cos_sum = sum(math.cos(math.radians(h)) for h in headings)
        avg_hdg = math.degrees(math.atan2(sin_sum, cos_sum)) % 360
        return (avg_speed, avg_hdg)

    # ── Private tick ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        # Run _time_scale physics steps per timer fire; only the last
        # snapshot is emitted to the GUI (keeps emit rate stable).
        snap = self._scenario.step()
        self._tick_n += 1
        if snap.tracks:
            t = snap.tracks[0]
            self._vel_buf.append((t.velocity.speed_ms, t.velocity.heading_deg))

        for _ in range(self._time_scale - 1):
            snap = self._scenario.step()
            self._tick_n += 1
            if snap.tracks:
                t = snap.tracks[0]
                self._vel_buf.append((t.velocity.speed_ms, t.velocity.heading_deg))

        # Throttle: emit GUI signals only every _emit_every ticks
        if self._tick_n % self._emit_every != 0:
            return

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

        # Acoustic x3 — include sensor position for bearing-line rendering in QML
        self.acousticUpdated.emit([
            {
                "sensorId":    r.sensor_id,
                "lat":         s._lat,
                "lon":         s._lon,
                "amplitudeDb": r.amplitude_db,
                "bearing":     r.estimated_bearing,
                "freqHz":      round(r.frequency_hz, 1),
                "confidence":  r.detection_confidence,
                "detected":    r.target_detected,
            }
            for r, s in zip(snap.acoustic_readings, self._scenario.acoustic_sensors)
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

        # Fused tracks — emit with smoothed velocity
        smooth_vel = self._smooth_velocity()
        self.tracksUpdated.emit([
            {
                "trackId":    t.track_id,
                "lat":        round(t.position.lat, 6),
                "lon":        round(t.position.lon, 6),
                "speedMs":    round(smooth_vel[0], 2) if smooth_vel else round(t.velocity.speed_ms, 2),
                "headingDeg": round(smooth_vel[1], 1) if smooth_vel else round(t.velocity.heading_deg, 1),
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
