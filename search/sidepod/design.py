"""The sidepod's parameters -> its design field over the region (mm, + = foam, full 1 mm grid).

  seed "original"  the team's sidepod (signed distance of the drawn body)
  seed "lean"      no sidepod at all (from scratch)
  seed "blend"     halfway (a free parameter t in [0, 1] mixes the two)

  Lattice(shape, amp_mm, seed)  a coarse grid of control points over the +y half of the region,
                                cubic-interpolated, mirrored to -y, added to the seed (CMA-ES)
"""
from __future__ import annotations

import sys
from pathlib import Path
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
import repo_paths  # noqa: E402,F401
import numpy as np
from scipy import ndimage


class Lattice:
    def __init__(self, car, shape=(10, 4, 5), amp_mm=12.0, seed="blend"):
        self.car, self.shape, self.amp, self.seed = car, tuple(shape), amp_mm, seed
        self.dim = int(np.prod(shape)) + (1 if seed == "blend" else 0)

    def x0(self, start: str):
        x = np.zeros(self.dim)
        if self.seed == "blend":
            x[-1] = {"original": 3.0, "lean": -3.0}.get(start, 0.0)   # logit of the mix t
        return x

    def field(self, x):
        c = self.car
        x = np.asarray(x, float)
        if self.seed == "blend":
            t = 1.0 / (1.0 + np.exp(-x[-1]))
            base = t * c.sdf_original + (1 - t) * c.sdf_lean
            g = x[:-1]
        else:
            base = c.sdf_original if self.seed == "original" else c.sdf_lean
            g = x
        f = base.copy()
        # the lattice spans the +y half of the region; mirror to -y
        j0 = np.searchsorted(c.ys, 0.0)
        lo, hi = c.rlo.copy(), c.rhi.copy()
        lo[1] = max(lo[1], j0)
        n = hi - lo
        up = ndimage.zoom(g.reshape(self.shape), n / np.array(self.shape), order=3, mode="nearest")[: n[0], : n[1], : n[2]]
        add = np.zeros_like(f)
        add[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] = self.amp * up
        add[:, :j0] = add[:, j0:][:, ::-1][:, : j0]
        return f + add
