"""rear_wing_engine.py -- the searches' rear wing and the supports it grows (user 2026-11-23).

The wing is STRAIGHT: a symmetric NACA section, level, square to the car -- no sweep, no dihedral, no angle
of attack, no camber ("make all wings so that they HAVE to be straight with NO tilt and NO angling"). What
is searched: its chord, its thickness, its half span, and its height over the lowest T9.6 / T9.7 allow (its
place behind Ref B is the layout's).

Its supports are LOFTS, not struts (wing_loft.py: "similar to the halo loft ... attach on the sides of the
wings and connect it to the rest"): each grows from a patch of the wing -- anywhere from just off the centre
line (team rule, user 2026-11-23: nothing on the centre line of a rear wing) out to the tip, over part or
all of the chord -- down to the nearest point of the body under or beside it, its outline morphing from the
patch's to its foot's, flared or narrowed, pinched or not. Its base is trimmed to the body's surface (a
glued joint that fits the milled body). Mirrored: each support is a pair. Numbers per support: width at the
wing (under the print wall it is not there), where on the span, how much of the chord, the foot's scale,
the waist. Where it lands is the body's.

Measured (gates()): T9.4.1 (wing and supports behind Ref B), T9.4.2 (within 40 mm of it), T9.4.3 (65 mm),
T9.5.1 (span >= 50, one piece), T9.5.2 (chord 15-25), T9.5.3 (2-6 mm thick), T9.6 (5 mm clear air but within
5 mm sideways of a support's joint), T9.7, T3.4, T7.9's zones and the rear wheel's clearance for the
supports, the centre-line rule, and that the wing is held."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np

import component_contract as cc

N_SUPPORTS = 2
MARGIN_MM = 0.3
WHEEL_CLEAR_MM = 1.0
HALF_WIDTH_MAX_MM = 42.5        # T3.4: 85 mm
CENTRE_CLEAR_MM = 2.5           # team (user 2026-11-23): nothing on the centre line -- a support's inner face this far off it
FOOT_REACH_MM = 60.0            # a support reaches no further than this to the body
N_SPAN = 6


@dataclass
class Support:
    """The pair of side supports: each covers the wing's tip (where its aerofoil shows) and is lofted down to
    the body (wing_loft.py). Only shape numbers; where it lands is the body's."""
    plate_mm: float = 3.0       # its thickness outboard of the tip (T3.4 keeps the whole car 85 mm wide)
    ext: float = 0.3            # how far it runs past the chord, as a share of the chord (half fore, half aft)
    rise_mm: float = 3.0        # how far it stands above the wing's top
    foot_scale: float = 1.0     # its foot's size, times the plate's
    waist: float = 0.3          # pinched half way down by this share


@dataclass
class RearWingDesign:
    chord_mm: float = 15.3      # T9.5.2 minimum + 0.3
    t_mm: float = 2.3           # T9.5.3 minimum + 0.3
    half_span_mm: float = 26.0  # T9.5.1: >= 25 a side
    x_le_mm: float = 3.5        # leading edge behind Ref B
    lift_mm: float = 0.0        # above the lowest height T9.6 and T9.7 allow
    support: Support = field(default_factory=Support)


def from_dict(d: dict) -> RearWingDesign:
    d = dict(d)
    sp = d.pop("support", None) or {}
    keep = {f.name for f in dataclasses.fields(RearWingDesign)}
    return RearWingDesign(**{k: v for k, v in d.items() if k in keep and k != "supports"},
                          support=Support(**sp) if isinstance(sp, dict) else sp)


def params_dict(d: RearWingDesign) -> dict:
    return dataclasses.asdict(d)


def section(d: RearWingDesign) -> np.ndarray:
    """The straight wing's section, (x from the LE, z about the chord line): symmetric, its thickness t_mm
    (the printable blunt trailing edge included)."""
    import wings as wg
    tf = d.t_mm / d.chord_mm
    P = None
    for _ in range(3):
        P = wg.naca4(d.chord_mm, tf, 0.0, te_mm=cc.BUILD_WALL_MM)
        th = 2 * P[:, 1].max()
        if th <= 0 or abs(th - d.t_mm) < 1e-3:
            break
        tf *= d.t_mm / th
    return P


