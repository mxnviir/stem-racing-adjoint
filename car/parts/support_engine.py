"""support_engine.py -- the wheel supports the searches design for each car, from that car's body.

One printed part per axle, wheel to wheel (built as its right half, y >= 0, like every Part 4 part):

  saddle      flush with the body. Over a chord `chord_mm` at the axle the body's lowest
              `saddle_h_mm` (measured straight up from its underside) is printed instead of milled:
              the underside of the car is unchanged, the foam is milled away from below (a slot
              whose top corners are the ball's own radius) and the saddle is glued in. Where the
              body is too thin to leave the 3 mm foam wall over the slot (its rounded side), the
              whole column is printed, so the saddle wraps the body's edge and its outside is the
              body's own surface.
  arm         from the body's side to the disc: a lofted superellipse section (chord, thickness,
              exponent p), its underside level with the body's underside where it leaves the body,
              rising or falling to `dz_mm` about the axle at the disc, tapering by `taper`.
  transition  the arm's last `fillet_mm` before the disc grows into it as a concave fillet of that
              radius (the "small piece" between the support and the flat cylinder).
  disc        a flat cylinder inside the wheel's rim (beam_support's disc: radius, recess), and
  axle        beam_support's stub: flare, shoulder, the 3 mm journal through the 3x6x2.5 bearing,
              and the hubcap pressed on its end.

Only the disc and the axle (stub, flare, hubcap) come from beam_support.py; the saddle, the arm and
the transition are generated here, from the car's own body at each axle.

What the rules and the loads ask, and how it is enforced (each is also MEASURED on the result, gates()):
  T7.12.1  the support only inside the cylinder through the axle's wheels: everything is clipped to
           R - 0.1 of the axle; a saddle that would need clipping is narrowed instead (so no foam
           sliver is left over the slot).
  T7.13    the claw's annulus (1.5 mm in from the wheel's inner face, over its outer 1.5 mm of
           radius) is clear: inside that band the support stays within R - 1.65.
  T3.7     1.5 mm off the track.
  loads    beam_support's "normal racing loads" (3 N radial at the bearing, 1.2 N sideways at the
           tyre, ABS at 40 MPa / 2, 0.15 mm sag at the bearing). The arm and the saddle are
           measured on their real cut sections; when they fail, their thickness is grown and the
           part rebuilt (lightest that passes, at least what the design asks).
  machining  the slot is cut from below (every column of it starts at the body's underside) and
           leaves at least 3 mm of foam over it or none: measured column by column.
  foam     the saddle presses on the foam with the root moment: 6 M / (chord L^2) at most
           FOAM_BEARING_MPA (an assumption for 0.163 g/cm3 board: the team to confirm).

Mass: the part (ABS 1.04 g/cm3, as beam_support) less the foam its slot removes, at its own COM.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

import numpy as np

import beam_support as bsm          # the disc and the axle (stub, flare, hubcap), and the load constants
import component_contract as cc

EDGE_STEP_MM = 0.3                  # the slot's depth where its ends meet the underside
SLOT_TOL_MM = 0.1                   # machining tolerance on foam left under the slot
WELD_MM = 0.002                     # vertices closer than this are one (see _weld)
ROOT_IN_MM = 2.0                    # the plate's root, inside the body's side, when the floor has no flat part
ROOT_SEARCH_MM = 8.0                # where to look for the floor's flat part, inward of the side
ROOT_LEVEL = 0.05                   # within that run, the root is the outermost point this level
ROOT_SLOPE = 0.25                   # the floor counts as flat while it rises less than this per mm sideways
DISC_SAG_SHARE_MM = 0.05            # of the 0.15 mm at the bearing, what the disc's bending may take
FLUSH_STEP_MM = 0.08                # most the underside's rise may change between 0.1 mm samples across the join
TWIST_MM = 4.0                      # the plate's chordwise line goes from the floor's to level over this
EASE_MM = 2.0                       # the plate's underside eases from the floor's slope to level over this
SPECK_MM3 = 0.05                    # Boolean leftovers smaller than this are dropped (counted in specks_mm3)
FOAM_WALL_MM = 3.0                  # thinnest machined foam wall (geometry_contract)
FOAM_G_CM3 = 0.163
FOAM_BEARING_MPA = 0.5              # allowed bearing pressure of the saddle on the foam (1.0 MPa / 2): assumption
TRACK_MIN_MM = cc.TRACK_CLEARANCE_MIN
LIP_MM = bsm.CLAW_LIP_MM
ALLOW_MPA = bsm.ABS_STRENGTH_MPA / bsm.SAFETY
E_MPA = bsm.ABS_E_MPA
N_SECTION = 72                      # points round a section of the loft


@dataclass
class SupportDesign:
    chord_mm: float = 12.0          # plate chord (x) where it leaves the body; the saddle's is at least this
    t_mm: float = 2.0               # plate thickness (z), at least what the loads need
    taper: float = 1.0              # plate chord at the disc / at the body
    fillet_mm: float = 2.5          # the transition into the disc: concave fillet radius
    saddle_h_mm: float = 3.0        # saddle depth from the underside, at least what the loads need
    disc_r_mm: float = 12.0         # beam_support's disc
    disc_recess_mm: float = 1.0     # disc's outer face this far inside the wheel's inner face
    hubcap: bool = True
    material_g_cm3: float = bsm.ABS_G_CM3


def params_dict(sd: SupportDesign) -> dict:
    return dataclasses.asdict(sd)


# --------------------------------------------------------------- mesh helpers (mm)
def _to_manifold(tm):
    import manifold3d as mf
    m = tm.copy()
    m.merge_vertices()
    M = mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                            tri_verts=np.asarray(m.faces, np.uint32)))
    if M.status() != mf.Error.NoError or M.is_empty():
        import cadio
        M = cadio.to_manifold(cadio.clean(m))
    return M


def _to_trimesh(M):
    """A clean closed mesh: manifold3d keeps zero-area triangle pairs where Boolean faces met edge-on
    (coincident vertices it holds apart); merged as an STL they would be open flaps, so they go."""
    import trimesh
    g = M.to_mesh()
    t = trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts), process=False)
    _weld(t)
    t.update_faces(t.nondegenerate_faces(height=1e-7))
    # back-to-back pairs (the same three vertices, opposite ways round): they enclose nothing
    from trimesh.grouping import group_rows
    pairs = group_rows(np.sort(t.faces, axis=1), require_count=2)
    if len(pairs):
        keep = np.ones(len(t.faces), bool)
        keep[np.asarray(pairs).ravel()] = False
        t.update_faces(keep)
    t.remove_unreferenced_vertices()
    t.merge_vertices()
    # flat or inside-out closed specks left by the weld (faces folded onto each other)
    comps = t.split(only_watertight=False)
    if len(comps) > 1:
        real = [c for c in comps if c.volume > 1e-3]           # mm3; inside-out or flat specks go
        if real and len(real) < len(comps):
            t = trimesh.util.concatenate(real)
            t.merge_vertices()
    return t


def _bad_edges(t):
    from collections import Counter
    c = Counter(map(tuple, t.edges_sorted))
    return [e for e, n in c.items() if n != 2]


def _closed(M, r=0.05, tries=4):
    """M as a closed solid in an STL: where two of its pieces only touch along an edge (a pinch that
    merges into an edge with four faces), a capsule of radius r along that edge joins them."""
    import manifold3d as mf
    for _ in range(tries):
        t = _to_trimesh(M)
        bad = _bad_edges(t)
        if not bad:
            return M, 0
        caps = [mf.Manifold.batch_hull([mf.Manifold.sphere(r, 12).translate(list(map(float, t.vertices[a]))),
                                        mf.Manifold.sphere(r, 12).translate(list(map(float, t.vertices[b])))])
                for a, b in bad]
        M = _clean(mf.Manifold.batch_boolean([M] + caps, mf.OpType.Add))
    return M, len(_bad_edges(_to_trimesh(M)))


def _weld(t, tol=WELD_MM):
    """Vertices closer than tol become one (clusters by distance, not a grid): Boolean slivers finer
    than an STL file can hold collapse here, the same way every time, instead of in the file."""
    from scipy.spatial import cKDTree
    t.merge_vertices()
    pairs = np.array(list(cKDTree(t.vertices).query_pairs(tol)))
    if len(pairs) == 0:
        return t
    parent = np.arange(len(t.vertices))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, j in pairs:
        a, b = root(i), root(j)
        if a != b:
            parent[max(a, b)] = min(a, b)
    rep = np.array([root(i) for i in range(len(parent))])
    F = rep[t.faces]
    ok = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    t.faces = F[ok]
    t.remove_unreferenced_vertices()
    return t


def _clean(M):
    """M without its zero-area triangle pairs; M itself where dropping them leaves two pieces touching
    along an edge (not a manifold): the export then shows it (fit_closed_solid)."""
    if M.is_empty():
        return M
    try:
        return _to_manifold(_to_trimesh(M))
    except ValueError:
        return M


def _box(x0, x1, y0, y1, z0, z1):
    import manifold3d as mf
    return mf.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def _cyl_y(x, z, r, y0, y1, n=128):
    """Cylinder about the line (x, ., z) from y0 to y1."""
    import manifold3d as mf
    return mf.Manifold.cylinder(y1 - y0, r, r, n).rotate([-90.0, 0.0, 0.0]).translate([x, y0, z])


def _proj(M):
    """Shadow of M on the x-y plane, as a clean CrossSection."""
    import manifold3d as mf
    return mf.CrossSection(M.project().to_polygons(), mf.FillRule.Positive)


def _yz_section(M, x):
    """(y, z) polygons of M cut at x (shapely)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    P = M.warp_batch(lambda V: np.c_[V[:, 1], V[:, 2], V[:, 0]]).slice(x)   # cyclic: keeps orientation
    polys = [Polygon(c) for c in P.to_polygons() if len(c) >= 3]
    return unary_union([p.buffer(0) for p in polys]) if polys else None


