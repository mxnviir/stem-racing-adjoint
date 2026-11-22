"""Wheel-support generator: the structure between the body and the wheel's disc is the generator's OWN geometry.

Per axle, one printed ABS part, wheel to wheel. Fixed (standard, sized for the loads): the stub axle with its
bearing seat and boss, and the flat disc covering the wheel's inner side (Part 4 `beam_support` helpers).
Generated: everything between the car's centre plane and the disc, as a free-form field on a fine grid
(default 0.4 mm), turned into a buildable part by rules, never by shape parameters:

  legal     inside the wheels' cylinder (T7.12.1), >= 1.5 mm off the track (T3.7), inboard of the disc,
            clear of the hang-test claw band (T7.13: 1.5 mm in from the wheel's inner face, outer 1.5 mm of
            radius); it may run INTO the body (then the foam is pocketed and the print is the body there)
  wall      morphological opening with a 1.05 mm ball: nothing thinner than the printer's wall survives
  piece     face-connected; only material that reaches BOTH the centre plane (y = 0: one part wheel to
            wheel) and the disc is kept; nothing kept = refused
  glue      at least MIN_BODY_CONTACT_MM2 of contact with the body (per half)
  loads     Part 4's load case (3 N radial at the bearing, 1.2 N at the tyre, ABS 40 MPa / safety 2, 0.15 mm
            sag at the bearing), checked slice by slice along the axle with beam theory: an ESTIMATE, as in
            Part 4. The stub and disc keep Part 4's own checks.

    python support_gen.py demo <car folder> [--h 0.4] [--out runs/support_gen]
        builds a test set of fields (full envelope, load-carved, random smooth, a deliberately broken one),
        renders each and writes <out>/<design>/car (the car with that support, CFD-ready) + report.json
    python support_gen.py add <car folder> <field.npz> [--out ...]   one design from a saved field

The grid spacing is a parameter, and the part is a triangle mesh in the car frame: it works with any CFD
mesh. Thin parts need surface refinement in CFD: GATE_PLUS_SURFACES=supports (gate.py) refines the patch to
level 5 on every resolution.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in ("part4-simulation", "part1-simulation", "part2-simulation"):
    sys.path.insert(0, str(ROOT / p))
sys.path.insert(0, str(HERE))

ABS_G_CM3, FOAM_G_CM3 = 1.04, 0.163
WALL_MM = 1.05                      # printer minimum + build margin (component_contract.BUILD_WALL_MM)
TRACK_MM = 1.5                      # T3.7
CLAW_MM = 1.5                       # T7.13 lip
CYL_MARGIN_MM = 0.3                 # inside the wheels' cylinder by at least this
MIN_BODY_CONTACT_MM2 = 10.0         # glue land with the foam, per half
TEAM_SUPPORTS_G = 5.882             # the team's two supports, already inside geometry.other_parts_g (assumed)


# ------------------------------------------------------------------ fixed parts (Part 4)
def fixed_parts(ax: dict, footprint_w_mm: float) -> dict:
    """Disc + boss + stub for one axle (full width, mm), sized by Part 4's load case."""
    import trimesh
    import beam_support as bsm
    import wheel as wh
    bs = bsm.BeamSupport(hubcap=False)
    hub = wh.hub_span_mm()[0 if ax["tag"] == "front" else 1]
    y_disc_out = ax["y_in"] + bs.disc_recess_mm
    y_bear = ax["y_in"] + 0.5 * (hub[0] + hub[1])
    y_tip = ax["y_in"] + ax["w"]
    M = bsm.LOAD_RADIAL_N * (y_bear - y_disc_out) + bsm.LOAD_AXIAL_N * ax["R"]
    w = max(footprint_w_mm, WALL_MM)
    t_d = max(WALL_MM, math.sqrt(6 * (M / 2) / (w * bsm.ABS_STRENGTH_MPA / bsm.SAFETY)))
    r_d = min(bs.disc_r_mm, ax["z"] - TRACK_MM - 0.1, bsm.RIM_INNER_R_MM - 0.5)
    root_d = bsm.sized_root_d_mm(bs, y_disc_out, y_bear, ax["R"])
    line = bsm.stub_outline(bs, y_disc_out, y_bear, y_tip, root_d)
    st = bsm.structure(bs, line, y_bear, y_disc_out, ax["R"])
    prof = [(0.0, y_disc_out - 0.01)] + list(line) + [(0.0, y_tip)]
    stub = bsm._revolve_y(prof, ax["x"], ax["z"])
    stub.apply_scale(1e3)
    disc = trimesh.creation.cylinder(radius=r_d, height=t_d, sections=96)
    disc.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    disc.apply_translation([ax["x"], y_disc_out - t_d / 2, ax["z"]])
    return {"disc": disc, "stub": stub, "t_disc": t_d, "r_disc": r_d, "y_disc_out": y_disc_out,
            "y_disc_in": y_disc_out - t_d, "y_bear": y_bear, "stub_struct": st,
            "disc_stress_mpa": 6 * (M / 2) / (w * t_d ** 2)}


