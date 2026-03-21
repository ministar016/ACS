"""
AMCS simulation data models.
All timestamps are float seconds since simulation epoch.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional


# ── Geo primitives ──────────────────────────────────────────────────────────

@dataclass
class GeoCoord:
    lat: float        # degrees N
    lon: float        # degrees E
    alt: float = 0.0  # metres MSL

    def __repr__(self) -> str:
        return f"({self.lat:.5f}°N, {self.lon:.5f}°E, {self.alt:.1f}m)"


@dataclass
class Velocity:
    speed_ms: float     # m/s
    heading_deg: float  # 0=N, 90=E, 180=S, 270=W


# ── Status enums ─────────────────────────────────────────────────────────────

class DeviceStatus(Enum):
    OFFLINE    = auto()
    CONNECTING = auto()
    ONLINE     = auto()
    DEPLOYED   = auto()
    DEPLOYING  = auto()
    ERROR      = auto()

class SensorStatus(Enum):
    INACTIVE = auto()
    ACTIVE   = auto()
    FAULT    = auto()

class ThreatLevel(Enum):
    NONE   = 0
    LOW    = 1
    MEDIUM = 2
    HIGH   = 3


# ── Sensor readings ───────────────────────────────────────────────────────────

@dataclass
class AcousticReading:
    sensor_id:          str
    timestamp:          float
    amplitude_db:       float          # dB SPL; background ~30 dB, engine ~80–110 dB
    estimated_bearing:  float          # degrees from sensor (0=N)
    frequency_hz:       float          # dominant frequency
    detection_confidence: float        # 0..1
    target_detected:    bool = False
    status:             SensorStatus = SensorStatus.ACTIVE


@dataclass
class SeismicReading:
    sensor_id:          str
    timestamp:          float
    amplitude_g:        float          # acceleration in g
    estimated_bearing:  float          # degrees from sensor
    detection_confidence: float        # 0..1
    target_detected:    bool = False
    status:             SensorStatus = SensorStatus.ACTIVE


@dataclass
class RadarReturn:
    sensor_id:          str
    timestamp:          float
    distance_m:         float
    azimuth_deg:        float          # relative to sensor heading
    elevation_deg:      float
    radial_velocity_ms: float          # + = closing
    rcs_dbsm:           float          # radar cross-section
    detection_confidence: float
    target_detected:    bool = False
    status:             SensorStatus = SensorStatus.ACTIVE


@dataclass
class CameraDetection:
    sensor_id:          str
    timestamp:          float
    object_class:       str            # e.g. "GROUND_VEHICLE", "PERSON"
    confidence:         float          # 0..1
    estimated_distance_m: float
    bearing_deg:        float
    bbox_norm:          tuple          # (x, y, w, h) normalised 0..1
    target_detected:    bool = False
    status:             SensorStatus = SensorStatus.ACTIVE


# ── Device telemetry ──────────────────────────────────────────────────────────

@dataclass
class UAVTelemetry:
    device_id:    str
    timestamp:    float
    position:     GeoCoord
    altitude_m:   float
    speed_ms:     float
    heading_deg:  float
    battery_pct:  float
    status:       DeviceStatus
    radar:        Optional[RadarReturn]  = None
    camera:       Optional[CameraDetection] = None


@dataclass
class UGVTelemetry:
    device_id:    str
    timestamp:    float
    position:     GeoCoord
    speed_ms:     float
    heading_deg:  float
    battery_pct:  float
    status:       DeviceStatus
    terrain_mode: str = "RUGGED"
    radar:        Optional[RadarReturn]  = None
    camera:       Optional[CameraDetection] = None


# ── Fused track ───────────────────────────────────────────────────────────────

@dataclass
class Track:
    track_id:        str
    timestamp:       float
    position:        GeoCoord
    velocity:        Velocity
    confidence:      float
    threat_level:    ThreatLevel
    sensor_sources:  List[str] = field(default_factory=list)  # which sensors contributed


# ── Scenario snapshot (one simulation tick) ────────────────────────────────────

@dataclass
class ScenarioSnapshot:
    timestamp:           float
    target_position:     GeoCoord          # ground truth (not observable!)
    acoustic_readings:   List[AcousticReading]
    seismic_readings:    List[SeismicReading]
    uav_telemetry:       UAVTelemetry
    ugv_telemetry:       UGVTelemetry
    tracks:              List[Track]        # fused output
    threat_level:        ThreatLevel