def _xz_polys(M, y):
    """Contours of M cut at y, as (x, z) arrays (outer anticlockwise, holes clockwise)."""
    P = M.warp_batch(lambda V: np.c_[V[:, 2], V[:, 0], V[:, 1]]).slice(y)   # (z, x) in the plane
    return [np.c_[c[:, 1], c[:, 0]][::-1] for c in P.to_polygons() if len(c) >= 3]   # (x, z); the swap mirrors


def section_props(polys):
    """Area, centroid height and second moment about the horizontal centroidal axis (bending under a
    vertical load), and the farthest fibre from it, of (x, z) contours."""
    A = Sz = Izz = 0.0
    zs = []
    for c in polys:
        x, z = c[:, 0], c[:, 1]
        x1, z1 = np.roll(x, -1), np.roll(z, -1)
        cr = x * z1 - x1 * z
        A += cr.sum() / 2
        Sz += ((z + z1) * cr).sum() / 6
        Izz += ((z * z + z * z1 + z1 * z1) * cr).sum() / 12
        zs.append(z)
    if abs(A) < 1e-9:
        return {"A": 0.0, "zc": 0.0, "I": 0.0, "c": 0.0}
    zc = Sz / A
    I = abs(Izz - A * zc * zc)
    zall = np.concatenate(zs)
    return {"A": abs(A), "zc": zc, "I": I, "c": float(np.abs(zall - zc).max())}


def superellipse(c, t, p, n=N_SECTION):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    co, si = np.cos(th), np.sin(th)
    return (c / 2 * np.sign(co) * np.abs(co) ** (2 / p), t / 2 * np.sign(si) * np.abs(si) ** (2 / p))


def smoothstep(s):
    return 3 * s * s - 2 * s ** 3


def stadium(c, t, n=N_SECTION):
    """A slab c long (x) and t thick (z) with half-round ends, centred on 0: flat top and bottom."""
    r = min(t / 2, c / 2)
    L = c - 2 * r
    per = 2 * L + 2 * math.pi * r
    s_ = np.linspace(0, per, n, endpoint=False)
    xs, zs = np.empty(n), np.empty(n)
    for i, v in enumerate(s_):
        if v < math.pi * r / 2:                                # right end, lower quarter -> top
            a = v / r; xs[i], zs[i] = L / 2 + r * math.cos(a), r * math.sin(a)
        elif v < math.pi * r / 2 + L:                          # top, right -> left
            xs[i], zs[i] = L / 2 - (v - math.pi * r / 2), r
        elif v < 3 * math.pi * r / 2 + L:                      # left end
            a = math.pi / 2 + (v - math.pi * r / 2 - L) / r; xs[i], zs[i] = -L / 2 + r * math.cos(a), r * math.sin(a)
        elif v < 3 * math.pi * r / 2 + 2 * L:                  # bottom, left -> right
            xs[i], zs[i] = -L / 2 + (v - 3 * math.pi * r / 2 - L), -r
        else:                                                  # right end, lower quarter
            a = 3 * math.pi / 2 + (v - 3 * math.pi * r / 2 - 2 * L) / r; xs[i], zs[i] = L / 2 + r * math.cos(a), r * math.sin(a)
    return xs, zs * (t / 2) / r if r > 0 else zs


