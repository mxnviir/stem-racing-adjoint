"""rear_wing_engine.py -- the searches' rear wing, with the supports it designs itself (user 2026-11-23:
"it must be able to come up with its own support structures for the rear wing too, like attached to top of
canister above the safety zone, or slotted, or even attached to rearpods ... the possibilities should be
endless").

One representation, no modes. The wing is a NACA 4-digit section (camber either way, angle of attack),
swept and given dihedral by shearing it along the span. Under it stand up to N_STRUTS strut pairs (mirrored;
one on the centre line where it sits there), each described only by continuous numbers:

  t_mm        thickness; under the printer's wall the strut is not there
  y_frac      where on the span it meets the wing (0 the centre line, 1 the tip)
  x_frac      where along the chord
  chord_mm    its own chord
  rake_deg    lean in side view (+: the foot further aft than the top)
  splay_deg   lean in front view (+: the foot further outboard)
  slot_mm     the root: <= 0 glued to the body's surface; > 0 set this deep into a slot the ball cuts

Each strut is CAST: from where it meets the wing, along its lean, down to the first body surface it meets,
whatever body the car has. A pair that splays out over a sidepod or a rearpod lands on it; one straight
down over the chamber lands on the chamber's top; a slotted root is a plug the 6.35 mm ball can cut (a
stadium as wide as the ball, its bottom the ball's own round), kept above the T5.5 wall and with 3 mm of
foam round it. A strut that meets no body is leaned back towards the vertical until it does; one that still
does not is reported (info["struts_not_placed"]), never silently dropped; with none placed the wing is not
held and the car is refused.

The wing is put as low as T9.6 (5 mm clear air to the body, the wheels and every other part, except within
5 mm sideways of its own struts' joints, the fillet the rule allows) and T9.7 (seen from the front, over
whatever is ahead of it within its span) let it be, plus the search's own `lift_mm`.

Measured always (gates()): T9.4.1 (wing and struts behind Ref B), T9.4.2 (within 40 mm of Ref B), T9.4.3
(65 mm), T9.5.1 (span >= 50, one piece), T9.5.2 (chord 15-25 along the track), T9.5.3 (2-6 mm thick),
T9.5.4 (height change along the span <= 15), T9.6, T9.7, the struts' print wall, their slots (T5.5 wall,
3 mm of foam), T7.9's wheel zones and the wheels' own clearance, and the car's width (T3.4)."""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field

import numpy as np

import component_contract as cc

N_STRUTS = 2
MARGIN_MM = 0.3                 # kept off every limit
GLUE_MM = 0.3                   # a glued foot runs this far into the body (as drawn: they touch)
BALL_R_MM = 3.175               # the team's cutter
FOAM_WALL_MM = 3.0              # foam left round a slot
WHEEL_CLEAR_MM = 1.0            # a strut stays this far off a wheel
TOP_EMBED_MM = 0.2              # a strut stops this far under the wing's upper surface
N_SPAN = 20
HALF_WIDTH_MAX_MM = 42.5        # T3.4: 85 mm


@dataclass
class Strut:
    t_mm: float = 2.0
    y_frac: float = 0.0
    x_frac: float = 0.5
    chord_mm: float = 10.0
    rake_deg: float = 0.0
    splay_deg: float = 0.0
    slot_mm: float = 0.0


@dataclass
class RearWingDesign:
    chord_mm: float = 15.3          # T9.5.2 minimum + 0.3
    t_mm: float = 2.3               # T9.5.3 minimum + 0.3
    camber: float = 0.0             # NACA camber (fraction of chord): + lifts, - presses down
    aoa_deg: float = 0.0            # nose up (+)
    half_span_mm: float = 26.0      # T9.5.1: >= 25 a side
    x_le_mm: float = 3.5            # leading edge at the root, behind Ref B
    lift_mm: float = 0.0            # above the lowest height T9.6 and T9.7 allow
    sweep_deg: float = 0.0          # leading edge back towards the tip (+)
    dihedral_deg: float = 0.0       # tip up (+)
    struts: tuple = field(default_factory=lambda: (Strut(),))


