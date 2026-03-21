"""
SeismicSensor — standalone field unit.

Physics model
─────────────
Ground vibration amplitude from a vehicle is empirically modelled as:
  A(d) = A_ref / d^1.5          (surface Rayleigh-wave attenuation)

A_ref  = 0.05 g at 1 m (tracked/wheeled heavy vehicle)
Detection threshold  = 0.000002 g  (≈ ≤700 m for this target weight class)
"""
from __future__ import annotations
import math
import random
from ..models import SeismicReading, SensorStatus
from ..target import FakeTarget


_A_REF_G      = 0.05
_D_REF_M      = 1.0
_DETECT_THR_G = 0.000002   # 0.002 mg  → ~700 m range
_NOISE_STD_G  = 0.0000002
_MAX_RANGE_M  = 800        # practical seismic range


class SeismicSensor:
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

    def sample(self, target: FakeTarget, timestamp: float) -> SeismicReading:
        dist_m = target.distance_to_m(self._lat, self._lon)

        amp_g = self._amplitude(dist_m)
        amp_g = max(0.0, amp_g + self._rng.gauss(0.0, _NOISE_STD_G))

        bearing_noise = self._rng.gauss(0.0, 8.0 * dist_m / max(_MAX_RANGE_M, 1))
        bearing = (target.bearing_from_m(self._lat, self._lon) + bearing_noise) % 360

        conf     = max(0.0, min(1.0, 1.0 - dist_m / _MAX_RANGE_M + self._rng.gauss(0.0, 0.04)))
        detected = amp_g >= _DETECT_THR_G and dist_m <= _MAX_RANGE_M

        return SeismicReading(
            sensor_id            = self.sensor_id,
            timestamp            = timestamp,
            amplitude_g          = round(amp_g, 7),
            estimated_bearing    = round(bearing, 1),
            detection_confidence = round(conf, 4),
            target_detected      = detected,
            status               = self.status,
        )

    def _amplitude(self, dist_m: float) -> float:
        if dist_m < 0.1:
            dist_m = 0.1
        return _A_REF_G * (_D_REF_M / dist_m) ** 1.5
