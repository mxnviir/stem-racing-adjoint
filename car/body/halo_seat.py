"""halo_seat.py -- where the halo sits, from the official halo itself (user 2026-11-23: "why is the halo
recessed? it has to be smooth and continuous, just that nothing can block the visibility of the halo from
front or side").

Appendix ix: the pocket is 3.175 mm deep with its floor at 24.0 mm (T4.4.4), cut with the 6.35 mm ball. A
ball as deep as its own radius makes walls that are a quarter circle all the way up, and the official
halo's base is rounded to sit in exactly that. So the seat here is the ball's own cut: the ball's centre
runs at the rim height (24 + 3.175) round the halo's outline at the rim, set in by the ball's radius, and
everything it sweeps below the rim is air, down to the flat floor at 24.0. The halo sits in it with a
0.1-0.4 mm gap all round; the body meets the halo's base flush at the rim, with no trench.

The old model was the pocket's 50 x 25 mm bounding box with square walls and, over it, a 25 x 21 mm box
(z 24-45) standing in for the halo: square trenches beside the halo's rounded base, square shoulders in
front and side.

Above the rim (all of it is the halo's or the views'):
  * over the halo's plan outline, air all the way up (T4.4.3: nothing above it in plan view);
  * the front and side views (T4.4.2): air ahead of the halo and beside it, from the rim to the halo's top,
    across its width and along its length. The rule's diagram lets a 4 mm base fillet be hidden; here
    nothing above the rim may stand in either view (user 2026-11-23), so the body meets the rim flush.

Fields are positive inside the air (mm), like exact_zones; meshes are manifold3d solids in metres, for the
exact cut (exact_zones.cut_boxes)."""
from __future__ import annotations

import functools

import numpy as np

from geometry_contract import HALO_MIN_Z_MM

DEPTH_MM = 3.175              # Appendix ix: the pocket's depth, = the 6.35 mm ball's radius
BALL_R_MM = 3.175             # the cutter
TOL_MM = 0.1                  # fit: the seat stands this far off the halo
RIM_Z_MM = HALO_MIN_Z_MM + DEPTH_MM
_H = 0.05                     # mm: the 2-D distance grids
REAR_FACE_MM = 3.0            # the halo's rear face: what shows from behind over its last 3 mm
LOFT_COVER_MM = 0.3           # the loft starts this much larger than the rear face all round


@functools.lru_cache(maxsize=1)
def _halo_local():
    """The official halo (both halves, mm), its front at x = 0."""
    import trimesh
    import hardware_geometry as hg
    h = hg.build_halo(0.0, 0.0)
    m = trimesh.util.concatenate([h["halo_left"], h["halo_right"]])
    m.apply_scale(1e3)
    m.apply_translation([-m.bounds[0, 0], 0.0, 0.0])
    return m


def _poly(tris2d):
    import shapely
    from shapely.geometry import Polygon
    a = tris2d[:, 1] - tris2d[:, 0]
    b = tris2d[:, 2] - tris2d[:, 0]
    area = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])
    ps = shapely.polygons(tris2d[area > 1e-10])
    return shapely.unary_union(ps).buffer(0)


@functools.lru_cache(maxsize=1)
def outlines():
    """{"plan": the halo's whole plan outline (x from its front, |y|), "rim": its section at the rim,
    "length", "half_w", "top"} -- shapely polygons in mm, symmetric in y."""
    m = _halo_local()
    tri = m.triangles
    plan = _poly(tri[:, :, :2])
    import shapely
    from shapely.geometry import Polygon
    s = m.section(plane_origin=np.array([0.0, 0.0, RIM_Z_MM]), plane_normal=np.array([0.0, 0.0, 1.0]))
    # each closed loop of the cut as a polygon (x, y); the halves' loops meet on y = 0 and union into one
    rim = shapely.unary_union([Polygon(L[:, :2]).buffer(0) for L in s.discrete if len(L) > 3]).buffer(0) \
        if s is not None else plan
    b = m.bounds
    # the rear face: what of the halo shows from behind over its last REAR_FACE_MM (y, z)
    L = float(b[1, 0] - b[0, 0])
    keep = tri[:, :, 0].min(axis=1) >= L - REAR_FACE_MM
    rear = _poly(tri[keep][:, :, 1:])
    return {"plan": plan, "rim": rim, "rear": rear, "length": L, "half_w": float(b[1, 1]),
            "top": float(b[1, 2])}


@functools.lru_cache(maxsize=4)
def _sdf2(which: str, grow_mm: float = 0.0):
    """A 2-D signed distance (mm, negative inside) to an outline, sampled on a _H grid: (x0, y0, grid)."""
    import shapely
    P = outlines()[which].buffer(grow_mm) if grow_mm else outlines()[which]
    x0, y0, x1, y1 = P.bounds
    pad = 6.0
    xs = np.arange(x0 - pad, x1 + pad + _H, _H)
    ys = np.arange(min(y0, -y1) - pad, max(y1, -y0) + pad + _H, _H)
    XX, YY = np.meshgrid(xs, ys, indexing="ij")
    pts = shapely.points(XX.ravel(), YY.ravel())
    d = shapely.distance(P.boundary, pts).reshape(XX.shape)
    inside = shapely.contains_xy(P, XX.ravel(), YY.ravel()).reshape(XX.shape)
    return xs[0], ys[0], np.where(inside, -d, d).astype(np.float32)