def from_dict(d: dict) -> RearWingDesign:
    d = dict(d)
    st = tuple(Strut(**s) if isinstance(s, dict) else s for s in d.pop("struts", ({},)))
    return RearWingDesign(**d, struts=st)


def params_dict(d: RearWingDesign) -> dict:
    return dataclasses.asdict(d)


# ------------------------------------------------------------------ sections and solids (mm)
def section(d: RearWingDesign) -> np.ndarray:
    """The wing's section, (x from the LE, z about the chord line), anticlockwise seen from +y."""
    import wings as wg
    tf = d.t_mm / d.chord_mm
    for _ in range(3):                                  # the printable blunt TE adds thickness: scaled to t_mm
        P = wg.naca4(d.chord_mm, tf, abs(d.camber), te_mm=cc.BUILD_WALL_MM)
        th = max(_mid_z(P, x)[1] for x in np.linspace(0.02, 0.98, 49) * d.chord_mm)
        if th <= 0 or abs(th - d.t_mm) < 1e-3:
            break
        tf *= d.t_mm / th
    if d.camber < 0:                                    # pressed down: the same section upside down
        P = (P * np.array([1.0, -1.0]))[::-1]
    a = math.radians(d.aoa_deg)                         # nose up: about the LE
    R = np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])
    return P @ R.T


def _wing(d: RearWingDesign, x_le, z_root):
    """The right half of the wing (manifold, mm), its root just across the centre line."""
    import support_engine as se
    sec = section(d)
    sw, dh = math.tan(math.radians(d.sweep_deg)), math.tan(math.radians(d.dihedral_deg))
    st = [(float(y), np.c_[x_le + sw * max(y, 0.0) + sec[:, 0], z_root + dh * max(y, 0.0) + sec[:, 1]])
          for y in np.linspace(-0.5, d.half_span_mm, N_SPAN)]
    return se.loft_sections(st) ^ se._box(-1e3, 1e3, 0.0, 1e3, -1e3, 1e3)


def _mid_z(sec, x):
    """The section's mid height (between its upper and lower surface) at x from the LE, and its thickness."""
    xs = sec[:, 0]
    lo, hi = xs.min(), xs.max()
    x = float(np.clip(x, lo + 1e-6, hi - 1e-6))
    zs = []
    n = len(sec)
    for i in range(n):
        a, b = sec[i], sec[(i + 1) % n]
        if (a[0] - x) * (b[0] - x) <= 0 and a[0] != b[0]:
            zs.append(a[1] + (x - a[0]) / (b[0] - a[0]) * (b[1] - a[1]))
    if len(zs) < 2:
        return 0.0, 0.0
    return 0.5 * (max(zs) + min(zs)), max(zs) - min(zs)


def _hit(body_tm, o, d):
    """First body surface from o along d (mm), or None."""
    o = np.asarray(o, float)[None]
    d = np.asarray(d, float)[None]
    loc, _, _ = body_tm.ray.intersects_location(o, d / np.linalg.norm(d), multiple_hits=True)
    if not len(loc):
        return None
    k = np.argmin(np.linalg.norm(loc - o, axis=1))
    return loc[k]


def _strut_solid(s: Strut, top, foot, sink_mm):
    """A strut (manifold, mm): its section (NACA 00xx in plan) carried along the line from `top` down to
    `foot`, run on sink_mm past the foot."""
    import front_wing_engine as fwe
    sec = fwe.naca00(s.chord_mm, min(0.4, s.t_mm / s.chord_mm))
    sec = sec - np.array([s.chord_mm / 2.0, 0.0])
    top, foot = np.asarray(top, float), np.asarray(foot, float)
    dz = max(top[2] - foot[2], 1e-6)
    st = []
    for z in np.linspace(foot[2] - sink_mm, top[2], 10):
        c = top + (top[2] - z) / dz * (foot - top)       # on the line from the top to the foot, run on past it
        st.append((float(z), np.c_[c[0] + sec[:, 0], c[1] + sec[:, 1]]))
    return fwe._loft_z(st)


