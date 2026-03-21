"""
RadarSensor — vehicle-mounted (UAV or UGV).

Simple free-space path-loss + RCS model:
  SNR = Pt + Gt + Gr + 20·log10(λ) + RCS_target - 30·log10(4π) - 40·log10(d)
  Detection when SNR > SNR_min.

We skip absolute power arithmetic and instead derive detection probability
from a simplified detection curve against distance.
  P_det(d) = 1 - (d / range_max)^2
"""
from __future__ import annotations
import math
import random
from ..models import RadarReturn, SensorStatus
from ..target import FakeTarget


_RCS_DBSM_VEHICLE = 20.0     # dBsm for a ground vehicle
_NOISE_MD_STD     = 30.0     # distance measurement noise σ (m)
_NOISE_AZ_STD     = 0.5      # azimuth noise σ (deg)
_NOISE_VEL_STD    = 0.2      # radial velocity noise σ (m/s)


class RadarSensor:
    def __init__(
        self,
        sensor_id:    str,
        range_m:      float = 5_000.0,
        frequency_ghz: float = 77.0,
        seed:         int   = 0,
    ) -> None:
        self.sensor_id    = sensor_id
        self.range_m      = range_m
        self.frequency_ghz = frequency_ghz
        self._rng         = random.Random(seed)
        self.status       = SensorStatus.ACTIVE

        # Sensor is mounted on a moving platform — position is updated each tick
        self._plat_lat:    float = 0.0
        self._plat_lon:    float = 0.0
        self._plat_heading: float = 0.0

    def update_platform(self, lat: float, lon: float, heading_deg: float) -> None:
        self._plat_lat     = lat
        self._plat_lon     = lon
        self._plat_heading = heading_deg

    def sample(self, target: FakeTarget, timestamp: float) -> RadarReturn:
        dist_m   = target.distance_to_m(self._plat_lat, self._plat_lon)
        abs_az   = target.bearing_from_m(self._plat_lat, self._plat_lon)
        rel_az   = (abs_az - self._plat_heading) % 360   # relative to nose

        # Detection probability
        p_det = max(0.0, 1.0 - (dist_m / self.range_m) ** 2)
        detected = dist_m <= self.range_m and self._rng.random() < p_det

        # Noisy measurements
        d_meas   = max(0.0, dist_m + self._rng.gauss(0.0, _NOISE_MD_STD))
        az_meas  = (rel_az  + self._rng.gauss(0.0, _NOISE_AZ_STD)) % 360
        el_meas  = self._rng.gauss(0.0, 0.3)                           # ground target ≈ 0°
        vel_meas = target.radial_velocity_ms(self._plat_lat, self._plat_lon) \
                   + self._rng.gauss(0.0, _NOISE_VEL_STD)
        rcs      = _RCS_DBSM_VEHICLE + self._rng.gauss(0.0, 2.0)

        conf = round(p_det * (1.0 + self._rng.gauss(0.0, 0.03)), 4)
        conf = max(0.0, min(1.0, conf))

        return RadarReturn(
            sensor_id            = self.sensor_id,
            timestamp            = timestamp,
            distance_m           = round(d_meas, 1),
            azimuth_deg          = round(az_meas, 2),
            elevation_deg        = round(el_meas, 2),
            radial_velocity_ms   = round(vel_meas, 3),
            rcs_dbsm             = round(rcs, 1),
            detection_confidence = conf,
            target_detected      = detected,
            status               = self.status,
        )