# ------------------------------------------------------------------ grid
class AxleGrid:
    def __init__(self, ax: dict, body_half, h: float = 0.4):
        """ax: x, y_in, w, R, z (mm, car frame), tag. body_half: right-half body (metres)."""
        self.ax, self.h = ax, h
        R = ax["R"]
        self.x = np.arange(ax["x"] - R - 1, ax["x"] + R + 1 + h / 2, h)
        self.y = np.arange(h / 2, ax["y_in"] + 2.0, h)               # cell centres, y > 0
        self.z = np.arange(0.0 + h / 2, ax["z"] + R + 1, h)
        X, Y, Z = np.meshgrid(self.x, self.y, self.z, indexing="ij")
        self.X, self.Y, self.Z = X, Y, Z
        self.r = np.hypot(X - ax["x"], Z - ax["z"])
        self.body = body_occupancy(body_half, self.x, self.y, self.z)

    def legal(self, y_disc_in: float, r_disc: float) -> np.ndarray:
        a = self.ax
        L = (self.r <= a["R"] - CYL_MARGIN_MM - self.h / 2) & (self.Z >= TRACK_MM + self.h / 2) \
            & (self.Y <= y_disc_in - self.h / 2)
        near_wheel = self.Y > a["y_in"] - CLAW_MM - 0.1                # the claw band and inside the rim
        L &= ~near_wheel | (self.r <= min(r_disc, a["R"] - CLAW_MM - 0.1) - self.h / 2)
        return L


def body_occupancy(body_half, x, y, z) -> np.ndarray:
    """Which grid cells (mm) are inside the body: the body's cross-section at each x, as (y, z) loops,
    point-in-polygon with even-odd holes. Light on memory (a mesh.contains() on ~300 k points took 10 GB)."""
    from matplotlib.path import Path as MPath
    Yg, Zg = np.meshgrid(y, z, indexing="ij")
    P = np.c_[Yg.ravel(), Zg.ravel()]
    occ = np.zeros((len(x), len(y), len(z)), bool)
    for i, xi in enumerate(x):
        sec = body_half.section(plane_origin=[xi / 1e3, 0, 0], plane_normal=[1, 0, 0])
        if sec is None:
            continue
        inside = np.zeros(len(P), bool)
        for loop in sec.discrete:
            yz = np.asarray(loop)[:, [1, 2]] * 1e3
            if len(yz) >= 3:
                inside ^= MPath(yz).contains_points(P)
        occ[i] = inside.reshape(Yg.shape)
    return occ


def ball(r_vox: float) -> np.ndarray:
    n = int(math.ceil(r_vox))
    g = np.mgrid[-n:n + 1, -n:n + 1, -n:n + 1]
    return (g ** 2).sum(0) <= r_vox ** 2 + 1e-9


