"""Variation operators on design fields (SEED_EVOLUTION_PLAN.md section 4).

A design is a field f on the space's grid (mm, + = foam, about slope 1 near the surface). Every operator
returns a new field; the caller passes it through space.build(), which applies the rules (mill, walls,
pieces) and returns the field of what would actually be made. Operators only use the Space interface
(X, Yabs, Z, region, h), so the same code runs on the toy grid and on the real car.

    child_field, meta = OPS[name](space, rng, fA, fB, guide)

fA: the parent the child starts from. fB: the second parent (crossover only). guide: optional adjoint
sensitivity of fA on the grid (objective change per mm of OUTWARD surface move, per cell; negative =
the surface "wants out" there). With a guide, mutations are placed where the sensitivity is large and
signed the way it asks; without one they are placed uniformly on the surface.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

BALL_R = 3.175          # the mill's ball end (6.35 mm): no cut narrower than this can be made
WALL = 3.0              # minimum foam wall


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _smooth_guide(space, guide, sigma_mm=3.0):
    if guide is None:
        return None
    return ndimage.gaussian_filter(guide, sigma_mm / space.h)


def _pick(space, rng, mask, w=None):
    """A random cell centre (x, |y|, z) of `mask`, optionally weighted."""
    idx = np.flatnonzero(mask & (space.Y >= 0))
    if idx.size == 0:
        return None
    p = None
    if w is not None:
        ww = np.clip(w.ravel()[idx], 0.0, None)
        if ww.sum() > 0:
            p = ww / ww.sum()
    i = rng.choice(idx, p=p)
    return np.array([space.X.ravel()[i], space.Yabs.ravel()[i], space.Z.ravel()[i]])


def _surface(space, f):
    return space.region & (np.abs(f) <= space.h)


def _dist(space, c):
    return np.sqrt((space.X - c[0]) ** 2 + (space.Yabs - c[1]) ** 2 + (space.Z - c[2]) ** 2)


def _win(space, c, r, edge=4.0):
    """1 inside the ball (c, r), 0 outside, smooth over `edge` mm."""
    return smoothstep((r - _dist(space, c)) / edge + 0.5)


def _in_region(space, f_new, f_old):
    return np.where(space.region, f_new, f_old)


# ------------------------------------------------------------------ crossover
def splice(space, rng, fA, fB, guide=None):
    """X1: one side of A, the other side of B, blended across a plane."""
    ax = int(rng.choice(3, p=[0.6, 0.15, 0.25]))
    C = (space.X, space.Yabs, space.Z)[ax]
    pod = space.region & ((fA > 0) | (fB > 0))
    if not pod.any():
        return fA.copy(), {"skip": "no pod"}
    lo, hi = np.quantile(C[pod], [0.25, 0.75])
    c, width = rng.uniform(lo, hi), rng.uniform(6.0, 10.0)
    w = smoothstep((C - c) / width + 0.5)
    if rng.random() < 0.5:
        w = 1.0 - w
    return _in_region(space, w * fA + (1 - w) * fB, fA), {"axis": ax, "cut": float(c)}


def graft(space, rng, fA, fB, guide=None):
    """X2: A, with B's geometry inside one window. The window is placed where the two differ (and, with a
    guide, where A's sensitivity is large)."""
    w = np.clip(np.abs(fA - fB), 0.0, 5.0)
    g = _smooth_guide(space, guide)
    if g is not None:
        w = w * (1.0 + np.abs(g) / (np.percentile(np.abs(g[_surface(space, fA)]), 95) + 1e-30))
    c = _pick(space, rng, _surface(space, fA) | _surface(space, fB), w)
    if c is None:
        return fA.copy(), {"skip": "no surface"}
    r = rng.uniform(8.0, 20.0)
    W = _win(space, c, r)
    return _in_region(space, fA + W * (fB - fA), fA), {"c": c.tolist(), "r": float(r)}


def combine(space, rng, fA, fB, guide=None):
    """X3: inside a window (or everywhere), both designs' cuts (minimum) or both designs' material (maximum)."""
    cuts = rng.random() < 0.6
    both = np.minimum(fA, fB) if cuts else np.maximum(fA, fB)
    if rng.random() < 0.5:
        return _in_region(space, both, fA), {"mode": "cuts" if cuts else "material", "whole": True}
    c = _pick(space, rng, _surface(space, fA) | _surface(space, fB), np.clip(np.abs(fA - fB), 0.0, 5.0))
    if c is None:
        return fA.copy(), {"skip": "no surface"}
    r = rng.uniform(15.0, 35.0)
    W = _win(space, c, r)
    return _in_region(space, fA + W * (both - fA), fA), {"mode": "cuts" if cuts else "material", "r": float(r)}


