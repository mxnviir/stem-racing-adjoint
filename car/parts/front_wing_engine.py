"""front_wing_engine.py -- the searches' front wing: one piece or two, with the supports it designs itself.

  pieces      1: one wing across the centre line; 2: a left and a right wing (T8.6.1: two segments of at
              least 25 mm each where another part, the nose or a support, passes through the span).
  element     a flat NACA 0015 (user 2026-11-22: low drag, low lift), chord 15.3-25 mm (T8.6.2),
              STRAIGHT (user 2026-11-23: no sweep, no dihedral, no tilt), so every vertical cut is the
              true section (T8.6.2 and T8.6.3 are measured on such cuts).
  supports    lofts (wing_loft.py, like the halo's loft): each grows from a patch of the wing -- anywhere on
              the span the rules let a support stand, over part or all of the chord -- to the nearest point
              of the nose, above or below, its outline morphing from the patch's to its foot's; printed with
              the nose (nose.stl). A wing passing through the nose is held by the nose (T8.6.1's figures).
              Numbers: width, where on the span, how much of the chord, the foot's scale, the waist.

Legal by construction where that is cheap, measured always (gates()):
  T8.5.1  supports inside |y| <= 15, z <= 25, ahead of Ref A.
  T8.5.2  the wing ahead of Ref A; no higher than 20 mm beyond 15 mm out (it is level: its height).
  T8.6.1  each element's span from the nose or support that cuts it (or from the centre) >= 25 (the
          tip is pushed out until it is), one piece >= 50.
  T8.6.2/3  chord 15-25, thickness 2-6 (the section: 15 % of a 15.3-25 mm chord).
  T8.7    5 mm of clear air to the track, the wheels, the body and the nose, except within 5 mm of the
          wing's joints with its supports (the fillet the rule allows): a wing under the nose is lowered
          to keep it, and refused if that would take it under the track's 5 mm.
  T8.8    nothing ahead of the wing outside the nose (the nose is all there is ahead of it).
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field

import numpy as np

import component_contract as cc

T_FRAC = 0.15                  # NACA 0015
CLEAR_MM = 5.0                 # T8.7
SUPPORT_BAND_MM = 15.0         # T8.5.1
HIGH_OUTBOARD_MM = 20.0        # T8.5.2
SEGMENT_MIN_MM = 25.0          # T8.6.1
OVERHANG_MM = 40.0             # T8.2: the car's front no more than this ahead of Ref A
MARGIN_MM = 0.3                # kept off every limit
EMBED_MM = 1.0                 # a pylon runs this far into the nose and into the wing
N_SPAN = 24                    # sections along an element


@dataclass
class Support:
    """A support grown from a patch of the wing to the nose (wing_loft.py): only shape numbers."""
    width_mm: float = 6.0          # along the span, where it leaves the wing; under the print wall: not there
    y_frac: float = 0.5            # where on the span: 0 the centre (or a half's root), 1 the furthest out a
                                   # support may stand (T8.5.1's 15 mm, and 25 mm of span beyond it, T8.6.1)
    chord_frac: float = 0.6        # how much of the chord it leaves from (centred on the chord)
    foot_scale: float = 1.0        # its foot's size, times the patch's
    waist: float = 0.2             # pinched half way by this share


@dataclass
class FrontWingDesign:
    """STRAIGHT (user 2026-11-23: no tilt, no angling): a level NACA 0015, square to the car."""
    pieces: int = 1                # 1 or 2
    chord_mm: float = 15.3         # T8.6.2 minimum + 0.3 for the print
    te_gap_mm: float = 6.0         # trailing edge this far ahead of Ref A (T8.7: >= 5 to the body)
    z_mm: float = 8.0              # chord line height
    tip_y_mm: float = 36.5         # tip: just outboard of the front wheel by default
    root_y_mm: float = 8.0         # two pieces: where each half starts (inside the support band)
    supports: tuple = field(default_factory=lambda: (Support(), Support()))


def from_dict(d: dict) -> FrontWingDesign:
    keep = {f.name for f in dataclasses.fields(FrontWingDesign)}
    d = dict(d)
    sp = tuple(Support(**q) if isinstance(q, dict) else q for q in d.pop("supports", ()))
    return FrontWingDesign(**{k: v for k, v in d.items() if k in keep and k != "supports"}, supports=sp)


def params_dict(d: FrontWingDesign) -> dict:
    return dataclasses.asdict(d)


def naca00(chord, t_frac=T_FRAC, n=48):
    """Closed symmetric NACA 4-digit section (x from 0 at the LE to chord, z), anticlockwise, with the
    trailing edge closed to the printer's minimum."""
    beta = np.linspace(0.0, math.pi, n)
    xc = 0.5 * (1 - np.cos(beta))
    yt = 5 * t_frac * (0.2969 * np.sqrt(xc) - 0.1260 * xc - 0.3516 * xc ** 2 + 0.2843 * xc ** 3 - 0.1036 * xc ** 4)
    te = cc.BUILD_WALL_MM / 2 / chord
    yt = np.maximum(yt, te * xc)                  # a printable trailing edge, never thinner than the wall
    upper = np.c_[xc[::-1], yt[::-1]]
    lower = np.c_[xc[1:-1], -yt[1:-1]]
    return np.vstack([upper, lower]) * chord     # TE (top) -> LE -> TE (bottom): anticlockwise in (x, z)