def rules(G: AxleGrid, field: np.ndarray, fx: dict) -> tuple[np.ndarray, dict]:
    """Field -> kept voxels + what each rule did."""
    h = G.h
    L = G.legal(fx["y_disc_in"], fx["r_disc"])
    M = (field > 0) & L
    rep = {"asked_mm3": float(M.sum() * h ** 3)}
    # min wall: opening with a ball of diameter WALL_MM; the y = 0 face is a symmetry plane, so mirror first
    full = np.concatenate([M[:, ::-1], M], axis=1)
    full = ndimage.binary_opening(full, structure=ball(WALL_MM / 2 / h))
    M = full[:, M.shape[1]:] & L
    rep["after_wall_mm3"] = float(M.sum() * h ** 3)
    lab, n = ndimage.label(M)                                          # face connectivity (6-neighbour)
    at_centre = set(np.unique(lab[:, 0, :])) - {0}
    disc_face = G.Y >= fx["y_disc_in"] - 1.5 * h
    at_disc = set(np.unique(lab[disc_face & (G.r <= fx["r_disc"])])) - {0}
    at_body = set(np.unique(lab[ndimage.binary_dilation(G.body) & (lab > 0)])) - {0}
    keep = sorted(at_disc & (at_body | at_centre))                    # every piece carries load disc -> car
    M = np.isin(lab, keep)
    rep.update(pieces_found=int(n), pieces_kept=len(keep), kept_mm3=float(M.sum() * h ** 3))
    rep["refused"] = (None if keep and (set(keep) & at_centre) else
                      "no material reaches both the centre plane and the disc" if not (at_centre & at_disc) and not keep
                      else "not one part wheel to wheel (nothing kept reaches the centre plane)" if keep
                      else "no material reaches both the centre plane and the disc")
    contact = (M & ndimage.binary_dilation(G.body)).sum() * h ** 2
    rep["body_contact_mm2"] = float(contact)
    if keep and contact < MIN_BODY_CONTACT_MM2:
        rep["refused"] = f"glue contact with the body {contact:.1f} mm2 < {MIN_BODY_CONTACT_MM2}"
    rep["in_body_mm3"] = float((M & G.body).sum() * h ** 3)
    fp = M & disc_face & (G.r <= fx["r_disc"])
    xs = G.X[fp]
    rep["disc_footprint_w_mm"] = float(xs.max() - xs.min() + h) if xs.size else 0.0
    rep["disc_footprint_mm2"] = float(fp.any(axis=1).sum() * h ** 2)
    return M, rep


def loads(G: AxleGrid, M: np.ndarray, fx: dict) -> dict:
    """Beam-theory estimate along the axle (half part, cantilever from the centre plane)."""
    import beam_support as bsm
    h, a = G.h, G.ax
    Fr, Fa, E = bsm.LOAD_RADIAL_N, bsm.LOAD_AXIAL_N, bsm.ABS_E_MPA
    allow = bsm.ABS_STRENGTH_MPA / bsm.SAFETY
    sig, curv, ys = [], [], []
    for j, y in enumerate(G.y):
        if y > fx["y_disc_in"] - h / 2:                              # the last legal slice (rules() stops here)
            break
        s = M[:, j, :]
        A = s.sum() * h * h
        ys.append(y)
        if A <= 0:
            sig.append(np.inf); curv.append(np.inf); continue
        z = G.Z[:, j, :][s]
        zc = z.mean()
        I = ((z - zc) ** 2).sum() * h * h + s.sum() * h ** 4 / 12
        c = np.abs(z - zc).max() + h / 2
        Mo = Fr * (fx["y_bear"] - y) + Fa * a["R"]
        sig.append(Mo * c / I + Fa / A)
        curv.append(Mo / (E * I))
    ys, sig, curv = np.array(ys), np.array(sig), np.array(curv)
    if not np.isfinite(curv).all():
        return {"ok": False, "stress_mpa": float("inf"), "allow_mpa": allow, "why": "a slice with no material"}
    slope = np.concatenate([[0.0], np.cumsum(0.5 * (curv[1:] + curv[:-1]) * np.diff(ys))])
    defl = float(np.sum(0.5 * (slope[1:] + slope[:-1]) * np.diff(ys)))
    sag = defl + slope[-1] * (fx["y_bear"] - ys[-1]) + fx["stub_struct"]["sag_mm"]
    i = int(np.argmax(sig))
    out = {"stress_mpa": float(sig[i]), "at_y_mm": float(ys[i]), "allow_mpa": allow, "sag_mm": float(sag),
           "sag_max_mm": bsm.SAG_MAX_MM, "stub_stress_mpa": fx["stub_struct"]["stress_mpa"],
           "disc_stress_mpa": float(fx["disc_stress_mpa"])}
    out["ok"] = bool(sig.max() <= allow and sag <= bsm.SAG_MAX_MM and out["stub_stress_mpa"] <= allow
                     and out["disc_stress_mpa"] <= allow)
    return out


