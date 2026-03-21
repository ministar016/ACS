"""
CameraSensor — vehicle-mounted (UAV or UGV).

Simple visibility model:
  At night / overcast the max reliable ID range ~600 m (UAV alt 150 m).
  Object angular size threshold for detection: ≥ 0.5° → ~400 m for a 3 m vehicle.
  Confidence degrades with distance and raises with proximity.
"""
from __future__ import annotations
import random
from ..models import CameraDetection, SensorStatus
from ..target import FakeTarget


_VEHICLE_SIZE_M  = 4.0     # approximate target vehicle length (m)
_FOV_DEG         = 60.0    # camera horizontal field-of-view
_MAX_RANGE_M     = 800.0   # practical visual ID range
_DETECT_ANG_DEG  = 0.4     # minimum angular size for detection (deg)
_NOISE_DIST_STD  = 15.0    # distance noise σ (m)


class CameraSensor:
    def __init__(
        self,
        sensor_id:    str,
        resolution:   str = "HD_1080P",
        fps:          int = 30,
        night_vision: bool = True,
        seed:         int = 0,
    ) -> None:
        self.sensor_id    = sensor_id
        self.resolution   = resolution
        self.fps          = fps
        self.night_vision = night_vision
        self._rng         = random.Random(seed)
        self.status       = SensorStatus.ACTIVE

        self._plat_lat:     float = 0.0
        self._plat_lon:     float = 0.0
        self._plat_heading: float = 0.0

    def update_platform(self, lat: float, lon: float, heading_deg: float) -> None:
        self._plat_lat     = lat
        self._plat_lon     = lon
        self._plat_heading = heading_deg

    def sample(self, target: FakeTarget, timestamp: float) -> CameraDetection:
        import math
        dist_m   = target.distance_to_m(self._plat_lat, self._plat_lon)
        bearing  = target.bearing_from_m(self._plat_lat, self._plat_lon)
        rel_az   = (bearing - self._plat_heading) % 360

        # Angular size of target
        ang_size_deg = math.degrees(math.atan2(_VEHICLE_SIZE_M, max(dist_m, 1.0)))

        in_fov   = abs((rel_az + 180) % 360 - 180) < _FOV_DEG / 2
        detected = (
            dist_m <= _MAX_RANGE_M and
            in_fov and
            ang_size_deg >= _DETECT_ANG_DEG and
            (self.night_vision or True)    # night_vision suppresses false negatives
        )

        # Confidence: higher when closer + larger angular size
        conf  = min(1.0, ang_size_deg / 5.0)    # saturates around 5°
        conf += self._rng.gauss(0.0, 0.02)
        conf  = max(0.0, min(1.0, conf))

        # Noisy distance
        d_meas = max(0.0, dist_m + self._rng.gauss(0.0, _NOISE_DIST_STD))

        # Bounding box (normalised): centred, width proportional to ang_size
        bw = min(1.0, ang_size_deg / _FOV_DEG)
        bh = bw * 0.6
        bx = 0.5 - bw / 2 + self._rng.gauss(0.0, 0.01)
        by = 0.45 + self._rng.gauss(0.0, 0.01)

        return CameraDetection(
            sensor_id            = self.sensor_id,
            timestamp            = timestamp,
            object_class         = "GROUND_VEHICLE" if detected else "UNKNOWN",
            confidence           = round(conf if detected else 0.0, 4),
            estimated_distance_m = round(d_meas, 1),
            bearing_deg          = round(bearing, 2),
            bbox_norm            = (round(bx,3), round(by,3), round(bw,3), round(bh,3)),
            target_detected      = detected,
            status               = self.status,
        )
