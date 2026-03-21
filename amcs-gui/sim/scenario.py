"""
Scenario — wires together FakeTarget, sensors, and devices.

Call scenario.step() at your desired rate (e.g. every 100 ms for 10 Hz).
Returns a ScenarioSnapshot with all sensor data and a fused track.
"""
from __future__ import annotations
import math
import random
from typing import List

from .models import (
    GeoCoord, Velocity, Track, ThreatLevel, ScenarioSnapshot,
    AcousticReading, SeismicReading,
)
from .target import FakeTarget, _move
from .devices.uav import UAV
from .devices.ugv import UGV
from .sensors.acoustic import AcousticSensor
from .sensors.seismic  import SeismicSensor


# ── Sensor layout (from object diagram) ─────────────────────────────────────

_ACOUSTIC_NODES = [
    ("ACO-FIELD-01", 42.824, 20.195),
    ("ACO-FIELD-02", 42.833, 20.350),
    ("ACO-FIELD-03", 42.821, 20.500),
]

_SEISMIC_NODES = [
    ("SEI-FIELD-01", 42.831, 20.225),
    ("SEI-FIELD-02", 42.818, 20.370),
    ("SEI-FIELD-03", 42.829, 20.485),
]


# ── Simple position estimator from polar observation ─────────────────────────

def _polar_to_geo(sensor_lat: float, sensor_lon: float,
                  bearing_deg: float, distance_m: float) -> GeoCoord:
    lat, lon = _move(sensor_lat, sensor_lon, bearing_deg, distance_m)
    return GeoCoord(lat, lon, 0.0)


# ── Fusion: weighted centroid of all position estimates ───────────────────────

def _fuse_positions(estimates: list[tuple[GeoCoord, float]]) -> GeoCoord | None:
    """Returns confidence-weighted average GeoCoord, or None if no estimates."""
    if not estimates:
        return None
    total_w = sum(w for _, w in estimates)
    if total_w < 1e-9:
        return None
    lat = sum(p.lat * w for p, w in estimates) / total_w
    lon = sum(p.lon * w for p, w in estimates) / total_w
    return GeoCoord(lat, lon, 0.0)


