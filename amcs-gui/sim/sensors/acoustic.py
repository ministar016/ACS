"""
AcousticSensor — standalone field unit.

Physics model
─────────────
Sound pressure level from a drone (engine + propeller) models as
inverse-square law, seen through the array's beamforming gain:
  SPL(d) = SPL_ref - 20·log10(d / d_ref)          [dB]

Effective SPL_ref (source level + array gain) 125 dB at 1 m.
Background noise floor  ~35 dB.
Detection threshold      45 dB  → UAV detection range ≈ 10 km.
Bearing noise grows linearly with range to ~3° σ at 10 km.
"""
from __future__ import annotations
import math
import random
from ..models import AcousticReading, SensorStatus
from ..target import AerialTarget


_SPL_REF_DB   = 127.0   # dB at 1 m incl. array gain (drone)
_D_REF_M      = 1.0
_NOISE_FLOOR  = 35.0    # ambient dB
_DETECT_THR   = 45.0    # minimum dB to flag detection (~10 km range)
_DOMINANT_HZ  = 180.0   # propeller blade-pass fundamental (Hz)
_NOISE_STD    = 1.5     # measurement noise σ
_MAX_RANGE_M  = 10_000  # UAV detection range


class AcousticSensor:
    def __init__(
        self,
        sensor_id: str,
        lat: float,
        lon: float,
        seed: int = 0,
    ) -> None:
        self.sensor_id = sensor_id
        self._lat      = lat
        self._lon      = lon
        self._rng      = random.Random(seed)
        self.status    = SensorStatus.ACTIVE

    # ── public ────────────────────────────────────────────────────────────

    def sample(self, target: AerialTarget, timestamp: float) -> AcousticReading:
        dist_m = target.distance_to_m(self._lat, self._lon)

        # SPL with noise
        spl    = self._spl(dist_m, getattr(target, "acoustic_db", _SPL_REF_DB)) + self._rng.gauss(0.0, _NOISE_STD)
        spl    = max(spl, _NOISE_FLOOR)

        # Bearing with noise proportional to distance
        bearing_noise = self._rng.gauss(0.0, 3.0 * dist_m / _MAX_RANGE_M)
        bearing  = (target.bearing_from_m(self._lat, self._lon) + bearing_noise) % 360

        # Confidence: 0 at max range → 1 at 0 m, clipped
        raw_conf = max(0.0, 1.0 - dist_m / _MAX_RANGE_M)
        conf     = min(1.0, raw_conf + self._rng.gauss(0.0, 0.03))
        detected = target.alive and spl >= _DETECT_THR and dist_m <= _MAX_RANGE_M

        return AcousticReading(
            sensor_id            = self.sensor_id,
            timestamp            = timestamp,
            amplitude_db         = round(spl, 2),
            estimated_bearing    = round(bearing, 1),
            frequency_hz         = _DOMINANT_HZ + self._rng.gauss(0.0, 5.0),
            detection_confidence = round(max(0.0, conf), 4),
            target_detected      = detected,
            status               = self.status,
        )

    # ── private ───────────────────────────────────────────────────────────

    def _spl(self, dist_m: float, ref_db: float = _SPL_REF_DB) -> float:
        if dist_m < 0.1:
            dist_m = 0.1
        return ref_db - 20.0 * math.log10(dist_m / _D_REF_M)