def _sample(which, x, y, grow_mm=0.0):
    from scipy.ndimage import map_coordinates
    x0, y0, g = _sdf2(which, grow_mm)
    i = (np.asarray(x, float) - x0) / _H
    j = (np.asarray(y, float) - y0) / _H
    inside = (i >= 0) & (i <= g.shape[0] - 1) & (j >= 0) & (j <= g.shape[1] - 1)
    v = map_coordinates(g, [np.clip(i, 0, g.shape[0] - 1).ravel(), np.clip(j, 0, g.shape[1] - 1).ravel()],
                        order=1, mode="nearest").reshape(np.shape(x))
    # off the grid: at least the distance to the grid's edge further out (exact enough: far from the halo)
    far = np.hypot(np.maximum(0, np.maximum(x0 - x, x - (x0 + (g.shape[0] - 1) * _H))),
                   np.maximum(0, np.maximum(y0 - y, y - (y0 + (g.shape[1] - 1) * _H))))
    return np.where(inside, v, v + far)


def seat_air(X, aY, Z, x_front_mm):
    """The halo, the ball-cut seat under it and the air above it (T4.4.3), positive inside (mm).
    x_front_mm: the halo's front (the pocket's front, halo_pocket.compute_halo_pocket_box_m)."""
    x = np.asarray(X, float) - x_front_mm
    d_rim = _sample("rim", x, aY)
    d_in = d_rim + BALL_R_MM                                   # to the ball centre's path, set in by its radius
    below = BALL_R_MM + TOL_MM - np.hypot(np.maximum(d_in, 0.0), np.minimum(np.asarray(Z, float) - RIM_Z_MM, 0.0))
    below = np.minimum(below, np.asarray(Z, float) - HALO_MIN_Z_MM)          # the floor, flat at 24.0
    above = np.minimum(TOL_MM - _sample("plan", x, aY), np.asarray(Z, float) - RIM_Z_MM)
    return np.maximum(below, above)


def view_air(X, aY, Z, x_front_mm, margin_mm=0.0):
    """T4.4.2, as the user asks it: nothing above the rim ahead of the halo across its width, nor beside
    it along its length, up to its top. Positive inside (mm)."""
    o = outlines()
    x = np.asarray(X, float) - x_front_mm
    Z = np.asarray(Z, float)
    zs = np.minimum(Z - RIM_Z_MM + margin_mm, o["top"] + margin_mm - Z)
    front = np.minimum.reduce([margin_mm - x, o["half_w"] + margin_mm - aY, zs])
    side = np.minimum.reduce([x + margin_mm, o["length"] + margin_mm - x, zs])
    return np.maximum(front, side)


def box_mm(x_front_mm):
    """The halo's bounding box in place: (x0, x1, half_w, top)."""
    o = outlines()
    return x_front_mm, x_front_mm + o["length"], o["half_w"], o["top"]


def seat_manifold_m(x_front_mm, grow_mm=0.0):
    """seat_air as a closed solid (manifold3d, metres): the plan outline from the rim up, and below the rim
    the ball swept round the rim outline set in by its radius, cut at the floor."""
    import manifold3d as mf
    o = outlines()
    up = 200.0

    def xsec(P):
        from shapely.geometry.polygon import orient
        polys = [P] if P.geom_type == "Polygon" else list(P.geoms)
        return mf.CrossSection([np.asarray(orient(q, 1.0).exterior.coords)[:-1] for q in polys])   # counter-clockwise
    plan = o["plan"].buffer(TOL_MM + grow_mm)
    prism = mf.Manifold.extrude(xsec(plan), up).translate([0.0, 0.0, RIM_Z_MM])
    inset = o["rim"].buffer(-BALL_R_MM)
    path = mf.Manifold.extrude(xsec(inset), 1e-3).translate([0.0, 0.0, RIM_Z_MM - 5e-4])
    ball = mf.Manifold.sphere(BALL_R_MM + TOL_MM + grow_mm, 48)
    swept = path.minkowski_sum(ball)
    cut = mf.Manifold.cube([1e3, 1e3, RIM_Z_MM - HALO_MIN_Z_MM + grow_mm + 1e-3]).translate(
        [-500.0, -500.0, HALO_MIN_Z_MM - grow_mm])
    seat = (swept ^ cut) + prism
    return seat.translate([x_front_mm, 0.0, 0.0]).scale([1e-3, 1e-3, 1e-3])


