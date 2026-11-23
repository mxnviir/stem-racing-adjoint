"""wing_loft.py -- a wing's support as a loft from the wing's SIDE, the way the halo is lofted to the cartridge
(user 2026-11-23: "similar to the halo loft ... attach on the sides of the wings and connect it to the rest";
"they should be on the sides of the wing where the aerofoil is").

A support covers an END FACE of the wing -- the face where its aerofoil shows: a rear wing's tip, a split
front wing's inner end -- with a plate (the PATCH: the face's outline, extended along the chord and above /
below the wing as the search likes) and carries it, slice by slice along a chosen axis, to the FOOT on
whatever it joins (the body, the nose): every slice a rounded rectangle whose centre runs from the patch's
to the foot's and whose size blends (smoothstep) from the patch's to the foot's (foot_scale times it),
pinched half way by `waist` -- a morph from one outline to the other, as the halo's loft blends its rear face
into the cartridge's circle. Before the morph starts the plate holds the patch's outline for `hold_mm` (over
the wing's end face). Where it lands is the geometry's (the caller finds the foot).

The rules this serves (STEM Racing Professional Class Technical Regulations 2026-2027): T1.6.1 a front wing
support joins the wing to the nose cone, ahead of Ref A (T8.5.1: within 15 mm of the centre line, 25 mm
high); T1.6.2 a rear wing support joins the wing to the body behind Ref B (T9.4.1); T1.6.3 what is outside
the minimum span is end plate; T8.7 / T9.6 the 5 mm clear air, checked with a 5 mm ball on a rod, so the
fillet where a wing meets its support is allowed; appendix iv's rear wings all stand on side supports."""
from __future__ import annotations

import numpy as np

AXES = {"z": (0, 1, 2), "y": (0, 2, 1)}       # (u, v, w): the slices' in-plane axes and the loft's axis


def _rbox(U, V, cu, cv, hu, hv, r):
    """Signed distance (negative inside) to a rounded rectangle, half sizes hu, hv, corner radius r."""
    r = np.minimum(r, np.minimum(hu, hv))
    qu = np.abs(U - cu) - (hu - r)
    qv = np.abs(V - cv) - (hv - r)
    return np.hypot(np.maximum(qu, 0.0), np.maximum(qv, 0.0)) + np.minimum(np.maximum(qu, qv), 0.0) - r


def loft(patch, w_top, foot_uv, w_foot, foot_scale=1.0, waist=0.0, past_mm=4.0, hold_mm=0.0, axis="z",
         h=0.2, corner=0.45):
    """The support as a closed solid (manifold3d, mm), or None.
    axis: the loft runs along "z" (slices in x, y) or "y" (slices in x, z). patch = (u0, u1, v0, v1): the plate
    at w_top, held for hold_mm on the side away from the foot; the foot centred at foot_uv at w_foot, its
    half sizes foot_scale times the patch's; waist: the slices' size down by this share half way; past_mm:
    run on past the foot; corner: corner radius as a share of the smaller half size."""
    import trimesh
    from skimage import measure
    u0, u1, v0, v1 = patch
    cua, cva, hua, hva = 0.5 * (u0 + u1), 0.5 * (v0 + v1), 0.5 * (u1 - u0), 0.5 * (v1 - v0)
    cub, cvb = foot_uv
    hub, hvb = hua * foot_scale, hva * foot_scale
    sgn = 1.0 if w_foot > w_top else -1.0
    w_start, w_end = w_top - sgn * hold_mm, w_foot + sgn * past_mm
    wlo, whi = min(w_start, w_end), max(w_start, w_end)
    pad = 1.0
    us = np.arange(min(cua - hua, cub - hub) - pad, max(cua + hua, cub + hub) + pad + h, h)
    vs = np.arange(min(cva - hva, cvb - hvb) - pad, max(cva + hva, cvb + hvb) + pad + h, h)
    ws = np.arange(wlo - pad, whi + pad + h, h)
    U, V, Wc = np.meshgrid(us, vs, ws, indexing="ij")
    t = np.clip((Wc - w_top) / (w_foot - w_top), 0.0, 1.0)
    s = t * t * (3.0 - 2.0 * t)
    pinch = 1.0 - waist * np.sin(np.pi * t)
    cu, cv = cua + s * (cub - cua), cva + s * (cvb - cva)
    hu = ((1 - s) * hua + s * hub) * pinch
    hv = ((1 - s) * hva + s * hvb) * pinch
    # the plate over the wing's end face keeps square corners (rounded ones cut the face's leading and
    # trailing edges where the plate barely passes them); the corners round off as it lofts away
    d = _rbox(U, V, cu, cv, hu, hv, corner * np.minimum(hu, hv) * np.where(t <= 0.0, 0.0, 0.15 + 0.85 * s))
    d = np.maximum(d, np.maximum(wlo - Wc, Wc - whi))
    if (d < 0).sum() < 8:
        return None
    d = np.pad(d, 1, constant_values=1.0)
    vtx, f, _, _ = measure.marching_cubes(d, 0.0, spacing=(h, h, h))
    vtx = vtx - h + np.array([us[0], vs[0], ws[0]])
    order = AXES[axis]
    P = np.zeros_like(vtx)
    for k, a in enumerate(order):               # (u, v, w) back to (x, y, z)
        P[:, a] = vtx[:, k]
    flip = axis == "y"                          # swapping two axes turns the faces inside out
    m = trimesh.Trimesh(P, f if flip else f[:, ::-1], process=True)
    if m.volume < 0:
        m.invert()
    import support_engine as se
    M = se._to_manifold(m)
    pcs = sorted(M.decompose(), key=lambda q: -q.volume())
    if not pcs:
        return None
    return pcs[0].simplify(0.01)                # a manifold3d solid (mm): the callers' Booleans take it as it is


def first_hit(m, o, d):
    """The first surface of m from o along d (mm), or None."""
    loc, _, _ = m.ray.intersects_location(np.asarray(o, float)[None], (np.asarray(d, float) / np.linalg.norm(d))[None],
                                          multiple_hits=True)
    if not len(loc):
        return None
    return loc[np.argmin(np.linalg.norm(loc - o, axis=1))]


def to_trimesh(M):
    """A manifold3d solid as a closed trimesh: its own mesh if that is closed, else support_engine's
    cleaned one, else after merging its slivers (the weld alone opened a support: rear wing, 2026-11-23)."""
    import trimesh
    import support_engine as se
    g = M.to_mesh()
    t = trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts), process=True)
    if t.is_volume:
        return t
    for q in (M, M.simplify(0.01), M.simplify(0.03)):
        t = se._to_trimesh(q)
        if t.is_volume:
            return t
    return t
