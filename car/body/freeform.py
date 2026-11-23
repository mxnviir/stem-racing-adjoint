"""freeform.py -- the searches' free-form body and nose (user 2026-11-23: no constant-width sidepods, no fixed
stations or squareness: only evolved, free-form).

The team mills the body from the top, the bottom and the sides with a 3.175 mm ball. Any body that process
makes is the solid between a TOP surface and a BOTTOM surface, inside a SIDE outline:

    { (x, y, z) :  bottom(x, |y|) <= z <= top(x, |y|),  |y| <= side(x, z) }

Each of the three is a smooth (bicubic) field over control points spread evenly from the nose tip to the
rear face: top and bottom over (x, |y|), the side half-width over (x, z). They are combined with a smooth
maximum (`blend_mm`), so where two meet the edge is rounded. The NOSE is the same surfaces ahead of Ref A
(a printed part): the body pipeline cuts the milled body at Ref A and the nose is meshed from the field
ahead of it, clipped to T8.5.1's box (|y| <= 15, z <= 25), T8.2's 40 mm and T3.7's 1.5 mm.

Everything else that makes a body legal is applied afterwards by param_body.build exactly as for any body:
the rule masks (cargo, chamber wall, halo pocket and container, T7.9 wheel zones, the block), the milling
(machining.make_machinable: the ball from top, bottom and sides, 3 mm walls), loose pieces, the mass skin.
Added here, because it lived only in the old loft's bounds: nothing outboard of the spine (|y| > 12.5 mm,
the halo pocket's half-width) between the wheels is higher than SIDEPOD_TOP_MM (the team's 27.175 mm).

fit() reads the three fields off any car (its body and nose meshes), so a search starts from a real car.
"""
from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import dataclass

import numpy as np

Y_MAX_MM = 36.0                 # top/bottom fields over |y| in 0 .. this
Z_MAX_MM = 52.0                 # side field over z in 0 .. this
SIDEPOD_TOP_MM = 27.175         # team: nothing above this outboard of the spine between the wheels
SPINE_HALF_MM = 12.5            # the spine: the halo pocket's half-width (Appendix ix: 25 mm wide)
NOSE_HALF_MAX_MM = 15.0         # T8.5.1
NOSE_Z_MAX_MM = 25.0            # T8.5.1
NOSE_OVERHANG_MM = 40.0         # T8.2
TRACK_MM = 1.5                  # T3.7
MARGIN_MM = 0.2


@dataclass(frozen=True)
class Freeform:
    nu: int = 12                # control points along the car (nose tip .. rear face)
    nv: int = 4                 # across (|y| 0 .. Y_MAX_MM), for top and bottom
    nw: int = 6                 # up (z 0 .. Z_MAX_MM), for the side
    top: tuple = ()             # nu*nv heights, mm
    bottom: tuple = ()          # nu*nv heights, mm
    side: tuple = ()            # nu*nw half-widths, mm
    blend_mm: float = 1.5       # rounding where two surfaces meet
    x_tip_mm: float = 0.0       # the fields run from the nose tip ...
    x_rear_mm: float = 240.0    # ... to the rear face (car frame, mm): the layout they were drawn for

    def grids(self):
        return (np.asarray(self.top, float).reshape(self.nu, self.nv),
                np.asarray(self.bottom, float).reshape(self.nu, self.nv),
                np.asarray(self.side, float).reshape(self.nu, self.nw))

    def as_dict(self):
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in dataclasses.asdict(self).items()}

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()})


def _interp(grid, a, b):
    """Cubic interpolation of a control grid at fractional coordinates a, b in [0, 1] (arrays)."""
    from scipy import ndimage
    n0, n1 = grid.shape
    c0 = np.clip(a, 0.0, 1.0) * (n0 - 1)
    c1 = np.clip(b, 0.0, 1.0) * (n1 - 1)
    return ndimage.map_coordinates(grid, [c0.ravel(), c1.ravel()], order=3, mode="nearest").reshape(np.shape(a))


def _smax(a, b, k):
    if k <= 0:
        return np.maximum(a, b)
    h = np.clip(0.5 + 0.5 * (a - b) / k, 0.0, 1.0)
    return a * h + b * (1 - h) + k * h * (1 - h)


def surfaces(ff: Freeform, X, Y, Z, x_tip, x_rear):
    T, B, S = ff.grids()
    u = (X - x_tip) / (x_rear - x_tip)
    v = np.abs(Y) / Y_MAX_MM
    w = Z / Z_MAX_MM
    return _interp(T, u, v), _interp(B, u, v), _interp(S, u, w)