def _smooth_random(space, rng, f, sigma_mm=4.5):
    n = ndimage.gaussian_filter(rng.standard_normal(f.shape), sigma_mm / space.h)
    n = 0.5 * (n + n[:, ::-1]) if getattr(space, "mirror", False) else n
    s = _surface(space, f)
    return n / (np.percentile(np.abs(n[s]), 95) + 1e-30) if s.any() else n * 0.0


def line(space, rng, fA, fB, guide=None):
    """X4: a fraction of the way from A towards B, plus a small smooth random move (directional variation)."""
    t, a = rng.uniform(0.1, 0.3), rng.uniform(0.3, 1.0)
    return _in_region(space, fA + t * (fB - fA) + a * np.clip(_smooth_random(space, rng, fA), -1, 1), fA), \
        {"t": float(t), "amp": float(a)}


# ------------------------------------------------------------------ mutation
def bump(space, rng, fA, fB=None, guide=None):
    """M1: a smooth local bump or dent, 1-4 mm high, 5-15 mm wide."""
    g = _smooth_guide(space, guide)
    c = _pick(space, rng, _surface(space, fA), None if g is None else np.abs(g))
    if c is None:
        return fA.copy(), {"skip": "no surface"}
    a, r = rng.uniform(2.0, 6.0), rng.uniform(8.0, 20.0)
    sign = rng.choice([-1.0, 1.0])
    if g is not None:
        gi = g[tuple(np.argmin(np.abs(ax - v)) for ax, v in zip(space.axes, (c[0], c[1], c[2])))]
        sign = -1.0 if gi > 0 else 1.0                       # outward where the objective falls for an outward move
    return _in_region(space, fA + sign * a * np.exp(-(_dist(space, c) / r) ** 2), fA), \
        {"a": float(sign * a), "r": float(r), "guided": g is not None}


def cut(space, rng, fA, fB=None, guide=None):
    """M2: a through-window (from above or from the side) or a groove along the car, cut by a ball of at
    least the mill's radius. With a guide: where the surface wants to move in."""
    g = _smooth_guide(space, guide)
    kind = str(rng.choice(["window_z", "window_y", "groove_x"], p=[0.35, 0.25, 0.4]))
    rho = rng.uniform(BALL_R + 0.5, 7.0)
    stretch = rng.uniform(1.5, 4.0)
    if kind == "groove_x":
        c = _pick(space, rng, _surface(space, fA), None if g is None else np.clip(g, 0, None))
        if c is None:
            return fA.copy(), {"skip": "no surface"}
        half = rng.uniform(10.0, 35.0)
        dx = np.clip(np.abs(space.X - c[0]) - half, 0.0, None)
        d = np.sqrt(dx ** 2 + (space.Yabs - c[1]) ** 2 + (space.Z - c[2]) ** 2)
    else:
        deep = space.region & (fA >= rho + WALL / 2)          # leave a wall around the window
        c = _pick(space, rng, deep if deep.any() else _surface(space, fA),
                  None if g is None else ndimage.maximum_filter(np.clip(g, 0, None), size=int(2 * rho / space.h) + 1))
        if c is None:
            return fA.copy(), {"skip": "no pod"}
        other = (space.Yabs - c[1]) if kind == "window_z" else (space.Z - c[2])
        d = np.sqrt(((space.X - c[0]) / stretch) ** 2 + other ** 2)
    return _in_region(space, np.minimum(fA, d - rho), fA), {"kind": kind, "rho": float(rho), "guided": g is not None}