def view_manifolds_m(x_front_mm, grow_mm=0.0):
    """view_air's two boxes as solids (metres), each grown by grow_mm."""
    import manifold3d as mf
    o = outlines()
    g = grow_mm
    z0, z1 = RIM_Z_MM - g, o["top"] + g
    front = mf.Manifold.cube([500.0, 2 * (o["half_w"] + g), z1 - z0]).translate([x_front_mm + g - 500.0, -(o["half_w"] + g), z0])
    side = mf.Manifold.cube([o["length"] + 2 * g, 1000.0, z1 - z0]).translate([x_front_mm - g, -500.0, z0])
    return [b.scale([1e-3, 1e-3, 1e-3]) for b in (front, side)]


def loft_solid(X, aY, Z, x_rear_mm, x_can_mm, z_can_mm, r_can_mm):
    """The body that must join the halo to the cartridge (user 2026-11-23: "the loft connects 100% of the
    halo face to the canister"): from the halo's whole rear face (LOFT_COVER_MM larger all round) at its
    rear, x_rear_mm, to the circle of the cartridge's T5.5 safety zone (radius r_can_mm about z_can_mm) at
    the chamber's front, x_can_mm -- each section a blend of the two outlines' distance fields (a
    smoothstep along x). Negative inside (mm). A lower bound only: the body may be bigger anywhere."""
    x = np.asarray(X, float)
    t = np.clip((x - x_rear_mm) / max(x_can_mm - x_rear_mm, 1e-6), 0.0, 1.0)
    s = t * t * (3.0 - 2.0 * t)
    d0 = _sample("rear", aY, Z) - LOFT_COVER_MM
    d1 = np.hypot(aY, np.asarray(Z, float) - z_can_mm) - r_can_mm
    d = (1.0 - s) * d0 + s * d1
    return np.maximum(d, np.maximum(x_rear_mm - x, x - x_can_mm))


def loft_manifold_m(x_rear_mm, x_can_mm, z_can_mm, r_can_mm, n_x=24, n_ring=160, h=0.05):
    """loft_solid as a closed solid (manifold3d, metres, the right half y >= 0): its zero level traced on
    n_x sections from x_rear_mm (+ TOL_MM, the seat's own fit) to the chamber's front, each resampled to
    n_ring points by angle round the section's centre, and lofted. The body is joined to it exactly
    (exact_zones.cut_boxes): on the field's grid the loft started up to a cell behind the halo's face and
    the mesh's rounding took the face's outer 1-2 mm off (95.7 % of the face backed, halo_test G00)."""
    import manifold3d as mf
    import trimesh
    from skimage import measure
    import support_engine as se
    xs = np.linspace(x_rear_mm + TOL_MM, x_can_mm + 0.5, n_x)
    ys = np.arange(-22.0, 22.0 + h, h)
    zs = np.arange(10.0, z_can_mm + r_can_mm + 6.0, h)
    YY, ZZ = np.meshgrid(ys, zs, indexing="ij")
    rings = []
    for x in xs:
        f = loft_solid(np.full(YY.shape, min(x, x_can_mm)), np.abs(YY), ZZ, x_rear_mm, x_can_mm, z_can_mm, r_can_mm)
        cs = measure.find_contours(f, 0.0)
        if not cs:
            return None
        c = max(cs, key=len)
        P = np.c_[ys[0] + c[:, 0] * h, zs[0] + c[:, 1] * h]
        ctr = P.mean(axis=0)
        ang = np.arctan2(P[:, 1] - ctr[1], P[:, 0] - ctr[0])
        o = np.argsort(ang)
        a, Q = ang[o], P[o]
        want = np.linspace(-np.pi, np.pi, n_ring, endpoint=False)
        # radius at each wanted angle (the sections are star-shaped about their centre)
        r = np.hypot(Q[:, 0] - ctr[0], Q[:, 1] - ctr[1])
        ri = np.interp(want, np.r_[a - 2 * np.pi, a, a + 2 * np.pi], np.r_[r, r, r])
        rings.append(np.c_[np.full(n_ring, x), ctr[0] + ri * np.cos(want), ctr[1] + ri * np.sin(want)])
    n, N = n_ring, len(rings)
    V = np.vstack(rings + [rings[0].mean(0)[None], rings[-1].mean(0)[None]])
    F = []
    for i in range(N - 1):
        for j in range(n):
            a_, b_ = i * n + j, i * n + (j + 1) % n
            c_, d_ = (i + 1) * n + j, (i + 1) * n + (j + 1) % n
            F += [(a_, b_, d_), (a_, d_, c_)]
    c0, c1 = N * n, N * n + 1
    for j in range(n):
        F.append((c0, (j + 1) % n, j))
        F.append((c1, (N - 1) * n + j, (N - 1) * n + (j + 1) % n))
    m = trimesh.Trimesh(V, np.array(F), process=False)
    if m.volume < 0:
        m.invert()
    M = se._to_manifold(m) ^ mf.Manifold.cube([1e3, 1e3, 1e3]).translate([-500.0, 0.0, -500.0])
    return M.scale([1e-3, 1e-3, 1e-3])