def build_axle(ax: dict, body_half, field_fn, h: float = 0.4) -> dict:
    """One axle: field -> rules -> loads -> meshes (right half, metres) + report."""
    import trimesh
    import cadio as CI
    G = AxleGrid(ax, body_half, h)
    fx = fixed_parts(ax, footprint_w_mm=10.0)
    field = field_fn(G, fx)
    M, rep = rules(G, field, fx)
    if rep["refused"]:
        return {"ok": False, "report": rep, "grid": G, "voxels": M}
    fx = fixed_parts(ax, footprint_w_mm=rep["disc_footprint_w_mm"])     # disc sized for its real footprint
    rep["loads"] = loads(G, M, fx)
    # fuse with the disc: the kept cells touching the disc face run on 2 cells into the (solid) disc, so the
    # smoothed surface overlaps it instead of stopping half a cell short
    Mm = M.copy()
    face = (G.Y >= fx["y_disc_in"] - 1.5 * h) & (G.Y < fx["y_disc_in"]) & M
    into = (G.Y >= fx["y_disc_in"] - h / 2) & (G.Y <= fx["y_disc_in"] + 2 * h) & (G.r <= fx["r_disc"] - h)
    Mm |= into & np.repeat(face.any(axis=1, keepdims=True), M.shape[1], axis=1)
    gen = _surface(G, Mm)
    parts = CI.to_manifold(gen) + CI.to_manifold(fx["disc"]) + CI.to_manifold(fx["stub"])
    lo = np.array([ax["x"] - 40, 0.0, -5.0]); hi = np.array([ax["x"] + 40, 80.0, 60.0])
    box = trimesh.creation.box(extents=hi - lo); box.apply_translation((lo + hi) / 2)
    half = CI.from_manifold(parts ^ CI.to_manifold(box))              # the right half, cut by a boolean
    half.apply_scale(1e-3)
    pieces = half.split(only_watertight=False)
    v = half.vertices * 1e3
    rr = np.hypot(v[:, 0] - ax["x"], v[:, 2] - ax["z"])
    claw = _claw_points(ax)
    blocked = int(half.contains(claw / 1e3).sum()) if half.is_watertight else -1
    gates = {"T3.7_clearance_mm": float(v[:, 2].min() - TRACK_MM),
             "T7.12.1_in_cylinder_mm": float(ax["R"] - rr.max()),
             "T7.13_claw_points_blocked": blocked,
             "one_piece": len(pieces) == 1, "watertight": bool(half.is_watertight),
             "disc_in_rim_mm": float(13.72 - 0.5 - fx["r_disc"])}
    ok = (gates["T3.7_clearance_mm"] >= -1e-6 and gates["T7.12.1_in_cylinder_mm"] >= -1e-6 and blocked == 0
          and gates["one_piece"] and gates["watertight"] and rep["loads"]["ok"])
    vol_full_mm3 = 2 * half.volume * 1e9
    rep.update(gates=gates, t_disc_mm=fx["t_disc"], r_disc_mm=fx["r_disc"],
               mass_g=float(vol_full_mm3 * ABS_G_CM3 * 1e-3),
               foam_displaced_g=float(2 * rep["in_body_mm3"] * FOAM_G_CM3 * 1e-3),
               com_mm=(half.center_mass * 1e3 * [1, 0, 1]).round(3).tolist())
    return {"ok": bool(ok), "report": rep, "half": half, "grid": G, "voxels": M, "fixed": fx}