def field(ff: Freeform, X, Y, Z, x_tip, x_rear, axles=None):
    """Signed distance-like field (mm, negative inside) of the drawn body + nose on grids X, Y, Z (mm).
    axles = (x_front_axle, x_rear_axle, R): between the wheels, nothing outboard of the spine above the
    sidepod top."""
    top, bot, side = surfaces(ff, X, Y, Z, x_tip, x_rear)
    k = ff.blend_mm
    phi = _smax(_smax(Z - top, bot - Z, k), np.abs(Y) - side, k)
    phi = np.maximum(phi, np.maximum(x_tip - X, X - x_rear))
    if axles is not None:
        xf, xr, R = axles
        between = (X > xf) & (X < xr)
        cap = np.minimum(Z - SIDEPOD_TOP_MM, np.abs(Y) - SPINE_HALF_MM)   # > 0 above the top AND outboard of the spine
        phi = np.where(between, np.maximum(phi, cap), phi)
    return phi


# ------------------------------------------------------------------ fitting to a car
def fit(meshes_mm, x_tip, x_rear, nu=12, nv=4, nw=6, blend_mm=1.5, step=0.5) -> Freeform:
    """The three fields read off a car: meshes_mm = closed solids in mm (both halves or the right half;
    the body and the nose). Each control point takes the car's own value there (top/bottom: the highest
    and lowest solid over (x, |y|); side: the widest solid at (x, z)), smoothed over its cell; control
    points off the car take the nearest value on it (so the field is smooth), where the other two fields
    then leave no solid."""
    import trimesh
    m = trimesh.util.concatenate(meshes_mm)
    us = np.linspace(0.0, 1.0, nu)
    xs = x_tip + us * (x_rear - x_tip)
    # columns over (x, |y|): rays down; rows over (x, z): rays in -y from outside
    vs = np.linspace(0.0, 1.0, nv) * Y_MAX_MM
    ws = np.linspace(0.0, 1.0, nw) * Z_MAX_MM
    half_cell = 0.5 * (x_rear - x_tip) / (nu - 1)

    def col(x, y):
        xx = np.arange(x - half_cell, x + half_cell + 1e-9, step)
        O = np.c_[xx, np.full(len(xx), y), np.full(len(xx), 200.0)]
        loc, ri, _ = m.ray.intersects_location(O, np.tile([0, 0, -1.0], (len(O), 1)), multiple_hits=True)
        if len(loc) == 0:
            return np.nan, np.nan
        return float(np.median([loc[ri == i, 2].max() for i in np.unique(ri)])), \
            float(np.median([loc[ri == i, 2].min() for i in np.unique(ri)]))

    def row(x, z):
        xx = np.arange(x - half_cell, x + half_cell + 1e-9, step)
        O = np.c_[xx, np.full(len(xx), 200.0), np.full(len(xx), z)]
        loc, ri, _ = m.ray.intersects_location(O, np.tile([0, -1.0, 0], (len(O), 1)), multiple_hits=True)
        if len(loc) == 0:
            return np.nan
        return float(np.median([np.abs(loc[ri == i, 1]).max() for i in np.unique(ri)]))
    T = np.full((nu, nv), np.nan); B = np.full((nu, nv), np.nan); S = np.full((nu, nw), np.nan)
    for i, x in enumerate(xs):
        for j, y in enumerate(vs):
            T[i, j], B[i, j] = col(x, max(y, 0.05))
        for j, z in enumerate(ws):
            S[i, j] = row(x, z)
    T, B, S = (_fill(g) for g in (T, B, S))
    # off the car: top below bottom there (no solid), the side drawn in to 0
    return Freeform(nu=nu, nv=nv, nw=nw, top=tuple(T.ravel()), bottom=tuple(B.ravel()),
                    side=tuple(np.maximum(S, 0.0).ravel()), blend_mm=blend_mm, x_tip_mm=float(x_tip), x_rear_mm=float(x_rear))


def _fill(g):
    """NaNs (control points off the car) take the nearest value on it."""
    from scipy import ndimage
    bad = np.isnan(g)
    if not bad.any():
        return g
    if bad.all():
        return np.zeros_like(g)
    idx = ndimage.distance_transform_edt(bad, return_distances=False, return_indices=True)
    return g[tuple(idx)]


