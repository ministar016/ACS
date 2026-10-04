"""
Interceptor guidance — predicted-intercept-point (PIP) lead pursuit.

Given the tracker's estimate of the target (position p, velocity v, local
ENU) and an interceptor at q flying at constant speed s, the intercept time
t solves

    |p + v·t − q| = s·t
    ⇒ (v·v − s²) t² + 2 (r·v) t + r·r = 0,     r = p − q

The smallest positive root gives the PIP = p + v·t.  Re-solving every tick
from fresh track estimates makes the interceptor fly a collision course that
continuously corrects for target manoeuvres — for a non-manoeuvring target it
is equivalent to proportional navigation with an ideal navigation constant.

If no real root exists (target faster than interceptor and opening), we fall
back to pure pursuit of a short-horizon lead point, and report infeasible.
"""
from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass
class InterceptSolution:
    feasible: bool
    t_go:     float          # s until intercept (or pursuit horizon)
    aim_x:    float
    aim_y:    float


def solve_intercept(px: float, py: float, vx: float, vy: float,
                    qx: float, qy: float, speed: float,
                    max_t: float = 600.0) -> InterceptSolution:
    rx, ry = px - qx, py - qy
    a = vx * vx + vy * vy - speed * speed
    b = 2.0 * (rx * vx + ry * vy)
    c = rx * rx + ry * ry

    t = None
    if abs(a) < 1e-9:                       # equal speeds → linear equation
        if b < 0:
            t = -c / b
    else:
        disc = b * b - 4 * a * c
        if disc >= 0:
            sq = math.sqrt(disc)
            roots = sorted(r for r in ((-b - sq) / (2 * a), (-b + sq) / (2 * a)) if r > 0)
            if roots:
                t = roots[0]

    if t is not None and t <= max_t:
        return InterceptSolution(True, t, px + vx * t, py + vy * t)

    # Infeasible: pursue a lead point a few seconds ahead
    lead = min(10.0, math.sqrt(c) / max(speed, 1.0))
    return InterceptSolution(False, math.sqrt(c) / max(speed, 1.0),
                             px + vx * lead, py + vy * lead)


def heading_to(x: float, y: float, tx: float, ty: float) -> float:
    """Compass heading (deg, 0 = N, clockwise) from (x, y) to (tx, ty)."""
    return math.degrees(math.atan2(tx - x, ty - y)) % 360.0


def turn_toward(current_deg: float, desired_deg: float,
                max_rate_dps: float, dt: float) -> float:
    err = (desired_deg - current_deg + 180.0) % 360.0 - 180.0
    step = max(-max_rate_dps * dt, min(max_rate_dps * dt, err))
    return (current_deg + step) % 360.0
