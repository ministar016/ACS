"""
TerrainMap — 100 × 100 m height map.

Primary source : real SRTM-30m elevation fetched via sim/terrain_real.py
                 (cached in sim/cache/ after first download).
Fallback        : procedural sine-wave noise (used when offline).

The grid is always 101 × 101 at 1 m spacing.  Heights are normalised to
relative metres so both real and procedural data look consistent in 3D.
"""
from __future__ import annotations
import numpy as np


class TerrainMap:
    SIZE_M     = 100
    SPACING_M  = 1        # → 101 × 101  = 10 201 vertices

    def __init__(self, seed: int = 42,
                 elev_data: np.ndarray | None = None,
                 map_colors: np.ndarray | None = None) -> None:
        """
        Parameters
        ----------
        seed       : random seed for procedural fallback
        elev_data  : (101, 101) float32 array of relative heights [m]
                     from terrain_real.get_elevation_grid().
                     If None or wrong shape → procedural generation.
        map_colors : (101, 101, 4) float32 RGBA OSM map colours
                     from terrain_real.get_osm_colors_for_field().
                     If provided, surface_data() uses these instead of
                     the rainbow height colormap.
        """
        N  = self.SIZE_M // self.SPACING_M + 1   # 101
        xs = np.linspace(0.0, self.SIZE_M, N)
        ys = np.linspace(0.0, self.SIZE_M, N)
        X, Y = np.meshgrid(xs, ys)

        if elev_data is not None and elev_data.shape == (N, N):
            Z = elev_data.copy()
            self.is_real = True
        else:
            rng = np.random.default_rng(seed)
            Z = (3.5 * np.sin(X / 18.0) * np.cos(Y / 22.0)
               + 2.0 * np.sin(X / 9.0  + Y / 12.0 + 1.2)
               + 0.8 * np.sin(X / 4.5  + Y / 6.0  + 2.1)
               + 0.25 * rng.standard_normal(X.shape))
            Z -= Z.min()
            Z += 0.10
            self.is_real = False

        self._N         = N
        self._xs_1d     = xs.astype(np.float32)
        self._ys_1d     = ys.astype(np.float32)
        self._Z_2d      = Z.astype(np.float32)
        self.map_colors = (map_colors
                           if map_colors is not None and map_colors.shape == (N, N, 4)
                           else None)
        self.has_map    = self.map_colors is not None
        self.x       = X.ravel().astype(np.float32)
        self.y       = Y.ravel().astype(np.float32)
        self.z       = Z.ravel().astype(np.float32)
        self._z_min  = float(self.z.min())
        self._z_max  = float(self.z.max())

    # ── accessors ─────────────────────────────────────────────────────────

    @property
    def points(self) -> np.ndarray:
        """Return (N², 3) float32 array of (x, y, z) terrain vertices."""
        return np.column_stack([self.x, self.y, self.z])

    @property
    def colors(self) -> np.ndarray:
        """Return (N², 4) float32 RGBA array colour-mapped by height."""
        t = (self.z - self._z_min) / max(self._z_max - self._z_min, 1e-6)
        return height_colormap(t)

    def height_label(self) -> str:
        """Human-readable source label for UI display."""
        src = "SRTM-30m real" if self.is_real else "procedural"
        return f"z {self._z_min:.1f}–{self._z_max:.1f} m  [{src}]"

    def z_at(self, x: float, y: float) -> float:
        """Bilinear-ish: snap to nearest grid point and return its height."""
        xi = int(round(x / self.SPACING_M))
        yi = int(round(y / self.SPACING_M))
        xi = max(0, min(self._N - 1, xi))
        yi = max(0, min(self._N - 1, yi))
        return float(self.z[yi * self._N + xi])

    def surface_data(self) -> tuple:
        """
        Return (xs_1d, ys_1d, Z_surf, C_surf) for GLSurfacePlotItem.

        GLSurfacePlotItem expects z[i,j] = height at (xs[i], ys[j]).
        Our _Z_2d[i,j] = height at (xs[j], ys[i])  (meshgrid row-major).
        So Z_surf = _Z_2d.T and colours follow the same transpose.
        """
        N      = self._N
        Z_surf = self._Z_2d.T                                         # (N, N)
        if self.map_colors is not None:
            # map_colors[i,j] = colour at xs[i], ys[j]  (already transposed)
            C_surf = self.map_colors
        else:
            t      = ((Z_surf - self._z_min)
                      / max(self._z_max - self._z_min, 1e-6))
            C_surf = height_colormap(t.ravel()).reshape(N, N, 4)      # (N, N, 4)
        return self._xs_1d, self._ys_1d, Z_surf, C_surf


# ── colour map ────────────────────────────────────────────────────────────────

def height_colormap(t: np.ndarray) -> np.ndarray:
    """
    Map normalised height t ∈ [0, 1] to RGBA float32.

    Palette (military night-vision inspired):
      0.00 → deep navy blue
      0.25 → cyan-teal (water/low ground)
      0.50 → moss green (mid slopes)
      0.75 → amber (high ground)
      1.00 → near-white (peaks)
    """
    bp = np.array([
        [0.00, 0.05, 0.15, 0.50],
        [0.25, 0.00, 0.55, 0.75],
        [0.50, 0.10, 0.65, 0.20],
        [0.75, 0.80, 0.75, 0.10],
        [1.00, 0.95, 0.95, 0.95],
    ], dtype=np.float32)   # (breakpoint, R, G, B)

    r = np.interp(t, bp[:, 0], bp[:, 1]).astype(np.float32)
    g = np.interp(t, bp[:, 0], bp[:, 2]).astype(np.float32)
    b = np.interp(t, bp[:, 0], bp[:, 3]).astype(np.float32)
    a = np.full_like(t, 0.75, dtype=np.float32)
    return np.column_stack([r, g, b, a])