def fill(space, rng, fA, fB=None, guide=None):
    """M3: add material: a blob, a rib (>= 3 mm) across an opening, or a local closing of cuts."""
    g = _smooth_guide(space, guide)
    kind = str(rng.choice(["blob", "rib", "close"], p=[0.3, 0.4, 0.3]))
    near_air = space.region & (fA < 0) & (fA > -6.0)
    c = _pick(space, rng, near_air, None if g is None else ndimage.maximum_filter(np.clip(-g, 0, None), size=7))
    if c is None:
        return fA.copy(), {"skip": "no air near the pod"}
    if kind == "blob":
        add = rng.uniform(4.0, 9.0) - _dist(space, c)
    elif kind == "rib":
        t, R = rng.uniform(WALL, 6.0), rng.uniform(10.0, 20.0)
        C = space.X if rng.random() < 0.7 else space.Z
        add = np.minimum(t / 2 - np.abs(C - (c[0] if C is space.X else c[2])), R - _dist(space, c))
    else:
        r = int(round(rng.uniform(3.0, 5.0) / space.h))
        k = np.arange(-r, r + 1)
        ball = (k[:, None, None] ** 2 + k[None, :, None] ** 2 + k[None, None, :] ** 2) <= r * r
        B = fA > 0
        closed = ndimage.binary_closing(B, ball)
        fc = np.where(closed & ~B, 0.5 * space.h, fA)
        W = _win(space, c, rng.uniform(15.0, 30.0))
        return _in_region(space, fA + W * (fc - fA), fA), {"kind": kind}
    return _in_region(space, np.maximum(fA, add), fA), {"kind": kind, "guided": g is not None}


def pattern(space, rng, fA, fB=None, guide=None):
    """M4: an array of slots inside a window: period >= 3 mm rib + 6.35 mm ball. Ribs and windows as a family."""
    g = _smooth_guide(space, guide)
    c = _pick(space, rng, _surface(space, fA), None if g is None else np.clip(g, 0, None))
    if c is None:
        return fA.copy(), {"skip": "no surface"}
    P = rng.uniform(2 * BALL_R + WALL + 0.15, 14.0)
    s = rng.uniform(2 * BALL_R + 0.1, P - WALL)
    U = space.X if rng.random() < 0.8 else space.Z
    slot = np.abs(((U - rng.uniform(0, P)) % P) - P / 2) - s / 2            # < 0 inside a slot
    R = rng.uniform(12.0, 25.0)
    cutsdf = np.maximum(slot, _dist(space, c) - R)                          # slots, inside the window only
    if rng.random() < 0.5:                                                  # partial depth: grooves, not windows
        cutsdf = np.maximum(cutsdf, fA - rng.uniform(4.0, 10.0))
    return _in_region(space, np.minimum(fA, cutsdf), fA), {"period": float(P), "slot": float(s), "R": float(R)}


def offset(space, rng, fA, fB=None, guide=None):
    """M5: grow or shrink the surface by 0.5-2 mm, everywhere or inside a window."""
    a = rng.uniform(0.5, 2.0) * rng.choice([-1.0, 1.0])
    if rng.random() < 0.4:
        return _in_region(space, fA + a, fA), {"a": float(a), "whole": True}
    g = _smooth_guide(space, guide)
    c = _pick(space, rng, _surface(space, fA), None if g is None else np.abs(g))
    if c is None:
        return fA.copy(), {"skip": "no surface"}
    if g is not None:
        gi = g[tuple(np.argmin(np.abs(ax - v)) for ax, v in zip(space.axes, (c[0], c[1], c[2])))]
        a = -abs(a) if gi > 0 else abs(a)
    return _in_region(space, fA + a * _win(space, c, rng.uniform(10.0, 25.0), edge=8.0), fA), {"a": float(a)}


# ------------------------------------------------------------------ the adjoint's own move
def grad_step(space, f, g, step_mm, sigma_mm=4.5):
    """G: one step against a sensitivity g (objective per mm of outward move, per cell): the hybrid loop's
    rule (smooth, divide by the 95th percentile on the surface band, clip, times the step size).
    Outward where g < 0. The real car uses shape_loop.step_field, which adds the mass price."""
    gs = ndimage.gaussian_filter(g, sigma_mm / space.h) * space.region
    b = space.region & (np.abs(f) <= 1.5 * space.h)
    norm = np.percentile(np.abs(gs[b]), 95) if b.any() else 0.0
    if norm <= 0:
        return f.copy(), 0.0
    d = step_mm * np.clip(gs / norm, -1.0, 1.0)
    return f - d, float((g * (-d)).sum())                                   # the field, and first-order prediction


CROSSOVER = {"splice": splice, "graft": graft, "combine": combine, "line": line}
MUTATION = {"bump": bump, "cut": cut, "fill": fill, "pattern": pattern, "offset": offset}
OPS = {**CROSSOVER, **MUTATION}
