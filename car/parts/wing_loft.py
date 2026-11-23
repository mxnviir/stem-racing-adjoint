"""wing_loft.py -- a wing's support as a loft, the way the halo is lofted to the cartridge (user 2026-11-23:
"similar to the halo loft in the way that it can attach on the sides of the wings and connect it to the
rest ... not fixed struts").

A support leaves the wing from a PATCH of it -- a part of the wing's planform, anywhere along the span up to
the tip (its side), over part or all of the chord -- and arrives at the FOOT, the nearest point of whatever
it joins (the body for the rear wing, the nose for the front). Between them every horizontal slice is a
rounded rectangle whose centre runs from the patch's to the foot's and whose size blends (smoothstep) from
the patch's to the foot's (foot_scale times it), pinched at mid-height by `waist`: a smooth morph from one
outline to the other, as the halo's loft blends its rear face into the cartridge's circle. The only numbers
are the patch (where, how wide, how much of the chord), the foot's scale and the waist; where it lands is
the geometry's.

It starts at the wing's mid-plane (inside the wing: nothing pokes through its far surface) and runs on past
the foot into what it joins; the caller trims it to that surface (a glued, conforming base) or prints it
with it (the nose)."""
from __future__ import annotations

import numpy as np


def _rbox(X, Y, cx, cy, hx, hy, r):
    """Signed distance (negative inside) to a rounded rectangle, half sizes hx, hy, corner radius r."""
    r = np.minimum(r, np.minimum(hx, hy))
    qx = np.abs(X - cx) - (hx - r)
    qy = np.abs(Y - cy) - (hy - r)
    return np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0)) + np.minimum(np.maximum(qx, qy), 0.0) - r


def loft(patch, z_top, foot_xy, z_foot, foot_scale=1.0, waist=0.0, past_mm=4.0, h=0.2, corner=0.45):
    """The support as a closed solid (trimesh, mm), or None.
    patch = (x0, x1, y0, y1) on the wing's mid-plane at z_top; the foot centred at foot_xy, at z_foot (above
    or below z_top), its half sizes foot_scale times the patch's; waist: the slices' size down by this share
    half way; past_mm: run on past the foot; corner: corner radius as a share of the smaller half size."""
    import trimesh
    from skimage import measure
    x0, x1, y0, y1 = patch
    cxa, cya, hxa, hya = 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (x1 - x0), 0.5 * (y1 - y0)
    cxb, cyb = foot_xy
    hxb, hyb = hxa * foot_scale, hya * foot_scale
    up = z_foot > z_top
    z_end = z_foot + (past_mm if up else -past_mm)
    zlo, zhi = min(z_top, z_end), max(z_top, z_end)
    pad = 1.0
    xs = np.arange(min(cxa - hxa, cxb - hxb) - pad, max(cxa + hxa, cxb + hxb) + pad + h, h)
    ys = np.arange(min(cya - hya, cyb - hyb) - pad, max(cya + hya, cyb + hyb) + pad + h, h)
    zs = np.arange(zlo - pad, zhi + pad + h, h)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    t = np.clip((Z - z_top) / (z_foot - z_top), 0.0, 1.0)
    s = t * t * (3.0 - 2.0 * t)
    pinch = 1.0 - waist * np.sin(np.pi * t)
    cx, cy = cxa + t * (cxb - cxa), cya + t * (cyb - cya)
    hx = ((1 - s) * hxa + s * hxb) * pinch
    hy = ((1 - s) * hya + s * hyb) * pinch
    d = _rbox(X, Y, cx, cy, hx, hy, corner * np.minimum(hx, hy))
    d = np.maximum(d, np.maximum(zlo - Z, Z - zhi))
    if (d < 0).sum() < 8:
        return None
    d = np.pad(d, 1, constant_values=1.0)
    v, f, _, _ = measure.marching_cubes(d, 0.0, spacing=(h, h, h))
    v = v - h + np.array([xs[0], ys[0], zs[0]])
    m = trimesh.Trimesh(v, f[:, ::-1], process=True)
    if m.volume < 0:
        m.invert()
    import manifold3d as mf
    import support_engine as se
    M = se._to_manifold(m)
    pcs = sorted(M.decompose(), key=lambda q: -q.volume())
    if not pcs:
        return None
    return se._to_trimesh(pcs[0].simplify(0.01))


def first_hit(m, o, d):
    """The first surface of m from o along d (mm), or None."""
    loc, _, _ = m.ray.intersects_location(np.asarray(o, float)[None], (np.asarray(d, float) / np.linalg.norm(d))[None],
                                          multiple_hits=True)
    if not len(loc):
        return None
    return loc[np.argmin(np.linalg.norm(loc - o, axis=1))]
