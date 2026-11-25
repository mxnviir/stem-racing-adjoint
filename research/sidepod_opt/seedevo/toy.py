"""A known-answer bench for the search machinery (tests T3a-T3d). NOT a model of aerodynamics.

Objective: weighted mismatch between a design and a hidden legal target shape. The target is built from
parts of three seeds, one cut no seed has, and a smooth sculpt of its whole surface, so reaching it needs
recombination (crossover), a new feature (mutation) and continuous shaping (the adjoint's job).

What it copies from the real problem, by construction:
  * fresh-mesh score = truth + noise sigma_fresh (set to 0.25 x the seeds' spread: reliability 0.94, the
    level test E demands of the real instrument);
  * morph score = an exact difference to the parent with noise sigma_fresh / 50, available only for small
    moves that keep the topology, and only within 2 mm of the parent's last fresh mesh;
  * the adjoint = the true surface sensitivity mixed with a FIXED smooth bias field to a chosen correlation
    rho (0.85 = what coarse DAFoam showed on the good mesh; 0 = useless; negative = misleading), with the
    wrong size (x2). It never creates a hole: it only moves the surface;
  * costs: fresh run 1, morph run 1, adjoint solve 0.7.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import operators as OP
from .space import ToySpace, through_openings


def occ(f, h):
    return np.clip(0.5 + f / (2.0 * h), 0.0, 1.0)


def _box(sp, x0, x1, yw, z0, z1, taper):
    t = OP.smoothstep((sp.X - x0) / max(x1 - x0, 1e-9))
    ymax = 4.0 + yw * (1.0 - taper * t)
    d = np.maximum(np.maximum(np.maximum(x0 - sp.X, sp.X - x1), sp.Y - ymax), np.maximum(z0 - sp.Z, sp.Z - z1))
    return -d


def make_seeds(sp, n=12, seed=1):
    """n legal, visibly different pods: boxes of different length, width, height and taper, most with one
    or two cuts or slot arrays."""
    rng = np.random.default_rng(1000 + seed)
    out = {}
    while len(out) < n:
        x0 = rng.uniform(4, 16); x1 = rng.uniform(40, 60)
        z0 = rng.uniform(3, 9); z1 = rng.uniform(16, 23)
        f = _box(sp, x0, x1, rng.uniform(7, 15), z0, z1, rng.uniform(0.0, 0.6))
        for _ in range(int(rng.integers(0, 3))):
            b = sp.build(f)
            if not b["ok"]:
                break
            name = str(rng.choice(["cut", "pattern", "fill"], p=[0.5, 0.35, 0.15]))
            f, _m = OP.OPS[name](sp, rng, b["f"], None, None)
        b = sp.build(f)
        if b["ok"] and b["pod_mm3"] > 1500:
            out[f"s{len(out):02d}"] = b["f"]
    return out


def make_target(sp, seeds, seed=1):
    rng = np.random.default_rng(7000 + seed)
    names = list(seeds)
    a, b, c = (seeds[names[i]] for i in rng.choice(len(names), 3, replace=False))
    w = OP.smoothstep((sp.X - rng.uniform(26, 38)) / 8.0 + 0.5)
    f = w * a + (1 - w) * b                                                   # front of one, rear of another
    ctr = OP._pick(sp, rng, sp.region & (np.abs(c) <= sp.h))
    if ctr is not None:
        W = OP._win(sp, ctr, 12.0)
        f = f + W * (c - f)                                                   # a window of the third
    f = sp.build(f)["f"]
    f, _ = OP.cut(sp, rng, f, None, None)                                     # a cut no seed has
    f = sp.build(f)["f"]
    n = ndimage.gaussian_filter(rng.standard_normal(f.shape), 6.0 / sp.h)
    s = sp.region & (np.abs(f) <= sp.h)
    f = f + 1.5 * np.clip(n / (np.percentile(np.abs(n[s]), 95) + 1e-30), -1, 1)   # the smooth sculpt
    return sp.build(f)["f"]


class ToyEvaluator:
    cost_fresh, cost_morph, cost_adjoint = 1.0, 1.0, 0.7

    def __init__(self, sp: ToySpace, target_f, rho=0.85, sigma_fresh=1.0, seed=0, morph_max_mm=2.5):
        self.sp, self.rho = sp, rho
        self.occT = occ(target_f, sp.h)
        self.w = (1.0 + 2.0 * np.exp(-((sp.X - 50.0) / 15.0) ** 2)) * sp.region
        self.sigma_fresh, self.sigma_morph = sigma_fresh, sigma_fresh / 50.0
        self.rng = np.random.default_rng(90000 + seed)
        self.bias = ndimage.gaussian_filter(np.random.default_rng(4242).standard_normal(sp.shape), 5.0 / sp.h)
        self.morph_max = morph_max_mm
        self.calls = {"fresh": 0, "morph": 0, "adjoint": 0, "fold": 0}

    def true(self, f):
        return float((self.w * np.abs(occ(f, self.sp.h) - self.occT)).sum() * self.sp.h ** 3 / 1e3)

    def fresh(self, ind, k):
        self.calls["fresh"] += 1
        return self.true(ind.f) + self.rng.normal(0.0, self.sigma_fresh)

    def morph(self, parent, child):
        self.calls["morph"] += 1
        sp = self.sp
        b = sp.region & ((np.abs(parent.f) <= 1.5 * sp.h) | (np.abs(child.f) <= 1.5 * sp.h))
        moved = float(np.abs(child.f - parent.f)[b].max()) if b.any() else 0.0
        topo = (through_openings(parent.B & sp.region) != through_openings(child.B & sp.region)
                or ndimage.label(~child.B)[1] != ndimage.label(~parent.B)[1])
        if moved > self.morph_max or topo:
            self.calls["fold"] += 1
            return None
        return self.true(child.f) - self.true(parent.f) + self.rng.normal(0.0, self.sigma_morph * np.sqrt(2.0))

    def adjoint(self, ind):
        """Objective change per mm of outward surface move, per cell: the truth mixed with the bias."""
        self.calls["adjoint"] += 1
        sp = self.sp
        band = sp.region & (np.abs(ind.f) < sp.h)
        g = self.w * np.sign(occ(ind.f, sp.h) - self.occT) / (2.0 * sp.h) * sp.h ** 3 / 1e3 * band
        b = self.bias * band
        ng, nb = np.linalg.norm(g), np.linalg.norm(b)
        if ng == 0:
            return g
        return 2.0 * (self.rho * g + np.sqrt(max(0.0, 1.0 - self.rho ** 2)) * b * (ng / (nb + 1e-30)))

    def grad_step(self, space, e, step_mm):
        return OP.grad_step(space, e.f, e.grad, step_mm)