def _plug(foot, length_mm, depth_mm):
    """The slot a ball cuts at `foot`, as the strut's root fills it (manifold, mm): a stadium as wide as the
    ball, length_mm long in x, from depth_mm under the foot up to 2 mm over it, its bottom the ball's round."""
    import manifold3d as mf
    R = BALL_R_MM
    L = max(length_mm - 2 * R, 0.0)
    zc = foot[2] - depth_mm + R
    path = mf.Manifold.cube([max(L, 1e-3), 1e-3, 1e-3]).translate([foot[0] - L / 2, foot[1] - 5e-4, zc - 5e-4])
    swept = path.minkowski_sum(mf.Manifold.sphere(R, 32))
    up = mf.Manifold.extrude(mf.CrossSection.circle(R, 32), foot[2] + 2.0 - zc)
    if L > 0:
        up = up + up.translate([L, 0.0, 0.0])
        up = mf.Manifold.hull(up)
    up = up.translate([foot[0] - L / 2, foot[1], zc])
    return swept + up


# ------------------------------------------------------------------ build
def build(d: RearWingDesign, body_half_m, x_front_mm, W_mm, wheel_rear, clear_of=(), forward_parts=()):
    """The wing and its struts, right halves (trimesh, metres), on this body.
    wheel_rear = (x_axle, y_inner, R, width) of the rear wheel; clear_of: other parts (trimesh, metres) the
    wing keeps T9.6's 5 mm from; forward_parts: what T9.7 looks over. Returns {"wing", "struts" (list),
    "plugs" (list, the slots' foam), "gates", "info"}."""
    import trimesh
    import support_engine as se
    body = body_half_m.copy(); body.apply_scale(1e3)
    others = []
    for m in clear_of:
        q = m.copy(); q.apply_scale(1e3); others.append(q)
    fwd = []
    for m in forward_parts:
        q = m.copy(); q.apply_scale(1e3); fwd.append(q)
    info = {"design": params_dict(d)}
    ref_b = cc.ref_plane_B(x_front_mm, W_mm)
    rear_face = float(body.bounds[1, 0])
    # -- the pose, repaired into T9.4 / T9.5 ------------------------------------------------------------
    hs = float(np.clip(d.half_span_mm, cc.REAR_SPAN_MIN / 2 + MARGIN_MM, HALF_WIDTH_MAX_MM - MARGIN_MM))
    chord = float(np.clip(d.chord_mm, cc.REAR_CHORD_MIN + MARGIN_MM, cc.REAR_CHORD_MAX - MARGIN_MM))
    t = float(np.clip(d.t_mm, cc.WING_THICK_MIN + MARGIN_MM, cc.WING_THICK_MAX - MARGIN_MM))
    room = cc.REAR_OVERHANG_MAX - 2 * MARGIN_MM - chord * math.cos(math.radians(d.aoa_deg))
    sw_lim = math.degrees(math.atan(max(room, 0.0) / hs))
    sweep = float(np.clip(d.sweep_deg, -sw_lim, sw_lim))
    back, fwd_tip = max(0.0, math.tan(math.radians(sweep)) * hs), max(0.0, -math.tan(math.radians(sweep)) * hs)
    x_le = float(np.clip(ref_b + d.x_le_mm, ref_b + MARGIN_MM + fwd_tip, ref_b + MARGIN_MM + room - back))
    dh_lim = math.degrees(math.atan((cc.REAR_HEIGHT_DEVIATION_MAX - MARGIN_MM) / hs))
    dih = float(np.clip(d.dihedral_deg, -dh_lim, dh_lim))
    # T7.9: the wheels' zones run the car's full height (behind the rear wheel, outboard of its inner face):
    # a wing tip swept forward into one is moved aft until it is clear (T9.4.2 then measured as ever)
    import exact_zones as ez
    sw_ = math.tan(math.radians(sweep))
    ys_ = np.linspace(0.0, hs, 60)
    zs_ = np.linspace(0.0, cc.REAR_Z_MAX, 14)
    for _ in range(40):
        Y_, Z_ = np.meshgrid(ys_, zs_, indexing="ij")
        X_ = x_le + sw_ * Y_ - MARGIN_MM
        zv = ez.t79_zones(X_.ravel(), Y_.ravel(), Z_.ravel(), W_mm, x_front_mm)
        if not (zv > -MARGIN_MM).any():
            break
        x_le += float(zv.max()) + MARGIN_MM + 0.05
        info["moved_aft_of_T7.9_mm"] = info.get("moved_aft_of_T7.9_mm", 0.0) + float(zv.max()) + MARGIN_MM + 0.05
    d = dataclasses.replace(d, half_span_mm=hs, chord_mm=chord, t_mm=t, sweep_deg=sweep, dihedral_deg=dih)
    info.update(half_span_mm=hs, chord_mm=chord, t_mm=t, sweep_used_deg=sweep, dihedral_used_deg=dih, x_le_mm=x_le)
    sec = section(d)
    sw, dhk = math.tan(math.radians(sweep)), math.tan(math.radians(dih))
    # -- where the struts meet the wing (y on the span, x along the chord) --------------------------------
    struts = [s for s in d.struts if s.t_mm >= cc.BUILD_WALL_MM]
    info["struts_asked"] = len(d.struts)
    info["struts_thick_enough"] = len(struts)
    plans = []
    for s in struts:
        c = float(np.clip(s.chord_mm, cc.BUILD_WALL_MM * 2, chord * 0.8))
        tt = float(np.clip(s.t_mm, cc.BUILD_WALL_MM, 8.0))
        y = float(np.clip(s.y_frac, 0.0, 1.0)) * (hs - tt / 2 - MARGIN_MM)
        if y < tt / 2 + 0.5:
            y = 0.0                                      # one strut on the centre line
        xf = float(np.clip(s.x_frac, 0.1 + c / 2 / chord, 0.9 - c / 2 / chord)) if c < 0.8 * chord else 0.5
        plans.append(dataclasses.replace(s, chord_mm=c, t_mm=tt, y_frac=y, x_frac=xf))

    def joint_bands():
        return [(p.y_frac - p.t_mm / 2 - cc.CLEAR_AIR, p.y_frac + p.t_mm / 2 + cc.CLEAR_AIR) for p in plans]

    # -- height: T9.6 (5 mm clear, but at the joints) then T9.7, then the search's lift -------------------
    # The clearance search runs on a cloud of points on everything the wing keeps clear of (a KD-tree: the
    # exact distance to a 40,000-face body, 14 heights deep, took 40 s a wing); the height it finds is then
    # checked exactly and raised by any shortfall.
    from scipy.spatial import cKDTree
    cloud = np.vstack([m.sample(int(min(400000, max(20000, m.area * 8)))) for m in [body] + others])
    tree = cKDTree(cloud)
    base = se._to_trimesh(_wing(d, x_le, 0.0))
    pts0, _ = trimesh.sample.sample_surface_even(base, 1500, seed=1)
    keep = np.ones(len(pts0), bool)
    for a_, b_ in joint_bands():
        keep &= ~((pts0[:, 1] >= a_) & (pts0[:, 1] <= b_))
    q0 = pts0[keep] if keep.any() else pts0
    lo0 = float(base.bounds[0, 2])

    def short(zr, exact=False):
        """(T9.6 shortfall, T9.7 shortfall) at root height zr (mm; > 0: short)."""
        q = q0 + np.array([0.0, 0.0, zr])
        if exact:
            gap = min(float(np.concatenate([trimesh.proximity.closest_point(m, q[i:i + 256])[1]
                                            for i in range(0, len(q), 256)]).min()) for m in [body] + others)
        else:
            gap = float(tree.query(q)[0].min()) - 0.15              # the cloud's spacing, conservatively
        gap = min(gap, float(q[:, 2].min()))
        w = base.copy(); w.apply_translation([0.0, 0.0, zr])
        return cc.CLEAR_AIR + MARGIN_MM - gap, _front_view_top(w, fwd) + 0.1 - (lo0 + zr)
    lo, hi = 0.0, cc.REAR_Z_MAX
    if max(short(hi)) > 0:
        z = hi                                           # nowhere it fits: the gates say so
    else:
        for _ in range(16):                              # the lowest root height both allow
            mid = 0.5 * (lo + hi)
            if max(short(mid)) > 0:
                lo = mid
            else:
                hi = mid
        z = hi
        for _ in range(3):
            a_, b_ = short(z, exact=True)
            if max(a_, b_) <= 0:
                break
            z += max(a_, b_) + 0.05
    wing_tm = se._to_trimesh(_wing(d, x_le, z))
    z_low = z
    if d.lift_mm > 0:
        z += d.lift_mm
        wing_tm = se._to_trimesh(_wing(d, x_le, z))
    info.update(z_root_mm=z, z_lowest_mm=z_low)
    # -- struts, cast to the body ------------------------------------------------------------------------
    solids, plugs, placed = [], [], []
    from geometry_contract import CHAMBER_AXIS_Z_MM, MODEL_BLOCK_BORE_DIA_MM
    wall_top = CHAMBER_AXIS_Z_MM + MODEL_BLOCK_BORE_DIA_MM / 2.0 + 3.0     # the T5.5 wall's top
    x_bore_front = rear_face - 52.0
    for i, p in enumerate(plans):
        xm = x_le + sw * p.y_frac + p.x_frac * chord
        zmid, th = _mid_z(sec, p.x_frac * chord)
        top = np.array([xm, p.y_frac, z + dhk * p.y_frac + zmid + th / 2 - TOP_EMBED_MM])
        start = np.array([xm, max(p.y_frac, 0.05), z + dhk * p.y_frac + zmid])
        foot, used = None, None
        for k in np.linspace(1.0, 0.0, 6):               # leaned back towards the vertical if it misses
            rk, sp = math.radians(p.rake_deg * k), math.radians(p.splay_deg * k)
            dirv = np.array([math.tan(rk), math.tan(sp) if p.y_frac > 0 else 0.0, -1.0])
            hit = _hit(body, start, dirv)
            if hit is not None:
                foot, used = hit, (p.rake_deg * k, p.splay_deg * k)
                break
        if foot is None:
            info.setdefault("struts_not_placed", []).append(i)
            continue
        if foot[1] < 0.05 and p.y_frac == 0.0:
            foot = np.array([foot[0], 0.0, foot[2]])
        if p.y_frac > 0 and foot[1] + p.t_mm / 2 > HALF_WIDTH_MAX_MM - MARGIN_MM:
            info.setdefault("struts_not_placed", []).append(i)
            continue
        slot = float(p.slot_mm)
        plug = None
        if slot > 0:
            # the slot: a stadium the ball cuts, above the T5.5 wall where it is over the chamber, 3 mm of
            # foam round it, else shallower, else glued
            over_chamber = abs(foot[1]) < 12.5 + BALL_R_MM and foot[0] + p.chord_mm / 2 + BALL_R_MM > x_bore_front - 3.0
            if over_chamber:
                slot = min(slot, foot[2] - (wall_top + FOAM_WALL_MM + MARGIN_MM))
            while slot > 0.5:
                pm = se._to_trimesh(_plug(foot, max(p.chord_mm, 2 * BALL_R_MM), slot))
                if _foam_round(body, pm) >= FOAM_WALL_MM - 0.05:
                    plug = pm
                    break
                slot -= 0.5
            if plug is None:
                slot = 0.0
                info.setdefault("slots_glued_instead", []).append(i)
        sink = slot if plug is not None else GLUE_MM
        m = _strut_solid(p, top, foot, sink)
        if plug is not None:
            import manifold3d as mf
            m = m + se._to_manifold(plug)
            plugs.append(plug)
        m = m ^ se._box(-1e3, 1e3, 0.0, 1e3, -1e3, 1e3)
        solids.append(se._to_trimesh(m))
        placed.append(dict(index=i, y_mm=round(p.y_frac, 2), foot_mm=[round(float(v), 2) for v in foot],
                           lean_deg=[round(v, 2) for v in used], slot_mm=round(slot if plug is not None else 0.0, 2),
                           t_mm=p.t_mm, chord_mm=p.chord_mm))
    info["struts"] = placed
    info["supported"] = bool(placed)
    gates = measure(d, wing_tm, solids, plugs, body, others, fwd, ref_b, wheel_rear, x_front_mm, W_mm,
                    wall_top, x_bore_front, placed)
    out = {"gates": gates, "info": info}
    for k, v in (("wing", wing_tm),):
        q = v.copy(); q.apply_scale(1e-3); out[k] = q
    out["struts"] = []
    for s in solids:
        q = s.copy(); q.apply_scale(1e-3); out["struts"].append(q)
    out["plugs"] = []
    for s in plugs:
        q = s.copy(); q.apply_scale(1e-3); out["plugs"].append(q)
    return out


