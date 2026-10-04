"""
RadarSensor — vehicle-mounted (UAV or UGV).

Simple free-space path-loss + RCS model:
  SNR = Pt + Gt + Gr + 20·log10(λ) + RCS_target - 30·log10(4π) - 40·log10(d)
  Detection when SNR > SNR_min.

We skip absolute power arithmetic and instead derive detection probability
from a simplified detection curve against distance.
  P_det(d) = 1 - (d / range_max)^2

range_m is the instrumented range against a reference target of
`rcs_ref_dbsm` (default −15 dBsm — small fixed-wing drone).  From the radar
equation R ∝ σ^¼, so the effective range scales as 10^((σ − σ_ref)/40).

Ground targets are seen in the GMTI (ground moving-target) mode, limited to
`ground_range_m` by clutter and terrain; the plot carries the mode so the
tracker never mixes air and ground tracks.
"""
from __future__ import annotations
import math
import random
from ..models import RadarReturn, SensorStatus
from ..target import AerialTarget


_RCS_REF_DBSM     = -15.0    # reference drone RCS for range_m
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
        rcs_ref_dbsm: float = _RCS_REF_DBSM,
        ground_range_m: float = 4_000.0,
        max_range_m:  float = 0.0,
    ) -> None:
        self.sensor_id    = sensor_id
        self.range_m      = range_m
        self.rcs_ref_dbsm = rcs_ref_dbsm
        self.ground_range_m = ground_range_m
        self.max_range_m  = max_range_m      # instrumented range cap (0 = none)
        self.frequency_ghz = frequency_ghz
        self._rng         = random.Random(seed)
        self.status       = SensorStatus.ACTIVE

        # Sensor is mounted on a moving platform — position is updated each tick
        self._plat_lat:    float = 0.0
        self._plat_lon:    float = 0.0
        self._plat_heading: float = 0.0
        self._plat_alt:     float = 0.0

    def update_platform(self, lat: float, lon: float, heading_deg: float,
                        alt_m: float = 0.0) -> None:
        self._plat_lat     = lat
        self._plat_lon     = lon
        self._plat_heading = heading_deg
        self._plat_alt     = alt_m

    def effective_range_m(self, rcs_dbsm: float) -> float:
        r = self.range_m * 10.0 ** ((rcs_dbsm - self.rcs_ref_dbsm) / 40.0)
        return min(r, self.max_range_m) if self.max_range_m else r

    def sample(self, target: AerialTarget, timestamp: float) -> RadarReturn:
        dist_m   = target.distance_to_m(self._plat_lat, self._plat_lon)
        abs_az   = target.bearing_from_m(self._plat_lat, self._plat_lon)
        rel_az   = (abs_az - self._plat_heading) % 360   # relative to nose
        tgt_rcs  = getattr(target, "rcs_dbsm", self.rcs_ref_dbsm)
        r_eff    = self.effective_range_m(tgt_rcs)
        if getattr(target, "domain", "AIR") == "GROUND":
            r_eff = min(r_eff, self.ground_range_m)

        # Detection probability
        p_det = max(0.0, 1.0 - (dist_m / r_eff) ** 2)
        detected = target.alive and dist_m <= r_eff and self._rng.random() < p_det

        # Noisy measurements
        d_meas   = max(0.0, dist_m + self._rng.gauss(0.0, _NOISE_MD_STD))
        az_meas  = (rel_az  + self._rng.gauss(0.0, _NOISE_AZ_STD)) % 360
        true_el  = math.degrees(math.atan2(target.position.alt - self._plat_alt,
                                           max(dist_m, 1.0)))
        el_meas  = true_el + self._rng.gauss(0.0, 0.3)
        vel_meas = target.radial_velocity_ms(self._plat_lat, self._plat_lon) \
                   + self._rng.gauss(0.0, _NOISE_VEL_STD)
        rcs      = tgt_rcs + self._rng.gauss(0.0, 2.0)

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