class Scenario:
    """
    Full AMCS scenario simulation.

    Usage
    -----
    scenario = Scenario(dt=0.1)
    for _ in range(1800):                 # 3 minutes at 10 Hz
        snap = scenario.step()
        print(snap.threat_level, snap.tracks)
    """

    def __init__(self, dt: float = 0.1, seed: int = 42) -> None:
        self._dt   = dt
        self._t    = 0.0
        self._rng  = random.Random(seed)

        # Ground Truth
        self.target = FakeTarget(dt=dt, seed=seed)

        # Field sensors
        self.acoustic_sensors: list[AcousticSensor] = [
            AcousticSensor(sid, lat, lon, seed=seed + i)
            for i, (sid, lat, lon) in enumerate(_ACOUSTIC_NODES)
        ]
        self.seismic_sensors: list[SeismicSensor] = [
            SeismicSensor(sid, lat, lon, seed=seed + 10 + i)
            for i, (sid, lat, lon) in enumerate(_SEISMIC_NODES)
        ]

        # Devices
        self.uav = UAV(dt=dt, seed=seed + 20)
        self.ugv = UGV(dt=dt, seed=seed + 30)

    # ── main tick ─────────────────────────────────────────────────────────

    def step(self) -> ScenarioSnapshot:
        self._t += self._dt
        ts = self._t

        # Advance target
        self.target.step()

        # Sample standalone sensors
        acoustic_readings: list[AcousticReading] = [
            s.sample(self.target, ts) for s in self.acoustic_sensors
        ]
        seismic_readings: list[SeismicReading] = [
            s.sample(self.target, ts) for s in self.seismic_sensors
        ]

        # Step devices (each also reads its own sensors)
        uav_tel = self.uav.step(self.target, ts)
        ugv_tel = self.ugv.step(self.target, ts)

        # Fuse into track(s)
        tracks = self._fuse(
            ts, acoustic_readings, seismic_readings, uav_tel, ugv_tel
        )

        threat = self._threat_level(tracks)

        return ScenarioSnapshot(
            timestamp           = round(ts, 3),
            target_position     = self.target.position,  # ground truth
            acoustic_readings   = acoustic_readings,
            seismic_readings    = seismic_readings,
            uav_telemetry       = uav_tel,
            ugv_telemetry       = ugv_tel,
            tracks              = tracks,
            threat_level        = threat,
        )

    # ── private helpers ───────────────────────────────────────────────────

    def _fuse(self, ts, acoustics, seismics, uav_tel, ugv_tel) -> list[Track]:
        estimates: list[tuple[GeoCoord, float]] = []
        sources:   list[str] = []

        # Acoustic — bearing-only: need ≥2 sensors for triangulation
        aco_detected = [(r, s) for r, s in zip(acoustics, self.acoustic_sensors)
                        if r.target_detected]
        if len(aco_detected) >= 2:
            # Simple pairwise triangulation (first two detections)
            r0, s0 = aco_detected[0]
            r1, s1 = aco_detected[1]
            pos = self._triangulate(
                s0._lat, s0._lon, r0.estimated_bearing,
                s1._lat, s1._lon, r1.estimated_bearing,
            )
            if pos:
                w = (r0.detection_confidence + r1.detection_confidence) / 2
                estimates.append((pos, w * 0.6))    # lower weight: bearing-only
                sources += [r0.sensor_id, r1.sensor_id]

        # Seismic — very short range; amplitude-based range is unreliable so
        # seismic only contributes to the source list (confidence boost), not
        # to the position estimate.
        sei_detected = [(r, s) for r, s in zip(seismics, self.seismic_sensors)
                        if r.target_detected]
        for r, s in sei_detected:
            sources.append(r.sensor_id)

        # UAV radar (most accurate)
        if uav_tel.radar and uav_tel.radar.target_detected:
            r = uav_tel.radar
            pos = _polar_to_geo(
                uav_tel.position.lat, uav_tel.position.lon,
                (r.azimuth_deg + uav_tel.heading_deg) % 360,
                r.distance_m,
            )
            estimates.append((pos, r.detection_confidence))
            sources.append(r.sensor_id)

        # UGV radar
        if ugv_tel.radar and ugv_tel.radar.target_detected:
            r = ugv_tel.radar
            pos = _polar_to_geo(
                ugv_tel.position.lat, ugv_tel.position.lon,
                (r.azimuth_deg + ugv_tel.heading_deg) % 360,
                r.distance_m,
            )
            estimates.append((pos, r.detection_confidence))
            sources.append(r.sensor_id)

        # Camera confirmations (don't add new position estimates, boost confidence)
        for cam in (uav_tel.camera, ugv_tel.camera):
            if cam and cam.target_detected:
                sources.append(cam.sensor_id)

        if not estimates:
            return []

        fused_pos = _fuse_positions(estimates)
        if fused_pos is None:
            return []

        total_conf = min(1.0, sum(w for _, w in estimates) / len(estimates) +
                         0.05 * len(sources))
        total_conf = round(max(0.0, min(1.0, total_conf)), 4)

        # Velocity from target's noisy heading/speed (real system would use Kalman)
        vel_noise  = self._rng.gauss(0.0, 0.5)
        hdg_noise  = self._rng.gauss(0.0, 5.0)
        track = Track(
            track_id       = "TRK-20260321-001",
            timestamp      = ts,
            position       = fused_pos,
            velocity       = Velocity(
                speed_ms    = max(0.0, self.target.velocity.speed_ms + vel_noise),
                heading_deg = (self.target.velocity.heading_deg + hdg_noise) % 360,
            ),
            confidence     = total_conf,
            threat_level   = ThreatLevel.HIGH if total_conf > 0.7 else
                             ThreatLevel.MEDIUM if total_conf > 0.4 else
                             ThreatLevel.LOW,
            sensor_sources = list(set(sources)),
        )
        return [track]

    def _triangulate(
        self,
        lat0: float, lon0: float, bearing0: float,
        lat1: float, lon1: float, bearing1: float,
    ) -> GeoCoord | None:
        """
        Approximate bearing-line intersection in a flat local frame (NED).
        Returns None if lines are nearly parallel.
        """
        # Convert to local metres relative to sensor 0
        scale_lat = 111_320.0
        scale_lon = 111_320.0 * math.cos(math.radians(lat0))

        x1, y1 = 0.0, 0.0
        x2 = (lon1 - lon0) * scale_lon
        y2 = (lat1 - lat0) * scale_lat

        # Direction vectors
        b0, b1 = math.radians(bearing0), math.radians(bearing1)
        dx0, dy0 = math.sin(b0),  math.cos(b0)
        dx1, dy1 = math.sin(b1),  math.cos(b1)

        # Solve  [dx0 -dx1] [t]   [x2-x1]
        #        [dy0 -dy1] [s] = [y2-y1]
        det = -dx0 * dy1 + dy0 * dx1
        if abs(det) < 1e-6:
            return None

        t = (-(x2 - x1) * dy1 + (y2 - y1) * dx1) / det
        ix = x1 + t * dx0
        iy = y1 + t * dy0

        lat = lat0 + iy / scale_lat
        lon = lon0 + ix / scale_lon
        return GeoCoord(lat, lon, 0.0)

    @staticmethod
    def _threat_level(tracks: list[Track]) -> ThreatLevel:
        if not tracks:
            return ThreatLevel.NONE
        return max(t.threat_level for t in tracks)