def _foam_round(body, plug):
    """The thinnest foam (mm) round a slot, below the body's top: from points on the plug's sides and
    bottom inside the body, how far out (along the plug's normal) the body still holds."""
    pts, fi = plug.sample(1200, return_index=True)
    n = plug.face_normals[fi]
    p = np.c_[pts[:, 0], np.abs(pts[:, 1]), pts[:, 2]]
    inside = body.contains(p - n * 0.05)
    sides = inside & (n[:, 2] < 0.5)
    if not sides.any():
        return 99.0
    p, n = p[sides], n[sides]
    best = np.full(len(p), 0.0)
    for w in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        q = p + n * w
        q[:, 1] = np.abs(q[:, 1])
        ok = body.contains(q)
        best = np.where(ok & (best >= w - 0.5 - 1e-9), w, best)
    return float(best.min())


def _front_view_top(wing, forward_parts) -> float:
    """Highest top (mm) of what stands ahead of the wing within its span."""
    b = wing.bounds
    top = 0.0
    for m in forward_parts:
        q = m.slice_plane([b[0, 0], 0, 0], [-1.0, 0, 0])
        if q is None or q.is_empty:
            continue
        q = q.slice_plane([0, b[1, 1], 0], [0, -1.0, 0])
        if q is None or q.is_empty:
            continue
        top = max(top, float(q.bounds[1, 2]))
    return top