def _loft(stations):
    import support_engine as se
    return se.loft_sections(stations)


def element(d: FrontWingDesign, y0, y1, x_le_root, z_root):
    """One straight wing element from y0 to y1 (y0 < y1) (manifold, mm)."""
    sec = naca00(d.chord_mm)
    return _loft([(float(y), np.c_[x_le_root + sec[:, 0], z_root + sec[:, 1]]) for y in (y0, y1)])


def _loft_z(stations):
    """Closed solid through (x, y) sections stacked along z: [(z, (n, 2) array)] (manifold, mm)."""
    import trimesh
    import support_engine as se
    rings = [np.c_[P[:, 0], P[:, 1], np.full(len(P), z)] for z, P in stations]
    n, N = len(rings[0]), len(rings)
    V = np.vstack(rings + [np.mean(rings[0], 0)[None], np.mean(rings[-1], 0)[None]])
    F = []
    for i in range(N - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            c_, d_ = (i + 1) * n + j, (i + 1) * n + (j + 1) % n
            F += [(a, b, d_), (a, d_, c_)]
    c0, c1 = N * n, N * n + 1
    for j in range(n):
        F.append((c0, (j + 1) % n, j))
        F.append((c1, (N - 1) * n + j, (N - 1) * n + (j + 1) % n))
    m = trimesh.Trimesh(V, np.array(F), process=False)
    if m.volume < 0:
        m.invert()
    return se._to_manifold(m)


def _nose_hits(nose_tm, x, y, z0):
    """(z of the nose's surface above z0, below z0) along the vertical through (x, y), or None."""
    o = np.array([[x, y, z0], [x, y, z0]])
    dirs = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]])
    loc, ri, _ = nose_tm.ray.intersects_location(o, dirs, multiple_hits=True)
    loc = np.asarray(loc).reshape(-1, 3); ri = np.asarray(ri).reshape(-1)
    up = loc[ri == 0, 2]
    dn = loc[ri == 1, 2]
    return (float(up.min()) if len(up) else None), (float(dn.max()) if len(dn) else None)


def _ray_hit(m, o, d):
    """The first surface of m from o along d (mm), or None."""
    loc, _, _ = m.ray.intersects_location(o[None], (d / np.linalg.norm(d))[None], multiple_hits=True)
    if not len(loc):
        return None
    return loc[np.argmin(np.linalg.norm(loc - o, axis=1))]


def build(d: FrontWingDesign, nose_half_m, x_front_mm, wheel, body_half_m=None):
    """The wing and its pylons, right halves (trimesh, metres), for this nose. wheel = (x_axle, y_inner,
    R) of the front wheel. Returns {"wing": trimesh, "pylons": trimesh or None, "gates": {...}, "info": {...}}.
    A wing the nose does not hold, closer than 5 mm to it, is lowered by what it lacks and built again
    (down to the track's own 5 mm)."""
    r = _build_once(d, nose_half_m, x_front_mm, wheel, body_half_m)
    for _ in range(3):
        short = -r["gates"].get("T8.7_fw_nose", 0.0)
        if short <= 0 or r["info"].get("held_by_nose"):
            break
        d = dataclasses.replace(d, z_mm=r["info"]["z_mm"] - short - MARGIN_MM)
        r2 = _build_once(d, nose_half_m, x_front_mm, wheel, body_half_m)
        r2["info"]["lowered_for_clear_air_mm"] = r["info"].get("lowered_for_clear_air_mm", 0.0) + short + MARGIN_MM
        r = r2
    return r