def _surface(G: AxleGrid, M: np.ndarray):
    """Kept voxels -> closed full-width surface (mm), smoothed below the wall size."""
    import trimesh
    from skimage import measure
    h = G.h
    full = np.concatenate([M[:, ::-1], M], axis=1).astype(float)     # y columns: -y[-1] .. +y[-1]
    full = ndimage.gaussian_filter(np.pad(full, 2), 0.6)
    v, f, _, _ = measure.marching_cubes(full, 0.5)
    ny = M.shape[1]
    v = (v - 2.0)                                                     # index space of the unpadded grid
    xyz = np.c_[G.x[0] + v[:, 0] * h, (v[:, 1] - ny + 0.5) * h, G.z[0] + v[:, 2] * h]
    m = trimesh.Trimesh(xyz, f, process=True)
    if m.volume < 0:
        m.invert()
    return m


def _claw_points(ax: dict) -> np.ndarray:
    pts = []
    for yy in np.linspace(ax["y_in"] - CLAW_MM + 0.05, ax["y_in"] - 0.05, 4):
        for rr in np.linspace(ax["R"] - CLAW_MM + 0.05, ax["R"] - 0.05, 4):
            for t in np.linspace(0, 2 * math.pi, 36, endpoint=False):
                pts.append((ax["x"] + rr * math.cos(t), yy, ax["z"] + rr * math.sin(t)))
    p = np.array(pts)
    return p[p[:, 2] > 0.5]


# ------------------------------------------------------------------ test fields (fields, not shape parameters)
def f_envelope(G, fx):
    return np.ones(G.X.shape)


def f_random(seed: int, sigma_mm: float, fill: float):
    def fn(G, fx):
        rng = np.random.default_rng(seed)
        g = ndimage.gaussian_filter(rng.normal(size=G.X.shape), sigma_mm / G.h)
        return g - np.quantile(g, 1 - fill)
    return fn


def f_broken(G, fx):
    f = np.ones(G.X.shape)
    f[(G.Y > 4.0) & (G.Y < 6.5)] = -1.0                               # a cut right across: no load path
    return f