def _wing(d, x_le, z):
    """Right half of the straight wing (manifold, mm), its root just across the centre line."""
    import support_engine as se
    sec = section(d)
    st = [(float(y), np.c_[x_le + sec[:, 0], z + sec[:, 1]]) for y in np.linspace(-0.5, d.half_span_mm, N_SPAN)]
    return se.loft_sections(st) ^ se._box(-1e3, 1e3, 0.0, 1e3, -1e3, 1e3)


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


def build(d: RearWingDesign, body_half_m, x_front_mm, W_mm, wheel_rear, clear_of=(), forward_parts=()):
    """The wing and its supports, right halves (trimesh, metres), on this body. wheel_rear = (x_axle,
    y_inner, R, width); clear_of: other parts the wing keeps T9.6's 5 mm from; forward_parts: what T9.7
    looks over. Returns {"wing", "struts" (the supports), "plugs" ([]), "gates", "info"}."""
    import trimesh
    import support_engine as se
    import wing_loft as wl
    from scipy.spatial import cKDTree
    body = body_half_m.copy(); body.apply_scale(1e3)
    others = [m.copy() for m in clear_of]
    for m in others:
        m.apply_scale(1e3)
    fwd = [m.copy() for m in forward_parts]
    for m in fwd:
        m.apply_scale(1e3)
    info = {"design": params_dict(d)}
    ref_b = cc.ref_plane_B(x_front_mm, W_mm)
    sp = d.support
    plate = float(np.clip(sp.plate_mm, cc.BUILD_WALL_MM, 8.0))
    hs = float(np.clip(d.half_span_mm, cc.REAR_SPAN_MIN / 2 + MARGIN_MM, HALF_WIDTH_MAX_MM - MARGIN_MM - plate))
    chord = float(np.clip(d.chord_mm, cc.REAR_CHORD_MIN + MARGIN_MM, cc.REAR_CHORD_MAX - MARGIN_MM))
    t = float(np.clip(d.t_mm, cc.WING_THICK_MIN + MARGIN_MM, cc.WING_THICK_MAX - MARGIN_MM))
    room = cc.REAR_OVERHANG_MAX - 2 * MARGIN_MM - chord
    x_le = float(np.clip(ref_b + d.x_le_mm, ref_b + MARGIN_MM, ref_b + MARGIN_MM + max(room, 0.0)))
    # T7.9's zones run the car's full height: a wing tip in one moves aft until clear
    import exact_zones as ez
    Y_, Z_ = np.meshgrid(np.linspace(0.0, hs, 40), np.linspace(0.0, cc.REAR_Z_MAX, 14), indexing="ij")
    for _ in range(40):
        zv = ez.t79_zones(np.full(Y_.size, x_le - MARGIN_MM), Y_.ravel(), Z_.ravel(), W_mm, x_front_mm)
        if not (zv > -MARGIN_MM).any():
            break
        x_le += float(zv.max()) + MARGIN_MM + 0.05
        info["moved_aft_of_T7.9"] = True
    d = dataclasses.replace(d, half_span_mm=hs, chord_mm=chord, t_mm=t)
    info.update(half_span_mm=hs, chord_mm=chord, t_mm=t, x_le_mm=x_le)

    def bands():
        return [(hs - cc.CLEAR_AIR, hs + plate)]          # the joints with the side supports, at the tips

    # -- height: the lowest T9.6 (but at the joints) and T9.7 allow, then the search's lift --------------
    cloud = np.vstack([m.sample(int(min(400000, max(20000, m.area * 8)))) for m in [body] + others])
    tree = cKDTree(cloud)
    base = se._to_trimesh(_wing(d, x_le, 0.0))
    pts0, _ = trimesh.sample.sample_surface_even(base, 1500, seed=1)
    keep = np.ones(len(pts0), bool)
    for a, b in bands():
        keep &= ~((pts0[:, 1] >= a) & (pts0[:, 1] <= b))
    q0 = pts0[keep] if keep.any() else pts0
    lo0 = float(base.bounds[0, 2])

    def short(zr, exact=False):
        q = q0 + np.array([0.0, 0.0, zr])
        if exact:
            gap = min(float(np.concatenate([trimesh.proximity.closest_point(m, q[i:i + 256])[1]
                                            for i in range(0, len(q), 256)]).min()) for m in [body] + others)
        else:
            gap = float(tree.query(q)[0].min()) - 0.15
        gap = min(gap, float(q[:, 2].min()))
        w_ = base.copy(); w_.apply_translation([0.0, 0.0, zr])
        return cc.CLEAR_AIR + MARGIN_MM - gap, _front_view_top(w_, fwd) + 0.1 - (lo0 + zr)
    lo, hi = 0.0, cc.REAR_Z_MAX
    if max(short(hi)) > 0:
        z = hi
    else:
        for _ in range(16):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if max(short(mid)) > 0 else (lo, mid)
        z = hi
        for _ in range(3):
            a, b = short(z, exact=True)
            if max(a, b) <= 0:
                break
            z += max(a, b) + 0.05
    wing_tm = se._to_trimesh(_wing(d, x_le, z))
    room_up = (cc.REAR_Z_MAX - MARGIN_MM) - float(wing_tm.bounds[1, 2])
    lift = float(np.clip(d.lift_mm, 0.0, max(room_up, 0.0)))
    if lift > 0:
        z += lift
        wing_tm = se._to_trimesh(_wing(d, x_le, z))
    info.update(z_chord_mm=z, lift_used_mm=lift)

    # -- the side supports: from the wing's tips (their aerofoil faces) lofted to the body --------------
    t_half = 0.5 * float(wing_tm.bounds[1, 2] - wing_tm.bounds[0, 2])
    z_bot, z_top = z - t_half, z + t_half
    rise = float(np.clip(sp.rise_mm, 0.0, max((cc.REAR_Z_MAX - MARGIN_MM) - z_top, 0.0)))
    ext = float(np.clip(sp.ext, 0.0, 0.8))
    Mbody = se._to_manifold(body)
    sup, placed = None, []
    for _ in range(10):
        x0 = max(x_le - 0.5 * ext * chord, ref_b + MARGIN_MM)
        x1 = min(x_le + chord + 0.5 * ext * chord, ref_b + cc.REAR_OVERHANG_MAX - MARGIN_MM)
        y0, y1 = hs - 0.3, hs + plate                     # 0.3 mm into the wing's tip: one printed part
        bottom = np.array([0.5 * (x0 + x1), 0.5 * (y0 + y1), z_bot])
        foot = wl.first_hit(body, bottom, np.array([0.0, 0.0, -1.0]))
        if foot is None:                                  # nothing under the tip: the body's nearest point
            q, dist, _ = trimesh.proximity.closest_point(body, bottom[None])
            foot = q[0] if dist[0] <= FOOT_REACH_MM and q[0][2] < z_bot else None
        if foot is None:
            break
        fs = float(np.clip(sp.foot_scale, 0.3, 3.0))
        while fs > 0.25:
            hy = 0.5 * (y1 - y0) * fs
            if foot[1] - hy >= CENTRE_CLEAR_MM and foot[1] + hy <= HALF_WIDTH_MAX_MM - MARGIN_MM:
                break
            fs *= 0.85
        m = wl.loft((x0, x1, y0, y1), z_bot, (foot[0], foot[1]), foot[2], foot_scale=fs,
                    waist=float(np.clip(sp.waist, 0.0, 0.7)), hold_mm=z_top + rise - z_bot, axis="z")
        if m is not None:
            # its base fitted to the milled body (glued, no pocket); the right half
            M = (m - Mbody) ^ se._box(-1e3, 1e3, 0.0, 1e3, -1e3, 1e3)
            pcs = sorted(M.decompose(), key=lambda p: -p.volume())
            if pcs and _clear(wl.to_trimesh(pcs[0]), wheel_rear, W_mm, x_front_mm):
                sup = wl.to_trimesh(pcs[0])
                placed = [dict(y_mm=round(0.5 * (y0 + y1), 2), width_mm=round(y1 - y0, 2), plate_mm=plate,
                               x_mm=[round(x0, 2), round(x1, 2)], rise_mm=round(rise, 2),
                               foot_mm=[round(float(v), 2) for v in foot], foot_scale=round(fs, 3))]
                break
        ext *= 0.7                                        # shorter, then a smaller foot, until it is clear
        sp = dataclasses.replace(sp, foot_scale=sp.foot_scale * 0.85)
    if sup is None:
        info["supports_not_placed"] = True
    info["struts"] = placed
    info["supported"] = bool(placed)
    gates = measure(d, wing_tm, sup, body, others, fwd, ref_b, wheel_rear, x_front_mm, W_mm, placed)
    out = {"gates": gates, "info": info, "plugs": []}
    q = wing_tm.copy(); q.apply_scale(1e-3); out["wing"] = q
    out["struts"] = []
    if sup is not None:
        q = sup.copy(); q.apply_scale(1e-3); out["struts"].append(q)
    return out