def _build_once(d: FrontWingDesign, nose_half_m, x_front_mm, wheel, body_half_m=None):
    import support_engine as se
    import trimesh
    ref_a = x_front_mm - 16.0
    nose = nose_half_m.copy(); nose.apply_scale(1e3)
    info = dict(design=params_dict(d))
    t = T_FRAC * d.chord_mm
    # the whole wing between the car's front limit (T8.2: 40 mm ahead of Ref A) and te_gap ahead of Ref A
    gap = float(np.clip(d.te_gap_mm, CLEAR_MM, OVERHANG_MM - MARGIN_MM - d.chord_mm))
    x_le = ref_a - gap - d.chord_mm
    info.update(x_le_root_mm=x_le, front_x_mm=x_le, te_gap_used_mm=gap)
    # level, under 20 mm (T8.5.2 outboard of 15 mm) and 5 mm off the track
    z = float(np.clip(d.z_mm, CLEAR_MM + t / 2 + MARGIN_MM, HIGH_OUTBOARD_MM - t / 2 - MARGIN_MM))
    d = dataclasses.replace(d, z_mm=z)
    info.update(z_mm=z)
    # where the nose cuts the span, at the wing's height (its half-width there)
    xs = np.linspace(x_le, x_le + d.chord_mm, 7)
    cut, cut_min = 0.0, np.inf
    for x in xs:
        s = nose.section(plane_origin=[x, 0, 0], plane_normal=[1, 0, 0])
        near = s.vertices[np.abs(s.vertices[:, 2] - z) < t / 2 + 0.5] if s is not None else np.zeros((0, 3))
        w = float(near[:, 1].max()) if len(near) else 0.0
        cut, cut_min = max(cut, w), min(cut_min, w)
    info["nose_cut_y_mm"] = cut                           # widest along the chord: where the span is cut
    info["nose_cut_min_y_mm"] = cut_min                   # narrowest: a root inside it is held all along
    # the nose's half-width anywhere over the wing's length (where a pylon can reach it from above or below)
    hw_any = 0.0
    for x in xs:
        s_ = nose.section(plane_origin=[x, 0, 0], plane_normal=[1, 0, 0])
        if s_ is not None:
            hw_any = max(hw_any, float(s_.vertices[:, 1].max()))
    info["nose_half_width_mm"] = hw_any
    if d.pieces == 2:
        # each half starts in the nose's side (the nose holds it) or, where the wing passes over or under
        # the nose, above or below it, where a pylon reaches the nose
        lim = (cut_min - EMBED_MM) if cut_min > EMBED_MM + 0.5 else (hw_any - cc.BUILD_WALL_MM / 2 - 0.5)
        y0 = float(np.clip(min(d.root_y_mm, lim), 0.5, SUPPORT_BAND_MM - 1.0))
    else:
        y0 = -0.5                                         # across the centre line (mirrored: one piece)
    seg_from = max(cut, max(y0, 0.0))
    tip = max(d.tip_y_mm, seg_from + SEGMENT_MIN_MM + MARGIN_MM,
              (SEGMENT_MIN_MM + MARGIN_MM) if d.pieces == 1 and cut == 0.0 else 0.0)
    info["tip_y_mm"] = tip
    el = element(d, y0, tip, x_le, z)
    el = el ^ se._box(-1e3, 1e3, 0.0, 1e3, -1e3, 1e3)     # right half
    wing = se._to_trimesh(el)
    # is the wing held by the nose (does it run into it)?
    inside = trimesh.boolean.intersection([wing, nose], engine="manifold") if nose.is_volume else None
    held = inside is not None and not inside.is_empty and abs(inside.volume) > 1.0
    info["held_by_nose"] = bool(held)
    # supports: lofts from patches of the wing to the nose (wing_loft.py), printed with the nose
    import wing_loft as wl
    sups = [q for q in d.supports if q.width_mm >= cc.BUILD_WALL_MM]
    if not sups and not held and d.supports:
        # nothing holds the wing and every support is under the print wall: the widest, at the wall
        k = int(np.argmax([q.width_mm for q in d.supports]))
        sups = [dataclasses.replace(d.supports[k], width_mm=cc.BUILD_WALL_MM)]
        info["support_widened_to_wall"] = k
    pylons, placed = [], []
    # a support breaks the span (T8.6.1): none stands further out than leaves the tip's 25 mm beyond it,
    # and T8.5.1 keeps them inside 15 mm
    y_out = min(SUPPORT_BAND_MM - MARGIN_MM, tip - SEGMENT_MIN_MM - MARGIN_MM)
    for i, q in enumerate(sups):
        w = float(np.clip(q.width_mm, cc.BUILD_WALL_MM, 2 * y_out))
        y_lo = (max(y0, 0.0) + w / 2) if d.pieces == 2 else 0.0
        y_hi = y_out - w / 2
        yc = y_lo + float(np.clip(q.y_frac, 0.0, 1.0)) * max(y_hi - y_lo, 0.0)
        if d.pieces == 1 and yc < w / 2:
            yc = 0.0                                      # across the centre line: one support
        cf = float(np.clip(q.chord_frac, 0.2, 1.0))
        x0, x1 = x_le + d.chord_mm * (0.5 - cf / 2), x_le + d.chord_mm * (0.5 + cf / 2)
        o = np.array([0.5 * (x0 + x1), max(yc, 0.05), z])
        if nose.is_volume and nose.contains(o[None])[0]:
            info.setdefault("supports_in_the_nose", []).append(i)   # the nose holds the wing there itself
            continue
        import trimesh as _tm
        # the foot: the nose straight above or below the patch (the nearer), or its nearest point
        hits = [h for h in (wl.first_hit(nose, o, np.array([0, 0, -1.0])), wl.first_hit(nose, o, np.array([0, 0, 1.0])))
                if h is not None]
        if hits:
            foot = min(hits, key=lambda h: abs(h[2] - z))
        else:
            qq, dist, _ = _tm.proximity.closest_point(nose, o[None])
            foot = qq[0] if dist[0] <= 30.0 else None
        if foot is None:
            info.setdefault("supports_not_placed", []).append(i)
            continue
        if yc == 0.0:
            foot = np.array([foot[0], 0.0, foot[2]])
        fs = float(np.clip(q.foot_scale, 0.3, 3.0))
        ok = False
        for _ in range(12):                               # the foot inside T8.5.1's band and the span rule
            ok = abs(foot[1]) + 0.5 * w * fs <= y_out and foot[0] + 0.5 * (x1 - x0) * fs <= ref_a - MARGIN_MM
            if ok:
                break
            fs *= 0.85
        if not ok:
            info.setdefault("supports_not_placed", []).append(i)
            continue
        m = wl.loft((x0, x1, yc - w / 2, yc + w / 2), z, (foot[0], foot[1]), foot[2], foot_scale=fs,
                    waist=float(np.clip(q.waist, 0.0, 0.7)), past_mm=EMBED_MM)
        if m is None:
            info.setdefault("supports_not_placed", []).append(i)
            continue
        pylons.append(se._to_manifold(m))
        placed.append(dict(index=i, y_mm=round(yc, 2), t_mm=w, width_mm=round(w, 2), chord_frac=round(cf, 3),
                           nose_mm=[round(float(u), 2) for u in foot], foot_scale=round(fs, 3)))
    info["struts"] = placed
    info["pylon_y_placed_mm"] = [p["y_mm"] for p in placed]
    pyl = None
    if pylons:
        import manifold3d as mf
        Pm = mf.Manifold.batch_boolean(pylons, mf.OpType.Add) ^ se._box(-1e3, 1e3, 0.0, 1e3, -1e3, 1e3)
        pyl = se._to_trimesh(Pm)
    info["supported"] = bool(held or placed)
    gates = measure(d, wing, pyl, nose, ref_a, wheel, body_half_m, info)
    wing.apply_scale(1e-3)
    if pyl is not None:
        pyl.apply_scale(1e-3)
    return {"wing": wing, "pylons": pyl, "gates": gates, "info": info}