# ------------------------------------------------------------------ gates
def measure(d, wing, struts, plugs, body, others, fwd, ref_b, wheel_rear, x_front_mm, W_mm, wall_top,
            x_bore_front, placed) -> dict:
    import trimesh
    g = {}
    b = wing.bounds
    allb = trimesh.util.concatenate([wing] + struts).bounds if struts else b
    g["T9.4.1_rw_behind_ref_B"] = float(allb[0, 0]) - ref_b
    g["T9.4.2_rw_overhang"] = cc.REAR_OVERHANG_MAX - (float(allb[1, 0]) - ref_b)
    g["T9.4.3_rw_height"] = cc.REAR_Z_MAX - float(allb[1, 2])
    g["T3.4_rw_width"] = HALF_WIDTH_MAX_MM - float(allb[1, 1])
    g["T9.5.1_rw_span"] = 2 * float(b[1, 1]) - cc.REAR_SPAN_MIN
    # chord along the track and thickness, on vertical cuts across the span
    chords, thicks = [], []
    for y in np.linspace(0.5, float(b[1, 1]) - 0.5, 6):
        s = wing.section(plane_origin=[0, y, 0], plane_normal=[0, 1.0, 0])
        if s is None:
            continue
        v = s.vertices
        chords.append(float(v[:, 0].max() - v[:, 0].min()))
        sec = section(d)
        thicks.append(max(_mid_z(sec, x)[1] for x in np.linspace(0.05, 0.95, 19) * d.chord_mm))
    if chords:
        g["T9.5.2_rw_chord_min"] = min(chords) - cc.REAR_CHORD_MIN
        g["T9.5.2_rw_chord_max"] = cc.REAR_CHORD_MAX - max(chords)
        g["T9.5.3_rw_thick_min"] = min(thicks) - cc.WING_THICK_MIN
        g["T9.5.3_rw_thick_max"] = cc.WING_THICK_MAX - max(thicks)
    tops = []
    for y in np.linspace(0.5, float(b[1, 1]) - 0.5, 8):
        s = wing.section(plane_origin=[0, y, 0], plane_normal=[0, 1.0, 0])
        if s is not None:
            tops.append(float(s.vertices[:, 2].max()))
    g["T9.5.4_rw_height_change"] = cc.REAR_HEIGHT_DEVIATION_MAX - (max(tops) - min(tops) if tops else 0.0)
    # T9.6: clear air, but within 5 mm sideways of a strut's joint
    pts, _ = trimesh.sample.sample_surface_even(wing, 2500, seed=3)
    keep = np.ones(len(pts), bool)
    for p in placed:
        keep &= np.abs(pts[:, 1] - p["y_mm"]) > p["t_mm"] / 2 + cc.CLEAR_AIR
    q = pts[keep]
    if len(q):
        gaps = [float(np.concatenate([trimesh.proximity.closest_point(m, q[i:i + 256])[1]
                                      for i in range(0, len(q), 256)]).min()) for m in [body] + others]
        g["T9.6_rw_clear_air"] = min(gaps + [float(q[:, 2].min())]) - cc.CLEAR_AIR
    g["T9.7_rw_seen_from_front"] = float(b[0, 2]) - _front_view_top(wing, fwd)
    # the struts: held at all, printable, clear of the wheels and of T7.9's zones, slots legal
    g["rw_supported"] = 1.0 if placed else -1.0
    if struts:
        g["rw_strut_wall"] = min(p["t_mm"] for p in placed) - cc.BUILD_WALL_MM
        P = np.vstack([s.sample(600) for s in struts])
        xa, y_in, R, wdt = wheel_rear
        # the rear wheel as a cylinder about its axle, y_in .. y_in + width
        r = np.hypot(P[:, 0] - xa, P[:, 2] - R)
        inside_y = (P[:, 1] > y_in - WHEEL_CLEAR_MM) & (P[:, 1] < y_in + wdt + WHEEL_CLEAR_MM)
        near = np.where(inside_y, r - (R + WHEEL_CLEAR_MM), 99.0)
        g["rw_strut_wheel_clear"] = float(near.min()) if inside_y.any() else 1.0
        import exact_zones as ez
        zv = ez.t79_zones(P[:, 0], np.abs(P[:, 1]), P[:, 2], W_mm, x_front_mm)
        g["rw_strut_T7.9_zones"] = -float(zv.max()) if (zv > 0).any() else 1.0
    import exact_zones as ez
    Pw = wing.sample(3000)
    zw = ez.t79_zones(Pw[:, 0], np.abs(Pw[:, 1]), Pw[:, 2], W_mm, x_front_mm)
    g["rw_T7.9_zones"] = -float(zw.max()) if (zw > 0).any() else 1.0
    if plugs:
        lows = []
        for pl, p in zip(plugs, [p for p in placed if p["slot_mm"] > 0]):
            over = abs(p["foot_mm"][1]) < 12.5 + BALL_R_MM and pl.bounds[1, 0] > x_bore_front - 3.0
            if over:
                lows.append(float(pl.bounds[0, 2]) - (wall_top + FOAM_WALL_MM))
            g[f"rw_slot{p['index']}_foam"] = _foam_round(body, pl) - (FOAM_WALL_MM - 0.05)
        if lows:
            g["rw_slot_T5.5_wall"] = min(lows)
    return g