def _clear(m, wheel_rear, W_mm, x_front_mm) -> bool:
    """A support (mm) out of T7.9's zones and clear of the rear wheel."""
    import exact_zones as ez
    P = m.sample(2000)
    if (ez.t79_zones(P[:, 0], np.abs(P[:, 1]), P[:, 2], W_mm, x_front_mm) > -MARGIN_MM).any():
        return False
    xa, y_in, R, wdt = wheel_rear
    inside_y = (P[:, 1] > y_in - WHEEL_CLEAR_MM) & (P[:, 1] < y_in + wdt + WHEEL_CLEAR_MM)
    return not (inside_y & (np.hypot(P[:, 0] - xa, P[:, 2] - R) < R + WHEEL_CLEAR_MM)).any()


def measure(d, wing, sup, body, others, fwd, ref_b, wheel_rear, x_front_mm, W_mm, placed) -> dict:
    import trimesh
    import exact_zones as ez
    g = {}
    b = wing.bounds
    allb = trimesh.util.concatenate([wing, sup]).bounds if sup is not None else b
    g["T9.4.1_rw_behind_ref_B"] = float(allb[0, 0]) - ref_b
    g["T9.4.2_rw_overhang"] = cc.REAR_OVERHANG_MAX - (float(allb[1, 0]) - ref_b)
    g["T9.4.3_rw_height"] = cc.REAR_Z_MAX - float(allb[1, 2])
    g["T3.4_rw_width"] = HALF_WIDTH_MAX_MM - float(allb[1, 1])
    g["T9.5.1_rw_span"] = 2 * float(b[1, 1]) - cc.REAR_SPAN_MIN
    g["T9.5.2_rw_chord_min"] = float(b[1, 0] - b[0, 0]) - cc.REAR_CHORD_MIN
    g["T9.5.2_rw_chord_max"] = cc.REAR_CHORD_MAX - float(b[1, 0] - b[0, 0])
    g["T9.5.3_rw_thick_min"] = float(b[1, 2] - b[0, 2]) - cc.WING_THICK_MIN
    g["T9.5.3_rw_thick_max"] = cc.WING_THICK_MAX - float(b[1, 2] - b[0, 2])
    pts, _ = trimesh.sample.sample_surface_even(wing, 2500, seed=3)
    keep = np.ones(len(pts), bool)
    for p in placed:                                     # the joint with a side support: 5 mm in from the tip
        keep &= pts[:, 1] < b[1, 1] - cc.CLEAR_AIR
    q = pts[keep]
    if len(q):
        gaps = [float(np.concatenate([trimesh.proximity.closest_point(m, q[i:i + 256])[1]
                                      for i in range(0, len(q), 256)]).min()) for m in [body] + others]
        g["T9.6_rw_clear_air"] = min(gaps + [float(q[:, 2].min())]) - cc.CLEAR_AIR
    g["T9.7_rw_seen_from_front"] = float(b[0, 2]) - _front_view_top(wing, fwd)
    Pw = wing.sample(3000)
    zw = ez.t79_zones(Pw[:, 0], np.abs(Pw[:, 1]), Pw[:, 2], W_mm, x_front_mm)
    g["rw_T7.9_zones"] = -float(zw.max()) if (zw > 0).any() else 1.0
    g["rw_supported"] = 1.0 if placed else -1.0
    if sup is not None:
        P = sup.sample(4000)
        g["team_rw_no_centre_strut"] = float(np.abs(sup.vertices[:, 1]).min()) - (CENTRE_CLEAR_MM - 0.05)
        xa, y_in, R, wdt = wheel_rear
        r = np.hypot(P[:, 0] - xa, P[:, 2] - R)
        inside_y = (P[:, 1] > y_in - WHEEL_CLEAR_MM) & (P[:, 1] < y_in + wdt + WHEEL_CLEAR_MM)
        g["rw_support_wheel_clear"] = float(np.where(inside_y, r - (R + WHEEL_CLEAR_MM), 99.0).min())
        zv = ez.t79_zones(P[:, 0], np.abs(P[:, 1]), P[:, 2], W_mm, x_front_mm)
        g["rw_support_T7.9_zones"] = -float(zv.max()) if (zv > 0).any() else 1.0
        g["rw_support_wall"] = min(p["plate_mm"] for p in placed) - cc.BUILD_WALL_MM
    return g