def _chunked(f, pts, n=256):
    """f over the points a few hundred at a time: trimesh's closest point pairs every point with every
    triangle near it, which on a fine nose ran to 35 million pairs (a 10 GB build killed, gallery G01)."""
    return np.concatenate([np.asarray(f(pts[i:i + n]), float) for i in range(0, len(pts), n)]) if len(pts) else np.zeros(0)


def measure(d, wing, pyl, nose, ref_a, wheel, body_half_m, info) -> dict:
    """Gates (+ = passes, mm) measured on the built wing and pylons (all mm, right halves)."""
    import trimesh
    g = {}
    b = wing.bounds
    g["fw_supported"] = 0.0 if info["supported"] else -1.0
    g["T8.5.2_fw_ahead_of_ref_A"] = ref_a - float(b[1, 0])
    g["T8.2_fw_inside_overhang"] = OVERHANG_MM - (ref_a - float(b[0, 0]))
    out = wing.vertices[wing.vertices[:, 1] > SUPPORT_BAND_MM]
    if len(out):
        g["T8.5.2_fw_height_outboard"] = HIGH_OUTBOARD_MM - float(out[:, 2].max())
    seg_from = max(info["nose_cut_y_mm"], max(float(b[0, 1]), 0.0) if d.pieces == 2 else 0.0)
    if pyl is not None:
        seg_from = max(seg_from, float(pyl.bounds[1, 1]))
    seg = float(b[1, 1]) - seg_from
    g["T8.6.1_fw_segment"] = seg - SEGMENT_MIN_MM if (seg_from > 0 or d.pieces == 2) else 2 * float(b[1, 1]) - 2 * SEGMENT_MIN_MM
    g["T8.6.2_fw_chord_min"] = d.chord_mm - 15.0
    g["T8.6.2_fw_chord_max"] = 25.0 - d.chord_mm
    g["T8.6.3_fw_thickness_min"] = T_FRAC * d.chord_mm - 2.0
    g["T8.6.3_fw_thickness_max"] = 6.0 - T_FRAC * d.chord_mm
    if pyl is not None:
        pb = pyl.bounds
        g["T8.5.1_fw_support_half_width"] = SUPPORT_BAND_MM - float(pb[1, 1])
        g["T8.5.1_fw_support_height"] = 25.0 - float(pb[1, 2])
        g["T8.5.1_fw_support_ahead_of_ref_A"] = ref_a - float(pb[1, 0])
    # T8.7: clear air from the wing's surface to everything else, the joints excepted
    pts, _ = trimesh.sample.sample_surface(wing, 4000, seed=5)
    # the joints: where the wing meets the nose (it runs into it) and its pylons. Beside each, the corner
    # the 5 mm ball on its rod cannot enter is the fillet the rule allows: a spanwise band 5 mm wide
    # outboard of the nose where it cuts the wing, and 5 mm either side of each pylon (as the referee).
    near_joint = np.zeros(len(pts), bool)
    # as the referee (legality: points within 5 mm sideways of the nose's widest are its joint's fillet)
    near_joint |= pts[:, 1] < float(nose.bounds[1, 1]) + CLEAR_MM
    if info.get("held_by_nose"):
        near_joint |= pts[:, 1] < max(info["nose_cut_y_mm"], info.get("nose_half_width_mm", 0.0)) + CLEAR_MM
    for p in info.get("struts", []):
        near_joint |= np.abs(pts[:, 1] - p["y_mm"]) < p["t_mm"] / 2 + CLEAR_MM
    free = pts[~near_joint]
    g["T8.7_fw_track"] = float(wing.bounds[0, 2]) - CLEAR_MM
    xa, y_in, R = wheel
    g["T8.7_fw_wheel"] = (xa - R) - float(b[1, 0]) - CLEAR_MM
    if len(free):
        if nose.is_volume:
            sd = _chunked(lambda q: trimesh.proximity.signed_distance(nose, q), free)
            dn = np.where(sd > 0, 0.0, np.abs(sd))
        else:
            dn = np.full(len(free), 99.0)
        g["T8.7_fw_nose"] = float(dn.min()) - CLEAR_MM
        info["fw_nose_clear_mm"] = float(dn.min())
    if body_half_m is not None:
        body = body_half_m.copy(); body.apply_scale(1e3)
        if len(free):
            db = _chunked(lambda q: trimesh.proximity.closest_point(body, q)[1], free)
            g["T8.7_fw_body"] = float(db.min()) - CLEAR_MM
    return g