def load_flow(G, M, fx) -> np.ndarray:
    """How much of the wheel's load each voxel carries, as a flow problem (the electrical analogy for load
    paths): potential 1 where the material meets the disc, 0 where it meets the body or the centre plane,
    conduction through face-connected material. Returns |grad| per voxel (0 outside M)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve
    idx = -np.ones(M.shape, int)
    n = int(M.sum())
    idx[M] = np.arange(n)
    src = M & (G.Y >= fx["y_disc_in"] - 1.5 * G.h)
    snk = M & (ndimage.binary_dilation(G.body) | (np.arange(M.shape[1])[None, :, None] == 0))
    fixed = np.full(n, np.nan)
    fixed[idx[snk]] = 0.0
    fixed[idx[src]] = 1.0
    rows, cols = [], []
    for ax_ in range(3):
        a = np.moveaxis(idx, ax_, 0)
        i, j = a[:-1].ravel(), a[1:].ravel()
        k = (i >= 0) & (j >= 0)
        rows += [i[k], j[k]]; cols += [j[k], i[k]]
    r_, c_ = np.concatenate(rows), np.concatenate(cols)
    A = coo_matrix((np.ones(len(r_)), (r_, c_)), shape=(n, n)).tocsr()
    deg = np.asarray(A.sum(1)).ravel()
    free = np.isnan(fixed)
    L = (coo_matrix((deg, (np.arange(n), np.arange(n))), shape=(n, n)) - A).tocsr()
    phi = np.where(free, 0.0, np.nan_to_num(fixed))
    if free.any():
        rhs = -L[free][:, ~free] @ phi[~free]
        Lff = L[free][:, free] + 1e-9 * coo_matrix((np.ones(free.sum()), (np.arange(free.sum()),) * 2)).tocsr()
        phi[free] = spsolve(Lff.tocsc(), rhs)
    P = np.zeros(M.shape); P[M] = phi
    g = np.zeros(M.shape)
    for ax_ in range(3):
        d = np.diff(P, axis=ax_)
        both = np.diff(M.astype(int), axis=ax_) == 0
        d = np.where(both & np.take(M, range(M.shape[ax_] - 1), axis=ax_), d, 0.0)
        pad = [(0, 0)] * 3
        lo, hi = list(pad), list(pad)
        lo[ax_], hi[ax_] = (1, 0), (0, 1)
        g += 0.5 * (np.pad(d ** 2, lo) + np.pad(d ** 2, hi))
    return np.where(M, np.sqrt(g), 0.0)


def f_carved(G, fx, frac: float = 0.08, min_frac: float = 0.004, max_iter: int = 200):
    """Load-carved from the full envelope: repeatedly remove the material that carries the least of the
    wheel's load (load_flow), keeping the rules and the load estimate. A step that fails is undone and retried
    with half the step; it ends when even a tiny step fails. Nothing is drawn: the shape is what the load
    path leaves."""
    M, rep = rules(G, np.ones(G.X.shape), fx)
    best = M.copy()
    for _ in range(max_iter):
        flow = load_flow(G, best, fx)
        cut = np.quantile(flow[best], frac)
        M, rep = rules(G, np.where(best & (flow > cut), 1.0, -1.0), fx)
        if rep["refused"] or not loads(G, M, fx)["ok"]:
            frac /= 2
            if frac < min_frac:
                break
            continue
        best = M
    return np.where(best, 1.0, -1.0)


DEMO = {"envelope": f_envelope, "carved": f_carved,
        "random_a": f_random(1, 2.0, 0.55), "random_b": f_random(2, 3.0, 0.45), "random_c": f_random(3, 1.5, 0.6),
        "broken": f_broken}


# ------------------------------------------------------------------ car folder, render
def wheels_of(folder: Path) -> dict:
    import trimesh
    out = {}
    for tag, name in (("front", "wheelF"), ("rear", "wheelR")):
        b = trimesh.load(folder / f"{name}.stl").bounds * 1e3
        out[tag] = {"tag": tag, "x": float(b[:, 0].mean()), "y_in": float(b[0, 1]), "w": float(b[1, 1] - b[0, 1]),
                    "R": float((b[1, 0] - b[0, 0]) / 2), "z": float(b[:, 2].mean())}
    return out


def build_car(folder: Path, field_fns: dict, out: Path, h: float = 0.4) -> dict:
    """Both axles with the given field functions -> car folder with supports + report."""
    import trimesh
    import supports as SUP
    folder, out = Path(folder), Path(out)
    body = trimesh.load(folder / "car_half.stl", force="mesh")
    res = {tag: build_axle(ax, body, field_fns[tag], h) for tag, ax in wheels_of(folder).items()}
    rep = {tag: r["report"] for tag, r in res.items()}
    ok = all(r["ok"] for r in res.values())
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(folder, out, ignore=shutil.ignore_patterns("_body_half.stl"))
    if all("half" in r for r in res.values()):
        sup = trimesh.util.concatenate([res["front"]["half"], res["rear"]["half"]])
        SUP._write_ascii(sup, out / "supports.stl", "supports")
        a = json.loads((out / "assembly.json").read_text())
        a["extra_surfaces"] = [e for e in a["extra_surfaces"] if e["name"] != "supports"] + \
                              [{"name": "supports", "stl": "supports.stl", "rotating": None}]
        a["supports"] = "generated"
        (out / "assembly.json").write_text(json.dumps(a, indent=1))
        m = sum(r["report"]["mass_g"] for r in res.values())
        fd = sum(r["report"]["foam_displaced_g"] for r in res.values())
        rep["mass"] = {"supports_g": m, "foam_displaced_g": fd,
                       "car_mass_change_g": m - fd - TEAM_SUPPORTS_G,
                       "note": "change against geometry.Car's assumption (team supports 5.88 g inside other_parts_g)"}
    rep["ok"] = ok
    (out / "supports_gen.json").write_text(json.dumps(rep, indent=1, default=float))
    return {"ok": ok, "report": rep, "res": res, "body": body}


def render(car: dict, png: Path, title: str):
    """Close-ups of both axles: from below, front, rear and side, plus an x-section through each axle."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import trimesh
    import render as RD
    body = car["body"].copy(); body.apply_scale(1e3)
    fig = plt.figure(figsize=(16, 8.6))
    views = (("below", -65, -90), ("front 3/4", 15, -150), ("rear 3/4", 15, -30), ("side", 0, -90))
    for row, tag in enumerate(("front", "rear")):
        r = car["res"][tag]
        ax = r["grid"].ax
        lo = np.array([ax["x"] - 17, 0.0, 0.0]); hi = np.array([ax["x"] + 17, ax["y_in"] + ax["w"] + 1, 32.0])
        bclip = _clip(body, lo, hi)
        wheel = trimesh.creation.cylinder(radius=ax["R"], height=ax["w"], sections=72)
        wheel.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
        wheel.apply_translation([ax["x"], ax["y_in"] + ax["w"] / 2, ax["z"]])
        for col, (name, elev, azim) in enumerate(views):
            a3 = fig.add_subplot(2, 5, row * 5 + col + 1, projection="3d")
            if bclip is not None:
                RD.mesh(a3, bclip, "#c8a878", alpha=0.35)
            RD.mesh(a3, wheel, "#3a6ea5", alpha=0.12)
            if "half" in r:
                s = r["half"].copy(); s.apply_scale(1e3)
                RD.mesh(a3, s, "#909090")
            else:
                RD.surf(a3, r["voxels"], (r["grid"].x[0], r["grid"].y[0], r["grid"].z[0]), r["grid"].h, "#d04040")
            a3.set_xlim(lo[0], hi[0]); a3.set_ylim(0, hi[1]); a3.set_zlim(0, 32)
            a3.set_box_aspect((hi[0] - lo[0], hi[1], 32)); a3.view_init(elev, azim); a3.set_axis_off()
            a3.set_title(f"{tag}: {name}", fontsize=8)
        a2 = fig.add_subplot(2, 5, row * 5 + 5)
        G = r["grid"]; i = int(np.argmin(np.abs(G.x - ax["x"])))
        img = np.where(r["voxels"][i].T, 2, 0) + np.where(G.body[i].T, 1, 0)
        a2.imshow(img, origin="lower", extent=(0, G.y[-1], 0, G.z[-1]), cmap="Greys", vmin=0, vmax=3, aspect="equal")
        a2.add_patch(matplotlib.patches.Rectangle((ax["y_in"], ax["z"] - ax["R"]), ax["w"], 2 * ax["R"],
                                                  fill=False, ec="#3a6ea5", lw=0.8))
        a2.set_title(f"{tag}: section at the axle (y, z)\nlight = body, dark = support in air, black = support in body", fontsize=7)
        a2.set_xlabel("y mm", fontsize=7); a2.tick_params(labelsize=6)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(png, dpi=110)
    plt.close(fig)