def loft_sections(stations):
    """Closed solid through sections [(y, (n, 2) array of (x, z), anticlockwise seen from +y)]."""
    import trimesh
    rings = [np.c_[P[:, 0], np.full(len(P), y), P[:, 1]] for y, P in stations]
    n, N = len(rings[0]), len(rings)
    V = np.vstack(rings + [np.mean(rings[0], 0)[None], np.mean(rings[-1], 0)[None]])
    F = []
    for i in range(N - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            c_, d = (i + 1) * n + j, (i + 1) * n + (j + 1) % n
            F += [(a, b, d), (a, d, c_)]
    c0, c1 = N * n, N * n + 1
    for j in range(n):
        F.append((c0, (j + 1) % n, j))
        F.append((c1, (N - 1) * n + j, (N - 1) * n + (j + 1) % n))
    m = trimesh.Trimesh(V, np.array(F), process=False)
    if m.volume < 0:
        m.invert()
    return _to_manifold(m)


def loft(stations):
    """Closed solid through superellipse sections: stations = [(y, xc, zc, chord, thick, p), ...]."""
    import trimesh
    n = N_SECTION
    rings = []
    for y, xc, zc, c, t, p in stations:
        x, z = superellipse(c, t, p, n)
        rings.append(np.c_[xc + x, np.full(n, y), zc + z])
    N = len(rings)
    V = np.vstack(rings + [np.mean(rings[0], 0)[None], np.mean(rings[-1], 0)[None]])
    F = []
    for i in range(N - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            c_, d = (i + 1) * n + j, (i + 1) * n + (j + 1) % n
            F += [(a, b, d), (a, d, c_)]
    c0, c1 = N * n, N * n + 1
    for j in range(n):
        F.append((c0, (j + 1) % n, j))
        F.append((c1, (N - 1) * n + j, (N - 1) * n + (j + 1) % n))
    m = trimesh.Trimesh(V, np.array(F), process=False)
    if m.volume < 0:
        m.invert()
    return _to_manifold(m)


# --------------------------------------------------------------- the saddle
GRID_MM = 0.2                       # the saddle's column grid


def _columns(body_tm, xs, ys):
    """Per column (x, y): the underside zb and the top zt of the body's lowest interval (nan: no body)."""
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    O = np.c_[X.ravel(), Y.ravel(), np.full(X.size, -5.0)]
    D = np.tile([0.0, 0.0, 1.0], (len(O), 1))
    loc, ri, _ = body_tm.ray.intersects_location(O, D, multiple_hits=True)
    zb = np.full(len(O), np.nan); zt = np.full(len(O), np.nan)
    order = np.lexsort((loc[:, 2], ri))
    loc, ri = loc[order], ri[order]
    starts = np.r_[0, np.flatnonzero(np.diff(ri)) + 1]
    for k, s0 in enumerate(starts):
        s1 = starts[k + 1] if k + 1 < len(starts) else len(ri)
        z = np.unique(np.round(loc[s0:s1, 2], 5))
        if len(z) >= 2:
            zb[ri[s0]], zt[ri[s0]] = z[0], z[1]
    return zb.reshape(X.shape), zt.reshape(X.shape)


def _disk(rad_cells):
    n = int(math.ceil(rad_cells))
    i, j = np.mgrid[-n:n + 1, -n:n + 1]
    return (i * i + j * j) <= rad_cells * rad_cells + 1e-9, np.hypot(i, j)


def slot_ceiling(zb, zt, xs, xa, chord, h, g=GRID_MM, r=bsm.TOOL_R_MM):
    """The slot's ceiling over each column (the saddle is the body below it), on the grid (x, y >= 0):
      1. h over the underside across the chord;
      2. widened by h across steps in the floor (a channel's wall, a sidepod's underside), so the layers
         over the floor's levels join through the step instead of touching along its edge;
      3. whole columns where less than FOAM_WALL_MM of foam would be left over it;
      4. what the ball (radius r) can mill from below: the grey-scale opening of that ceiling by the
         ball (the largest ceiling made of the tops of balls that fit under it);
      5. no feather: less than EDGE_STEP_MM over the underside is no saddle.
    Outside the body the ceiling is free (air), below it means no saddle."""
    from scipy import ndimage
    body = np.isfinite(zb)
    # both halves (the centre plane is not a wall)
    full = lambda A: np.concatenate([A[:, :0:-1], A], axis=1)
    half = lambda A: A[:, A.shape[1] // 2:]
    ZB, ZT, BODY = full(zb), full(zt), full(body)
    inband = (np.abs(xs - xa) <= chord / 2)[:, None] & BODY
    t0 = np.where(inband, ZB + h, -1e3)
    fp, _ = _disk(h / g)
    t1 = np.where(inband, np.maximum(ndimage.grey_dilation(t0, footprint=fp), t0), -1e3)
    short = inband & (ZT - t1 < FOAM_WALL_MM)
    # a column printed whole is open to the ball (no foam left in it to spare); outside the band the body
    # is foam the ball may not enter (its ceiling under the underside); outside the body, air
    t2 = np.where(BODY, np.where(inband, np.where(short, 1e3, t1), ZB - 1.0), 1e3)
    fpr, d = _disk(r / g)
    cap = np.where(fpr, np.sqrt(np.maximum(r * r - (d * g) ** 2, 0.0)) - r, 0.0)
    for _ in range(12):
        t3 = np.minimum(ndimage.grey_opening(t2, structure=cap, footprint=fpr), t2)
        # where the ball cannot reach far enough to take the whole column, the foam it leaves must be
        # FOAM_WALL_MM thick: the ceiling comes down to leave that (or there is no saddle in the column)
        left = np.where(BODY, ZT - t3, -1.0)
        thin = BODY & (t3 > ZB) & (left > 1e-3) & (left < FOAM_WALL_MM - 1e-3)
        if not thin.any():
            break
        t2 = np.where(thin, np.where(ZT - FOAM_WALL_MM - ZB >= EDGE_STEP_MM, ZT - FOAM_WALL_MM, ZB - 1.0), t2)
    t3 = np.where(BODY & (t3 - ZB < EDGE_STEP_MM), ZB - 1.0, t3)
    short = BODY & (t3 >= ZT)
    return half(t3), half(short)


def heightfield_solid(xs, ys, Z, zbot):
    """Closed solid over the grid: from zbot up to Z (x, y) (manifold, mm)."""
    import trimesh
    nx, ny = Z.shape
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    top = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
    bot = np.c_[X.ravel(), Y.ravel(), np.full(X.size, zbot)]
    V = np.vstack([top, bot])
    idx = np.arange(nx * ny).reshape(nx, ny)
    F = []
    a, b, c, d = idx[:-1, :-1].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel(), idx[:-1, 1:].ravel()
    F += [np.c_[a, b, c], np.c_[a, c, d]]                               # top, up
    o = nx * ny
    F += [np.c_[a + o, c + o, b + o], np.c_[a + o, d + o, c + o]]       # bottom, down
    ring = np.r_[idx[:, 0], idx[-1, 1:], idx[-2::-1, -1], idx[0, -2:0:-1]]
    for k in range(len(ring)):
        p, q = ring[k], ring[(k + 1) % len(ring)]
        F += [np.array([[p, p + o, q]]), np.array([[q, p + o, q + o]])]
    m = trimesh.Trimesh(V, np.vstack(F), process=False)
    if m.volume < 0:
        m.invert()
    return _to_manifold(m)


def saddle(B, B_tm, xa, chord, h):
    """The printed part inside the body (slot_ceiling): the body below the ceiling. B: the body near the
    axle (manifold, mm), B_tm the same as a trimesh. Returns (saddle, report)."""
    import manifold3d as mf
    g = GRID_MM
    bb = B.bounding_box()
    xs = np.arange(xa - chord / 2 - 2.0, xa + chord / 2 + 2.0 + g / 2, g)
    ys = np.arange(0.0, bb[4] + 1.0 + g / 2, g)
    zb, zt = _columns(B_tm, xs, ys)
    Z, short = slot_ceiling(zb, zt, xs, xa, chord, h)
    zbot = bb[2] - 2.0
    Zc = np.clip(np.where(np.isfinite(Z), Z, zbot - 1.0), zbot - 1.0, bb[5] + 2.0)
    Zc = np.maximum(Zc, zbot - 1.0)
    # the solid is built a little past the centre plane and the band, so none of its sides lies on a face
    ys2 = np.r_[-0.5, ys]
    Zc = np.c_[Zc[:, :1], Zc]
    hf = heightfield_solid(xs, ys2, np.maximum(Zc, zbot + 0.01), zbot - 0.5)
    sad = B ^ hf
    pcs = sorted(sad.decompose(), key=lambda q: -q.volume())
    # one piece: a corner the ball cannot reach from the main slot is left as foam (it is the body's own
    # edge, under its 3 mm), never printed loose
    sad = pcs[0] if pcs else mf.Manifold()
    rep = {"short_columns": int(short.sum()), "ceiling_max_z_mm": float(np.nanmax(np.where(Z < 500, Z, np.nan))),
           "saddle_dropped_mm3": round(float(sum(abs(q.volume()) for q in pcs[1:])), 4),
           "grid_xs": xs, "grid_ys": ys}
    return _clean(sad), rep


# --------------------------------------------------------------- one axle
def build_axle(sd: SupportDesign, body_mm, x_axle, z_axle, R, y_inner, wheel_width, hub_mm,
               tag="front", t_mm=None, h_mm=None, chord_mm=None, disc_t_min=None):
    """Right half of one axle's support (manifold, mm), its hubcap, the foam its slot removes, and
    every measurement. body_mm: the car's body half (manifold, mm). t_mm / h_mm / chord_mm: the arm
    thickness, saddle depth and chord actually used (sizing), the design's when None."""
    t0 = max(sd.t_mm if t_mm is None else t_mm, bsm.PRINT_MIN_MM)
    h0 = max(sd.saddle_h_mm if h_mm is None else h_mm, bsm.PRINT_MIN_MM)
    chord = sd.chord_mm if chord_mm is None else chord_mm
    st = {"tag": tag, "t_mm": t0, "saddle_h_mm": h0, "chord_mm": chord}
    y_out = y_inner + wheel_width
    y_disc = y_inner + sd.disc_recess_mm
    y_bear = y_inner + 0.5 * (hub_mm[0] + hub_mm[1])
    y_tip = y_out - (bsm.BeamSupport().hubcap_t_mm if sd.hubcap else 0.0)

    # the body near this axle
    half = R + 2.0
    bb = body_mm.bounding_box()
    B = body_mm ^ _box(x_axle - half, x_axle + half, -0.01, bb[4] + 1.0, bb[2] - 1.0, bb[5] + 1.0)
    sec = _yz_section(B, x_axle)
    if sec is None or sec.is_empty:
        raise ValueError(f"support_engine: no body at the {tag} axle (x {x_axle:.1f})")
    y_side = float(sec.bounds[2])
    z_lowest = float(B.bounding_box()[2])
    st["y_body_side_mm"] = y_side

    # saddle: narrowed until it lies inside the wheels' cylinder (T7.12.1) with no foam sliver left
    # its chord: the arm's, but at least the ball's width and 2 mm more, and enough for the foam to bear
    # the root moment (6 M / (chord L^2) <= FOAM_BEARING_MPA)
    M_root = bsm.LOAD_RADIAL_N * (y_bear - y_side) + bsm.LOAD_AXIAL_N * R
    sad_chord = max(chord, 2 * bsm.TOOL_R_MM + 2.0, 1.02 * 6 * M_root / (FOAM_BEARING_MPA * max(y_side, 1.0) ** 2))
    cyl = _cyl_y(x_axle, z_axle, R - 0.1, -0.01, y_out + 1.0)
    B_tm = _to_trimesh(B)
    for _ in range(8):
        sad, srep = saddle(B, B_tm, x_axle, sad_chord, h0)
        out_vol = (sad - cyl).volume()
        if out_vol < 1e-3:
            break
        sad_chord *= 0.92
    st["chord_used_mm"] = sad_chord
    chord = min(chord, sad_chord)
    st.update(srep)
    st["saddle_outside_cylinder_mm3"] = round(out_vol, 4)

    # the plate (the example's form, user 2026-11-23): its underside continues the body's underside, level,
    # from the body's side out to the disc; a slab with rounded leading and trailing edges
    # It starts where the floor is still flat, before the body's lower edge rounds up (the plate runs on
    # under that edge), and its bottom follows the floor's own line along x there, so the underside has no
    # step anywhere across the chord.
    ys_r = np.arange(max(y_side - ROOT_SEARCH_MM, 0.5), y_side - 0.3, 0.1)
    zr = _columns(B_tm, np.array([x_axle]), ys_r)[0][0]
    good = np.isfinite(zr)
    y_root = y_side - ROOT_IN_MM
    if good.sum() > 3:
        yy, zz = ys_r[good], zr[good]
        flat = np.abs(np.gradient(zz, yy)) <= ROOT_SLOPE
        # the outermost run of flat floor at least 1 mm wide; its outer end is the root
        runs, start = [], None
        for i, fl in enumerate(np.r_[flat, False]):
            if fl and start is None:
                start = i
            elif not fl and start is not None:
                runs.append((start, i - 1)); start = None
        runs = [(a, b) for a, b in runs if yy[b] - yy[a] >= 1.0]
        if runs:
            a, b = runs[-1]
            slope_ab = np.abs(np.gradient(zz, yy))[a:b + 1]
            level = np.flatnonzero(slope_ab <= ROOT_LEVEL)   # where it is truly level, if anywhere
            y_root = float(yy[a + level[-1]] if len(level) else yy[b])
    xs_r = np.linspace(x_axle - chord / 2 - sd.fillet_mm - 1.0, x_axle + chord / 2 + sd.fillet_mm + 1.0, 41)
    zline = _columns(B_tm, xs_r, np.array([y_root]))[0][:, 0]
    if not np.isfinite(zline).any():
        zline = np.full_like(xs_r, z_lowest)
    zline = np.where(np.isfinite(zline), zline, np.nanmin(np.where(np.isfinite(zline), zline, np.nan)))
    zline_in = _columns(B_tm, xs_r, np.array([y_root - 0.3]))[0][:, 0]
    sl = np.where(np.isfinite(zline_in), (zline - zline_in) / 0.3, 0.0)
    sl = np.clip(sl, -3.0, 3.0)
    zp_of = lambda x: np.interp(x, xs_r, zline)
    slope_of = lambda x: np.interp(x, xs_r, sl)
    ease = min(EASE_MM, max(y_disc - 1.5 - y_root, 0.5))     # level before it reaches the disc

    def bottom_rise(x, y):
        """The plate's underside leaves the floor at its own slope and eases to level over `ease` mm."""
        u = np.clip(y - y_root, 0.0, ease)
        return slope_of(x) * (u - u * u / (2 * ease))
    z_p = float(zp_of(x_axle))                               # the underside where the plate starts, at the axle
    z_mid = z_p + t0 / 2
    st["plate_root_y_mm"] = y_root
    st["plate_bottom_z_mm"] = z_p
    # the disc: carries the stub's moment from the boss to where the plate meets it, bending as a strip as
    # wide as the plate's end over the gap between the boss and the plate (the plate lies below the axle)
    M_disc = bsm.LOAD_RADIAL_N * (y_bear - y_disc) + bsm.LOAD_AXIAL_N * R
    c_end = chord * sd.taper
    w_disc = c_end + 2 * sd.fillet_mm
    root_d = bsm.sized_root_d_mm(bsm.BeamSupport(), y_disc, y_bear, R)
    lever = max(abs(z_axle - z_mid) - (t0 / 2 + sd.fillet_mm) - root_d / 2, 0.3)
    reach = y_bear - y_disc
    t_str = math.sqrt(6 * M_disc / (w_disc * ALLOW_MPA))                                  # stress
    t_rot = (12 * M_disc * lever * reach / (E_MPA * w_disc * DISC_SAG_SHARE_MM)) ** (1 / 3)   # rotation
    disc_t = max(bsm.PRINT_MIN_MM, 1.01 * t_str, 1.01 * t_rot, disc_t_min or 0.0)
    I_d = w_disc * disc_t ** 3 / 12
    y_d0 = y_disc - disc_t                                   # the disc's inner face: where the plate ends
    st.update(disc_t_mm=disc_t, disc_stress_mpa=M_disc * (disc_t / 2) / I_d, y_disc_inner_mm=y_d0,
              disc_lever_mm=lever, disc_sag_mm=M_disc * lever / (E_MPA * I_d) * reach)
    st["arm_span_mm"] = y_d0 - y_side
    ys = np.unique(np.r_[np.linspace(y_root, y_d0, 24),
                        y_d0 - sd.fillet_mm * (1 - np.cos(np.linspace(0, np.pi / 2, 16)))])
    ys = ys[(ys >= y_root) & (ys <= y_d0)]
    stations = []
    span = max(y_d0 - y_side, 1e-6)
    for y in ys:
        s_ = float(np.clip((y - y_side) / span, 0.0, 1.0))
        c = chord * (1 + (sd.taper - 1) * (3 * s_ * s_ - 2 * s_ ** 3))
        sdist = y_d0 - y
        f = sd.fillet_mm - math.sqrt(max(0.0, sd.fillet_mm ** 2 - (sd.fillet_mm - sdist) ** 2)) if sdist < sd.fillet_mm else 0.0
        for _ in range(20):                                  # the transition stays on the disc
            x_, z_ = stadium(c + 2 * f, t0 + 2 * f)
            rmax = float(np.hypot(x_, z_mid - z_axle + z_).max())
            if rmax <= sd.disc_r_mm - 0.3 or f <= 0:
                break
            f = max(0.0, f - (rmax - sd.disc_r_mm + 0.3))
        x_, z_ = stadium(c + 2 * f, t0 + 2 * f)
        # flush at the root, it untwists to level over TWIST_MM outward (no angle of attack across the gap)
        w_t = 1.0 - smoothstep(np.clip((y - y_root) / TWIST_MM, 0.0, 1.0))
        follow = (zp_of(x_axle + x_) - z_p + bottom_rise(x_axle + x_, y)) * w_t \
            + (1.0 - w_t) * bottom_rise(x_axle, y)
        stations.append((float(y), np.c_[x_axle + x_, z_mid + z_ + follow]))
    arm = loft_sections(stations)
    # inside the body the saddle is the support: the plate is what lies outside it. Its faces on the body's
    # surface are the body's own triangles, as are the saddle's, so the two join exactly.
    Bbig = body_mm ^ _box(x_axle - half - 3, x_axle + half + 3, -0.01, bb[4] + 1.0, bb[2] - 1.0, bb[5] + 1.0)
    arm = arm - Bbig
    pcs = sorted(arm.decompose(), key=lambda q: -q.volume())
    st["arm_dropped_mm3"] = round(float(sum(abs(q.volume()) for q in pcs[1:])), 4)   # specks where the plate grazes the body
    arm = _clean(pcs[0])
    # disc + axle (beam_support's)
    bs = bsm.BeamSupport(disc_r_mm=sd.disc_r_mm, disc_recess_mm=sd.disc_recess_mm, hubcap=sd.hubcap)
    line = bsm.stub_outline(bs, y_disc, y_bear, y_tip, root_d)
    prof = [(0.0, y_d0 - 0.05), (sd.disc_r_mm, y_d0 - 0.05), (sd.disc_r_mm, y_disc)] + line + [(0.0, y_tip)]
    stub = _revolve(prof, x_axle, z_axle)
    st.update(bsm.structure(bs, line, y_bear, y_disc, R), root_d_mm=root_d)
    st["stub_stress_mpa"] = st.pop("stress_mpa")
    st["stub_sag_mm"] = st.pop("sag_mm")
    part = sad + arm + stub
    # rules, enforced: the cylinder, the claw band, the track
    y_claw = y_inner - LIP_MM - 0.1
    keep = (_cyl_y(x_axle, z_axle, R - 0.1, -0.01, y_claw)
            + _cyl_y(x_axle, z_axle, R - LIP_MM - 0.15, y_claw - 0.01, y_out + 1.0))
    part = part ^ keep
    part = part ^ _box(x_axle - half - 3, x_axle + half + 3, 0.0, y_out + 2.0, TRACK_MIN_MM + 0.1, bb[5] + 2.0)
    pieces = sorted(part.decompose(), key=lambda q: -q.volume())
    big = [q for q in pieces if q.volume() > SPECK_MM3]
    st["specks_mm3"] = round(float(sum(abs(q.volume()) for q in pieces if q.volume() <= SPECK_MM3)), 4)
    st["pieces"] = len(big)
    st["loose_mm3"] = round(float(sum(q.volume() for q in big[1:])), 4)
    part = _clean(big[0])                                    # a loose piece is refused below (fit_one_piece)
    part, st["pinch_edges_left"] = _closed(part)
    cap = None
    if sd.hubcap:
        hub_r, hub_len = 2.5, 2.0
        cap = _revolve([(0.0, y_tip), (bsm.STUB_D_MM / 2, y_tip), (bsm.STUB_D_MM / 2, y_tip - hub_len),
                        (hub_r, y_tip - hub_len), (hub_r, y_tip), (bs.hubcap_r_mm, y_tip),
                        (bs.hubcap_r_mm, y_out), (0.0, y_out)], x_axle, z_axle)
    slot, _ = _closed(_clean(part ^ Bbig))                   # the foam the slot removes
    st["slot_mm3"] = slot.volume()
    st.update(_structure(part, x_axle, y_side, y_d0, y_bear, R, st))
    return {"support": part, "hubcap": cap, "saddle": sad, "arm": arm, "slot": slot, "body_local": Bbig,
            "_struct": st, "geom": dict(x_axle=x_axle, z_axle=z_axle, R=R, y_inner=y_inner, y_out=y_out,
                                         y_side=y_side, y_d0=y_d0, y_bear=y_bear, chord=chord, y_root=y_root,
                                         y_flare=y_d0 - sd.fillet_mm)}


def _revolve(profile_ry, x, z):
    """Solid of revolution about the axle line (x, ., z) from a (radius, y) outline (manifold, mm)."""
    return _to_manifold(_mm(bsm._revolve_y(profile_ry, x, z, sections=128)))


def _mm(tm_m):
    m = tm_m.copy()
    m.apply_scale(1e3)
    return m


def _structure(part, x_axle, y_side, y_d0, y_bear, R, st):
    """The arm and the saddle measured on the part's own sections: stress along them and the sag
    at the bearing (the body taken as rigid at its side; the saddle's own bending added)."""
    out = {}
    M = lambda y: bsm.LOAD_RADIAL_N * (y_bear - y) + bsm.LOAD_AXIAL_N * R
    # arm: from the body's side to the disc
    ya = np.linspace(y_side, y_d0 - 0.05, 40) if y_d0 - 0.05 > y_side else np.array([y_side])
    sig, kap = [], []
    for y in ya:
        sp = section_props(_xz_polys(part, y))
        if sp["I"] <= 0:
            sig.append(np.inf); kap.append(np.inf); continue
        sig.append(M(y) * sp["c"] / sp["I"]); kap.append(M(y) / (E_MPA * sp["I"]))
    sig, kap = np.array(sig), np.array(kap)
    out["arm_stress_mpa"] = float(sig.max())
    out["arm_stress_at_y_mm"] = float(ya[int(sig.argmax())])
    if len(ya) > 1:
        th = np.concatenate([[0.0], np.cumsum(0.5 * (kap[1:] + kap[:-1]) * np.diff(ya))])
        dl = float(np.sum(0.5 * (th[1:] + th[:-1]) * np.diff(ya)))
        th_end = float(th[-1])
    else:
        dl = th_end = 0.0
    # saddle: between the centre plane and the body's side (conservative: the foam's own share ignored)
    yb = np.linspace(0.3, max(y_side - 0.3, 0.31), 16)
    ss, Is = [], []
    for y in yb:
        sp = section_props(_xz_polys(part, y))
        ss.append(M(y) * sp["c"] / sp["I"] if sp["I"] > 0 else np.inf)
        Is.append(sp["I"])
    out["saddle_stress_mpa"] = float(np.max(ss))
    # the saddle's rotation at the body's side, root moment over half its length (glue ignored: conservative)
    Imean = float(np.mean([i for i in Is if i > 0])) if any(i > 0 for i in Is) else 1e-9
    rot_saddle = M(y_side) * y_side / (E_MPA * Imean)
    out["arm_sag_mm"] = dl + th_end * (y_bear - y_d0)
    out["saddle_rotation_sag_mm"] = rot_saddle * (y_bear - y_side)
    # the saddle is glued along the floor into a body ~30x stiffer than it: the root is taken as rigid
    # (its free rotation, saddle_rotation_sag_mm, is reported: the bound if the glue let go)
    out["sag_mm"] = out["arm_sag_mm"] + st["stub_sag_mm"] + st.get("disc_sag_mm", 0.0)
    # foam bearing under the saddle: the root moment as a linear pressure over its length
    out["foam_bearing_mpa"] = 6 * M(y_side) / (st["chord_used_mm"] * max(y_side, 1.0) ** 2)
    return out


def build_axle_sized(sd, body_mm, x_axle, z_axle, R, y_inner, wheel_width, hub_mm, tag="front"):
    """build_axle, with the arm's thickness and the saddle's depth grown until the loads pass."""
    t, h = sd.t_mm, sd.saddle_h_mm
    for it in range(6):
        r = build_axle(sd, body_mm, x_axle, z_axle, R, y_inner, wheel_width, hub_mm, tag, t_mm=t, h_mm=h)
        s = r["_struct"]
        # thickness factors that would just pass: stress ~ 1/t^2, sag ~ 1/t^3
        budget = bsm.SAG_MAX_MM - s["stub_sag_mm"] - s.get("disc_sag_mm", 0.0) - 0.005
        f_t = max(math.sqrt(max(s["arm_stress_mpa"], 0.0) / ALLOW_MPA),
                  (max(s["arm_sag_mm"], 0.0) / budget) ** (1 / 3) if budget > 0 else np.inf)
        f_h = math.sqrt(max(s["saddle_stress_mpa"], 0.0) / ALLOW_MPA)
        s["sizing_iterations"] = it
        if not (np.isfinite(f_t) and np.isfinite(f_h)) or (f_t <= 1.0 and f_h <= 1.0):
            break
        if f_t > 1.0:
            t = s["t_mm"] * max(f_t, 1.05)
        if f_h > 1.0:
            h = s["saddle_h_mm"] * max(f_h, 1.05)
        if t > 8.0 or h > 10.0:
            break
    return r


# --------------------------------------------------------------- measured
def _intersect(A, B):
    """Intersection of two sorted lists of (z0, z1) intervals."""
    out, i, j = [], 0, 0
    while i < len(A) and j < len(B):
        lo, hi = max(A[i][0], B[j][0]), min(A[i][1], B[j][1])
        if hi > lo:
            out.append((lo, hi))
        if A[i][1] < B[j][1]:
            i += 1
        else:
            j += 1
    return out


def column_check(body_tm, part_tm, xs, ys):
    """Column by column (vertical rays at the slot's own grid nodes, where its ceiling is defined; between
    nodes a vertical step is drawn as a 0.2 mm slope): the slot is where the part is inside the body, taken
    as the overlap of the two solids' own intervals along each ray (no Boolean between them, whose seams
    can lose a sliver: L0035, 2026-11-22). Every column of the slot must start at the body's underside
    (cut from below), and the foam over it must be FOAM_WALL_MM thick or absent.
    Returns (worst foam over the slot - wall, foam under the slot (mm), columns tested)."""
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    O = np.c_[X.ravel(), Y.ravel(), np.full(X.size, -5.0)]
    D = np.tile([0.0, 0.0, 1.0], (len(O), 1))

    def intervals(m):
        loc, ri, _ = m.ray.intersects_location(O, D, multiple_hits=True)
        res = [[] for _ in range(len(O))]
        for (p, i) in zip(loc[:, 2], ri):
            res[i].append(p)
        out = []
        for zs in res:
            zs = np.unique(np.round(np.sort(zs), 5))
            out.append([(zs[k], zs[k + 1]) for k in range(0, len(zs) - 1, 2)])
        return out
    bi, pi = intervals(body_tm), intervals(part_tm)
    worst_wall, worst_under, n = np.inf, 0.0, 0
    for b, p in zip(bi, pi):
        s = [q for q in _intersect(b, p) if q[1] - q[0] > 1e-3]
        if not b or not s:
            continue
        n += 1
        zb0 = b[0][0]
        s0, s1 = s[0][0], max(q[1] for q in s)
        worst_under = max(worst_under, s0 - zb0)             # foam left under the slot
        for (a0, a1) in b:                                   # foam over the slot, in this body interval
            if a1 > s1 + 1e-3 and a0 <= s1 + 1e-3:
                worst_wall = min(worst_wall, a1 - s1)
    return (worst_wall - FOAM_WALL_MM + 1e-3 if np.isfinite(worst_wall) else 0.0), worst_under, n   # 1 um: round-off


def underside_step(body_tm, part_tm, xs, ys):
    """The car's underside (body and support together: the lowest surface seen from below) along y at
    each x, through the join between body and support. Returns the largest change of its rise between
    neighbouring 0.1 mm samples (mm): a step or a kink where the support meets the body, or none (flush);
    a smooth slope or curve gives a few hundredths."""
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    O = np.c_[X.ravel(), Y.ravel(), np.full(X.size, -5.0)]
    D = np.tile([0.0, 0.0, 1.0], (len(O), 1))

    def first(m):
        z = np.full(len(O), np.inf)
        loc, ri, _ = m.ray.intersects_location(O, D, multiple_hits=True)
        np.minimum.at(z, ri, loc[:, 2])
        return z
    z = np.minimum(first(body_tm), first(part_tm)).reshape(X.shape)
    d = np.diff(z, axis=1)
    dd = np.abs(np.diff(d, axis=1))                           # a step or a kink, not a slope
    ok = np.isfinite(dd)
    return float(dd[ok].max()) if ok.any() else 0.0


def gates(r, tag) -> dict:
    """Margins (+ = passes) measured on the built part (mm, MPa)."""
    g = r["geom"]
    st = r["_struct"]
    part = _to_trimesh(r["support"])
    v = part.vertices
    far = float(np.hypot(v[:, 0] - g["x_axle"], v[:, 2] - g["z_axle"]).max())
    band = v[(v[:, 1] > g["y_inner"] - LIP_MM) & (v[:, 1] < g["y_inner"])]
    claw_r = float(np.hypot(band[:, 0] - g["x_axle"], band[:, 2] - g["z_axle"]).max()) if len(band) else 0.0
    out = {f"T7.12.1_{tag}_support_in_cylinder": g["R"] - far,
           f"T3.7_{tag}_support_clearance": float(v[:, 2].min()) - TRACK_MIN_MM,
           f"T7.13_{tag}_support_clear_of_claw": (g["R"] - LIP_MM) - claw_r,
           f"load_{tag}_arm_stress": ALLOW_MPA - st["arm_stress_mpa"],
           f"load_{tag}_saddle_stress": ALLOW_MPA - st["saddle_stress_mpa"],
           f"load_{tag}_stub_stress": st["allow_mpa"] - st["stub_stress_mpa"],
           f"load_{tag}_disc_stress": ALLOW_MPA - st["disc_stress_mpa"],
           f"load_{tag}_bearing_sag": bsm.SAG_MAX_MM - st["sag_mm"],
           f"load_{tag}_foam_bearing": FOAM_BEARING_MPA - st["foam_bearing_mpa"],
           f"fit_{tag}_one_piece": -st["loose_mm3"] if st["pieces"] > 1 else 0.0,
           f"fit_{tag}_closed_solid": 0.0 if part.is_watertight and len(part.split(only_watertight=False)) == 1 else -1.0,
           f"fit_{tag}_arm_reaches_disc": st["arm_span_mm"] + 1.5,
           f"fit_{tag}_disc_in_rim": bsm.RIM_INNER_R_MM - 0.5 - r["_struct"].get("disc_r_mm", 12.0)}
    if r.get("hubcap") is not None:
        out[f"fit_{tag}_hubcap_in_rim"] = bsm.RIM_INNER_R_MM - 0.5 - bsm.BeamSupport().hubcap_r_mm
        out[f"T3.7_{tag}_hubcap_clearance"] = g["z_axle"] - bsm.BeamSupport().hubcap_r_mm - TRACK_MIN_MM
    gx, gy = st.pop("grid_xs"), st.pop("grid_ys")
    wall, under, n = column_check(_to_trimesh(r["body_local"]), part, gx, gy[gy <= g["y_side"] + 0.5])
    out[f"machining_{tag}_foam_over_slot"] = wall
    # flush: the underside runs on from the body into the plate with no step and no kink (0.1 mm samples
    # across the join, up to where the plate starts its fillet into the disc)
    c = g["chord"]
    step = underside_step(_to_trimesh(r["body_local"]), part, g["x_axle"] + np.array([-0.3, 0.0, 0.3]) * c,
                          np.arange(g["y_root"] - 0.3, max(g["y_root"] + 0.6, min(g["y_side"] + 1.5, g["y_flare"])), 0.1))
    st["underside_step_mm"] = step
    out[f"fit_{tag}_flush_with_the_underside"] = FLUSH_STEP_MM - step
    out[f"machining_{tag}_slot_cut_from_below"] = SLOT_TOL_MM - under
    st["slot_columns_tested"] = n
    return out


def build(sd: SupportDesign, body_half_m, axles, out_dir=None, keep_out_mm=None):
    """Both axles. body_half_m: the body's right half (trimesh, metres). axles: [(tag, x, z, R, y_inner,
    wheel_width, hub_mm)]. keep_out_mm: a solid (manifold, mm) no support may enter (the chamber and its
    wall: the referee measures the body without the slot, so it would not see a saddle in the wall). Returns {"support": trimesh (m, right half, both axles), "hubcaps": {tag: trimesh m},
    "gates", "info": per axle, "net_kg_each": per axle per side (part + hubcap - foam removed),
    "com_mm": per axle}."""
    import trimesh
    body_mm = _to_manifold(_mm(body_half_m))
    parts, caps, gts, info, net, com = [], {}, {}, {}, [], []
    for tag, x, z, R, y_in, w, hub in axles:
        r = build_axle_sized(sd, body_mm, x, z, R, y_in, w, hub, tag)
        r["_struct"]["disc_r_mm"] = sd.disc_r_mm
        gts.update(gates(r, tag))
        if keep_out_mm is not None:                # the chamber and its 3 mm wall: foam the saddle may not take
            v = (r["support"] ^ keep_out_mm).volume()
            gts[f"fit_{tag}_clear_of_chamber_wall"] = -round(float(v), 4) if v > 1e-3 else 0.0
        st = r["_struct"]
        tm = _to_trimesh(r["support"])
        vol = abs(tm.volume) + (r["hubcap"].volume() if r["hubcap"] is not None else 0.0)
        part_g = vol * 1e-3 * sd.material_g_cm3
        foam_g = st["slot_mm3"] * 1e-3 * FOAM_G_CM3
        st.update(part_g_each=part_g, foam_removed_g_each=foam_g, net_g_each=part_g - foam_g)
        net.append((part_g - foam_g) * 1e-3)
        com.append(tuple(float(c) for c in tm.center_mass))
        info[tag] = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in st.items()}
        parts.append(tm)
        if r["hubcap"] is not None:
            caps[tag] = _to_trimesh(r["hubcap"])
        if out_dir is not None:
            from pathlib import Path
            for k in ("saddle", "arm", "slot"):
                q = _to_trimesh(r[k]); q.apply_scale(1e-3)
                q.export(str(Path(out_dir) / f"support_{tag}_{k}.stl"))
    sup = trimesh.util.concatenate(parts)
    sup.apply_scale(1e-3)
    for c in caps.values():
        c.apply_scale(1e-3)
    return {"support": sup, "hubcaps": caps, "gates": gts, "info": info, "net_kg_each": net, "com_mm": com}