# ------------------------------------------------------------------ the nose
def build_nose(ff: Freeform, x_tip, x_rear, ref_a, blend_after_mm=1.0, h=0.25):
    """The printed nose: the field ahead of Ref A (and blend_after_mm into the body), clipped to T8.5.1's
    box, T8.2's 40 mm and T3.7's 1.5 mm. Returns {"nose": right half (trimesh, m), "_full": both halves (m)},
    like nose.build_nose."""
    import trimesh
    from skimage import measure
    x0 = max(x_tip, ref_a - NOSE_OVERHANG_MM + MARGIN_MM) - 1.0
    x1 = ref_a + blend_after_mm
    xs = np.arange(x0, x1 + h, h)
    ys = np.arange(-NOSE_HALF_MAX_MM - 1.0, NOSE_HALF_MAX_MM + 1.0 + h, h)
    zs = np.arange(0.0, NOSE_Z_MAX_MM + 1.0 + h, h)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    phi = field(ff, X, Y, Z, x_tip, x_rear)
    box = np.maximum.reduce([np.abs(Y) - (NOSE_HALF_MAX_MM - MARGIN_MM), Z - (NOSE_Z_MAX_MM - MARGIN_MM),
                             (TRACK_MM + MARGIN_MM) - Z, (ref_a - NOSE_OVERHANG_MM + MARGIN_MM) - X, X - x1])
    phi = np.maximum(phi, box)
    if (phi < 0).sum() < 10:
        return None
    phi = np.pad(phi, 1, constant_values=1.0)
    v, f, _, _ = measure.marching_cubes(phi, 0.0, spacing=(h, h, h))
    v = v - h + np.array([x0, ys[0], zs[0]])
    import manifold3d as mf
    full = trimesh.Trimesh(v, f[:, ::-1], process=True)
    if full.volume < 0:
        full.invert()
    M = mf.Manifold(mf.Mesh(vert_properties=np.asarray(full.vertices, np.float32), tri_verts=np.asarray(full.faces, np.uint32)))
    pcs = sorted(M.decompose(), key=lambda q: -q.volume())
    if not pcs:
        return None
    M = pcs[0]
    def tm(Q):
        g = Q.to_mesh()
        t = trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts), process=True)
        t.apply_scale(1e-3)
        return t
    half = M ^ mf.Manifold.cube([1e3, 1e3, 1e3]).translate([-500.0, 0.0, -500.0])     # y >= 0, closed
    return {"nose": tm(half), "_full": tm(M)}


# ------------------------------------------------------------------ the search's numbers
def coarse_grid_shapes(gu=5, gv=2, gw=3):
    return {"top": (gu, gv), "bottom": (gu, gv), "side": (gu, gw)}


def n_genes(gu=5, gv=2, gw=3) -> int:
    return sum(a * b for a, b in coarse_grid_shapes(gu, gv, gw).values())


def from_unit(seed: Freeform, u, amp_mm=(6.0, 6.0, 6.0), gu=5, gv=2, gw=3) -> Freeform:
    """Stage 2: the seed's fields moved by a coarse grid of control displacements (CMA's numbers, mm per unit:
    amp_mm for top, bottom, side), cubic-interpolated onto the seed's own control grid. A coarse grid keeps
    the number of free numbers to what the CFD runs can search; a finer one is a setting (gu, gv, gw)."""
    from scipy import ndimage
    u = np.asarray(u, float)
    T, B, S = seed.grids()
    out, i = [], 0
    for g, (a, b), amp in zip((T, B, S), coarse_grid_shapes(gu, gv, gw).values(), amp_mm):
        c = u[i:i + a * b].reshape(a, b); i += a * b
        ca = np.linspace(0, a - 1, g.shape[0]); cb = np.linspace(0, b - 1, g.shape[1])
        CA, CB = np.meshgrid(ca, cb, indexing="ij")
        d = ndimage.map_coordinates(c, [CA.ravel(), CB.ravel()], order=min(3, max(a, b) - 1) if min(a, b) > 1 else 1,
                                    mode="nearest").reshape(g.shape)
        out.append(g + amp * d)
    T2, B2, S2 = out
    return dataclasses.replace(seed, top=tuple(T2.ravel()), bottom=tuple(B2.ravel()), side=tuple(np.maximum(S2, 0.0).ravel()))


def dumps(ff: Freeform) -> str:
    return json.dumps(ff.as_dict())