def _clip(m, lo, hi):
    import trimesh
    try:
        b = trimesh.creation.box(extents=hi - lo)
        b.apply_translation((lo + hi) / 2)
        import cadio as CI
        return CI.from_manifold(CI.to_manifold(m) ^ CI.to_manifold(b))
    except Exception:
        return None


def demo(folder: Path, out: Path, h: float, only: list | None = None):
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name, fn in DEMO.items():
        if only and name not in only:
            continue
        car = build_car(folder, {"front": fn, "rear": fn}, out / name / "car", h)
        render(car, out / f"{name}.png", f"{name}: {'BUILT' if car['ok'] else 'REFUSED / FAILED'}")
        rep = car["report"]
        summary[name] = {"ok": car["ok"], "mass": rep.get("mass"),
                         **{t: {k: rep[t].get(k) for k in ("refused", "kept_mm3", "body_contact_mm2", "in_body_mm3",
                                                            "disc_footprint_w_mm", "t_disc_mm", "mass_g", "gates", "loads")}
                            for t in ("front", "rear")}}
        print(name, json.dumps(summary[name], default=float)[:900], flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["demo"])
    ap.add_argument("folder")
    ap.add_argument("--h", type=float, default=0.4)
    ap.add_argument("--out", default=str(HERE / "runs" / "support_gen"))
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    demo(Path(a.folder), Path(a.out), a.h, a.only)
