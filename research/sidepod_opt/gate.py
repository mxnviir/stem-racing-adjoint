"""Adjoint accuracy test on the trial car (Part 3's known-answer marks: sign >= 9/10, r >= 0.9).

    python gate.py base   [np]            plain medium solve of the original, run dir kept = state A
    python gate.py bumps                  write the bump STLs (exact mesh, Gaussian normal moves)
    python gate.py bump <k> [np]          time bump k on the state-A mesh reshaped onto it (morph path)
    python gate.py adjoint [np]           ESI adjoint on the original: per-vertex dD/dn
    python gate.py variant <name> <site> <mm>  extra bump folder at another height (null, pairs)
    python gate.py judge                  measured vs predicted drag change per bump

Drag only (half car, N): race time and mass are left out on purpose. Every result goes to
gate/results/*.json. A bump whose run fell back to a fresh mesh (MORPH_FALLBACK) is not used.
"""
import json, os, shutil, sys, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
P2 = HERE.parents[1] / "part2-simulation"
sys.path.insert(0, str(P2)); sys.path.insert(0, str(HERE))
G = HERE / "gate"
R = Path(os.environ.get("GATE_RESULTS", HERE / "gate_results")); R.mkdir(parents=True, exist_ok=True)   # tracked in git
ADJ = HERE / "gate_results"       # the adjoint was solved here (one machine); other machines judge against it
ORIG0 = G / "original"            # exact CAD export (state A is solved on this)
ORIG = G / "original_rm"          # the same surface re-meshed to even 1 mm triangles: zero run, bumps, adjoint
DOMAIN = ((-0.005, 0.0, 0.0), (0.265, 0.045, 0.066))      # fixed for every car (trial car is 257 mm)
# GATE_RES=coarse runs the same test on Part 2's coarse mesh (with GATE_RESULTS pointing elsewhere), e.g.
# for the DAFoam test, whose adjoint memory (>150 kB/cell) does not fit the medium mesh on 16 GB
RES = os.environ.get("GATE_RES", "medium")
ITERS_BASE, ITERS = int(os.environ.get("GATE_ITERS_BASE", 2000)), int(os.environ.get("GATE_ITERS", 1000))
REF_A = Path(os.environ["GATE_REF"]) if os.environ.get("GATE_REF") else G / ("refA" if RES == "medium" else f"refA_{RES}")
BUMP_R_M, BUMP_A_M = 0.010, 0.001                           # Part 3: 10 mm radius, 1 mm height
BUMP_R_M = float(os.environ.get("GATE_BUMP_R_MM", BUMP_R_M * 1e3)) * 1e-3   # RESOLVED_TEST.md rule 4 may widen it
# centres in the car frame (m): x from the nose, z up; y on the +y side. Front/attached vs rear/wake.
CENTRES = {"nose_top": (0.030, 0.000, 0.022), "nose_side": (0.040, 0.008, 0.019),
           "pod_front": (0.085, 0.030, 0.012), "pod_front_low": (0.095, 0.022, 0.004),
           "pod_rear": (0.160, 0.030, 0.012), "pod_rear_low": (0.165, 0.022, 0.004),
           "pod_rear_top": (0.150, 0.025, 0.026), "tail_side": (0.215, 0.010, 0.030)}


def kw(extra=None):
    import stopwatch as SW
    # GATE_DOMAIN_DX_MM: shift the whole meshing frame along x (same car STL, same domain size): the
    # background grid and octree cut the SAME geometry differently. This is the clean repeat mesh; nudging the
    # design field instead also moves parts of the surface by 0.2-1.5 mm (ROUTES.md 2026-11-21 16:05).
    dx = float(os.environ.get("GATE_DOMAIN_DX_MM", "0")) * 1e-3
    dom = ((DOMAIN[0][0] + dx,) + tuple(DOMAIN[0][1:]), (DOMAIN[1][0] + dx,) + tuple(DOMAIN[1][1:]))
    k = dict(SW.SEARCH, domain_reference_bounds=dom, resolution=RES)
    if os.environ.get("GATE_TIMEOUT"):                     # seconds per OpenFOAM stage (fine/resolved meshes)
        k["stage_timeout_s"] = int(os.environ["GATE_TIMEOUT"])
    if os.environ.get("GATE_WALL_RESOLVED") == "1":        # wall-resolved layer stack on any resolution
        k["wall_resolved"] = True
    if os.environ.get("GATE_PLUS_SURFACES"):               # e.g. "supports": those extra surfaces refined to
        k["plus_surfaces"] = tuple(os.environ["GATE_PLUS_SURFACES"].split(","))   # level (5 5) on any mesh
    k.update(extra or {})
    # Part 2's SEARCH mesh switches wall layers off (layer_overrides nSurfaceLayers 0), and
    # resolved_layer_controls applies layer_overrides too: a "resolved" run would get NO layer stack
    # (found 2026-11-21 by the bccheck). Wall-resolved runs keep Part 2's own y+ <= 2 stack.
    if k.get("resolution") == "resolved" or k.get("wall_resolved"):
        k.pop("layer_overrides", None)
    return k


def solve(folder, n_sub, iters, extra=None, keep=False):
    import stopwatch as SW
    from cfd_wrapper import run_half_car_cfd
    body = SW.body_stl(folder / "car_half.stl", folder / "_body_half.stl")
    k = kw(extra); k["max_iterations"] = iters
    t = time.time()
    half, health = run_half_car_cfd(str(body), n_subdomains=n_sub, extra_surfaces=SW.extra_surfaces(folder),
                                    keep_run_dir=keep, **k)
    return half, health, time.time() - t


def rec(half, health, secs, **more):
    d = {"D20_half_N": float(half.D20), "wall_s": round(secs, 1),
         "converged": bool(health.converged), "residual_p": health.residual_final,
         "force_osc": health.force_oscillation, "force_drift": getattr(health, "force_drift", None),
         "run_dir": str(getattr(health, "run_dir", "") or ""),
         "force_mean_stderr": getattr(health, "force_mean_stderr", None)}
    d.update(more)
    return d


def cmd_base(n_sub):
    half, health, secs = solve(ORIG0, n_sub, ITERS_BASE, keep=True)
    run = latest_run_of(os.getpid())
    keep = REF_A                                              # state A lives outside Part 2's runs folder
    if run:
        if keep.exists():
            shutil.rmtree(keep)
        shutil.copytree(run, keep, ignore=shutil.ignore_patterns("processor*"))
    d = rec(half, health, secs, run_dir_kept=str(keep) if run else None,
            full_D20_N=float(half.to_full_car().D20), full_L20_N=float(half.to_full_car().L))
    (R / "base.json").write_text(json.dumps(d, indent=1, default=float))
    print(json.dumps(d, default=float)[:600], flush=True)


def ref_dir():
    """State A: the kept run folder of the base solve."""
    return json.loads((R / "base.json").read_text())["run_dir_kept"]


def bump_field(mesh, centre, r=BUMP_R_M, a=BUMP_A_M):
    """Outward normal move (m) per vertex: a Gaussian bump centred on the surface point nearest
    `centre`, faded to zero on the closed symmetry face (y = 0) so that face stays flat."""
    v, n = mesh.vertices, mesh.vertex_normals
    c = v[np.argmin(np.linalg.norm(v - np.asarray(centre), axis=1))]
    d2 = ((v - c) ** 2).sum(1)
    w = a * np.exp(-d2 / r ** 2)
    on_plane = (np.abs(v[:, 1]) < 1e-7) & (n[:, 1] < -0.9)
    w[on_plane] = 0.0
    w *= np.clip(v[:, 1] / 0.002, 0.0, 1.0) ** 2 if c[1] > 0.004 else 1.0
    return w, c


def cmd_remesh(target_m=1.0e-3):
    """Even ~1 mm triangles (the CAD has 150 mm ones on flat faces): a 10 mm bump and a per-vertex
    sensitivity both need them. Sharp edges kept (30 deg), surface held within 20 um."""
    import pymeshlab as ml
    import trimesh
    import cadio as CI
    m = trimesh.load(ORIG0 / "car_half.stl")
    if (ADJ / "adjoint_faces.npy").exists():
        # the exact surface the adjoint was solved on (any machine): judge then needs no mapping
        t = trimesh.Trimesh(np.load(ADJ / "adjoint_verts.npy"), np.load(ADJ / "adjoint_faces.npy"), process=False)
    else:
        ms = ml.MeshSet(); ms.add_mesh(ml.Mesh(m.vertices, m.faces))
        ms.meshing_isotropic_explicit_remeshing(iterations=6, targetlen=ml.PureValue(target_m), featuredeg=30.0,
                                                checksurfdist=True, maxsurfdist=ml.PureValue(2e-5))
        r = ms.current_mesh()
        t = trimesh.Trimesh(r.vertex_matrix(), r.face_matrix())
    if ORIG.exists():
        shutil.rmtree(ORIG)
    shutil.copytree(ORIG0, ORIG, ignore=shutil.ignore_patterns("_body_half.stl", "car_half.stl"))
    CI.write_ascii_named(t, ORIG / "car_half.stl", "car", m.volume, 0.002)
    print("remeshed", len(t.vertices), "vertices, volume error", (t.volume - m.volume) / m.volume, flush=True)


def cmd_bumps():
    import trimesh
    import cadio as CI
    if not ORIG.exists():
        cmd_remesh()
    base = trimesh.load(ORIG / "car_half.stl")
    out = {}
    for k, cen in CENTRES.items():
        w, c = bump_field(base, cen)
        m = base.copy()
        nv = base.vertices + base.vertex_normals * w[:, None]
        nv[np.abs(base.vertices[:, 1]) < 1e-9, 1] = 0.0        # the symmetry face stays exactly at y = 0
        m.vertices = nv
        dv_expect = float((w[m.faces].mean(1) * base.area_faces).sum())
        dv = m.volume - base.volume
        folder = G / f"bump_{k}"
        if folder.exists():
            shutil.rmtree(folder)
        shutil.copytree(ORIG, folder, ignore=shutil.ignore_patterns("_body_half.stl"))
        CI.write_ascii_named(m, folder / "car_half.stl", "car", base.volume + dv, 0.01)
        np.save(folder / "move_m.npy", w)
        out[k] = {"centre_on_surface_m": c.tolist(), "dV_mm3": dv * 1e9, "dV_expected_mm3": dv_expect * 1e9,
                  "moved_vertices": int((w > 1e-6).sum()), "max_move_mm": float(w.max() * 1e3)}
        print(k, json.dumps(out[k]), flush=True)
    (R / "bumps.json").write_text(json.dumps(out, indent=1))


def cmd_variant(name, centre_key, amp_mm):
    """An extra bump folder: a CENTRES site at another height (negative = dent). For the noise
    floor (tiny height), linearity and +/- pairs."""
    import trimesh
    import cadio as CI
    base = trimesh.load(ORIG / "car_half.stl")
    w, c = bump_field(base, CENTRES[centre_key], a=float(amp_mm) * 1e-3)
    m = base.copy()
    nv = base.vertices + base.vertex_normals * w[:, None]
    nv[np.abs(base.vertices[:, 1]) < 1e-9, 1] = 0.0
    m.vertices = nv
    folder = G / f"bump_{name}"
    if folder.exists():
        shutil.rmtree(folder)
    shutil.copytree(ORIG, folder, ignore=shutil.ignore_patterns("_body_half.stl"))
    CI.write_ascii_named(m, folder / "car_half.stl", "car", m.volume, 0.01)
    np.save(folder / "move_m.npy", w)
    meta = json.loads((R / "bumps.json").read_text())
    meta[name] = {"site": centre_key, "amp_mm": float(amp_mm), "dV_mm3": (m.volume - base.volume) * 1e9}
    (R / "bumps.json").write_text(json.dumps(meta, indent=1))
    print(name, meta[name], flush=True)


def region_mask(v_m):
    """Car-frame points (m) inside the sidepod design region (geometry.Car's region: the box
    minus the T7.9.2/T7.9.3 wheel clearances, the halo zone and the spine), 1.0/0.0."""
    from geometry import CarSpec
    s = CarSpec()
    X = s.x_nose_mm - v_m[:, 0] * 1e3; AY = np.abs(v_m[:, 1]) * 1e3; Z = v_m[:, 2] * 1e3   # STEP frame
    box = ((X >= s.region_x[0]) & (X <= s.region_x[1]) & (AY <= s.region_ymax)
           & (Z >= s.region_z[0]) & (Z <= s.region_z[1]))
    dy = np.clip(AY - s.front_inner_y, 0, None)
    t792 = ((AY >= s.front_inner_y) & (X <= s.x_front_axle)
            & (X >= s.x_front_axle - s.r_wheel - (15.0 + dy / np.tan(np.radians(60)))))
    dy = np.clip(AY - s.rear_inner_y, 0, None)
    t793 = (AY >= s.rear_inner_y) & (X >= s.x_rear_axle) & (X <= s.x_rear_axle + s.r_wheel + 5.0 + dy)
    halo = (X >= s.halo_x0) & (Z > s.halo_zmin)
    spine = (AY <= s.spine_y) & (Z >= s.spine_z)
    return (box & ~(t792 | t793 | halo) & ~spine).astype(float)


def smooth_on_surface(v, f, area, sigma):
    """Area-weighted Gaussian average of a per-vertex field over vertices within 2.5 sigma."""
    from scipy.spatial import cKDTree
    T = cKDTree(v)
    out = np.empty(len(v))
    for k, i in enumerate(T.query_ball_point(v, 2.5 * sigma)):
        i = np.asarray(i)
        w = np.exp(-((v[i] - v[k]) ** 2).sum(1) / sigma ** 2) * area[i]
        out[k] = (w * f[i]).sum() / w.sum()
    return out


GRAD_SIGMA_M, GRAD_CLIP_PCT = 0.010, 98.0


def grad_field(base):
    """The adjoint's own steepest-ascent direction, made morphable: g clipped at the 98th
    percentile of |g| (the top values are edge/corner singularities: one vertical edge at
    x = 87.5 mm and the centreline at x = 67 mm carry g ~ 5e4 against a 95th percentile of 2.3e3),
    restricted to the sidepod region, smoothed over 10 mm, faded to zero at the region edge and
    on the symmetry face. Unit max. A move a*d gives a predicted change a * rho * sum(g d A)."""
    g, area = adjoint_on_base(base)
    v = base.vertices
    c = np.percentile(np.abs(g), GRAD_CLIP_PCT)
    mask = region_mask(v)
    d = smooth_on_surface(v, np.clip(g, -c, c) * mask, area, GRAD_SIGMA_M)
    d *= smooth_on_surface(v, mask, area, 0.003) * np.clip(v[:, 1] / 0.002, 0.0, 1.0) ** 2
    d /= np.abs(d).max()
    spikes = np.abs(g) > np.percentile(np.abs(g), 99.0)
    from scipy.spatial import cKDTree
    near = cKDTree(v[spikes]).query(v)[0] < 0.003
    contrib = g * d * area
    info = {"pred_mN_per_mm": float(1.225 * contrib.sum()) * 1e3 * 1e-3,
            "share_within_3mm_of_top1pct_g": float(contrib[near].sum() / contrib.sum()),
            "moved_vertices_over_10pct": int((np.abs(d) > 0.1).sum()),
            "clip": float(c), "sigma_mm": GRAD_SIGMA_M * 1e3}
    return d, info


def cmd_gradvariant(name, amp_mm):
    """A move along the adjoint's own gradient direction (grad_field), amp_mm at its peak
    (negative = against it). Run as a +/- pair: one directional check of size, not a
    replacement for the scatter test."""
    import trimesh
    import cadio as CI
    base = trimesh.load(ORIG / "car_half.stl")
    d, info = grad_field(base)
    w = d * float(amp_mm) * 1e-3
    m = base.copy()
    nv = base.vertices + base.vertex_normals * w[:, None]
    nv[np.abs(base.vertices[:, 1]) < 1e-9, 1] = 0.0
    m.vertices = nv
    folder = G / f"bump_{name}"
    if folder.exists():
        shutil.rmtree(folder)
    shutil.copytree(ORIG, folder, ignore=shutil.ignore_patterns("_body_half.stl"))
    CI.write_ascii_named(m, folder / "car_half.stl", "car", m.volume, 0.01)
    np.save(folder / "move_m.npy", w)
    meta = json.loads((R / "bumps.json").read_text())
    meta[name] = {"site": "adjoint_gradient", "amp_mm": float(amp_mm), "dV_mm3": (m.volume - base.volume) * 1e9, **info}
    (R / "bumps.json").write_text(json.dumps(meta, indent=1))
    print(name, meta[name], flush=True)


def cmd_bump(k, n_sub):
    if k == "adjoint_matched":          # lets the lane queue (gate/queue.txt) run the matched adjoint
        return cmd_adjoint(n_sub, matched=True)
    ref = ref_dir()
    folder = G / f"bump_{k}"
    morph_ref_rm()
    half, health, secs = solve(folder, n_sub, ITERS, extra={"morph_from": ref, "warm_from": ref}, keep=True)
    run = latest_run_of(os.getpid())
    fell_back = bool(run and (Path(run) / "MORPH_FALLBACK").exists())
    d = rec(half, health, secs, bump=k, morph_fallback=fell_back, run_dir_kept=run)
    (R / f"bump_{k}.json").write_text(json.dumps(d, indent=1, default=float))
    save_forces(run, f"bump_{k}")
    if run and not fell_back and os.environ.get("GATE_KEEP_RUN") != "1":   # GATE_KEEP_RUN=1: kept (e.g. an adjoint follows)
        shutil.rmtree(run, ignore_errors=True)             # keep the disk; the numbers are saved
    print(json.dumps(d, default=float), flush=True)


def morph_ref_rm():
    """GATE_MORPH_REF_RM=1: morph from ORIG's surface (the bumps' own base) instead of the one state A was
    snapped to. The two differ by up to 0.2 mm near edges, which inverted 15 um wall-layer cells."""
    if os.environ.get("GATE_MORPH_REF_RM") == "1":
        import stopwatch as SW
        os.environ["P2_MORPH_REF_STL"] = str(SW.body_stl(ORIG / "car_half.stl", ORIG / "_body_half.stl"))


def cmd_reference_repeat(n_sub):
    """The ORIGINAL on the morph path from state A: the zero of every bump difference (and a noise point)."""
    ref = ref_dir()
    morph_ref_rm()
    half, health, secs = solve(ORIG, n_sub, ITERS, extra={"morph_from": ref, "warm_from": ref}, keep=True)
    run = latest_run_of(os.getpid())
    d = rec(half, health, secs, morph_fallback=bool(run and (Path(run) / "MORPH_FALLBACK").exists()), run_dir_kept=run)
    (R / "zero.json").write_text(json.dumps(d, indent=1, default=float))
    save_forces(run, "zero")
    if run:
        shutil.rmtree(run, ignore_errors=True)
    print(json.dumps(d, default=float), flush=True)


def cmd_adjoint(n_sub, matched=False):
    """matched: the adjoint on the SAME mesh and primal as the bumps (SW.SEARCH: no wall layers;
    primal as long as state A's), run folder kept in gate/adjoint_matched. The first adjoint
    (tag "") ran with OpenFOAM's default 3 wall layers and a 1000-iteration primal: a different
    flow from the one every bump measures."""
    import openfoam_adjoint as OA
    import stopwatch as SW
    import trimesh
    tag = "_matched" if matched else ""
    body = SW.body_stl(ORIG / "car_half.stl", ORIG / "_body_half.stl")
    more = dict(layer_overrides=SW.SEARCH["layer_overrides"], primal_iters=ITERS_BASE, keep_run_dir=True) if matched else {}
    cfg = OA.AdjointRunConfig(resolution=RES, n_subdomains=n_sub, extra_surfaces=SW.extra_surfaces(ORIG),
                              domain_reference_bounds=DOMAIN, **more)
    t = time.time()
    s = OA.invoke_adjoint(str(body), str(P2 / "cfd_case_template"), cfg)      # kinematic dD_half/dn per corner
    v = trimesh.load(body).vertices
    np.save(R / f"adjoint_sens{tag}.npy", np.asarray(s)); np.save(R / f"adjoint_verts{tag}.npy", v)
    info = {"wall_s": round(time.time() - t, 1), "n": int(len(s)), "rho": 1.225, **{k: v_ for k, v_ in more.items()}}
    if matched:
        runs = sorted((P2 / "cfd_case_template" / "adjoint_runs").iterdir(), key=lambda q: q.stat().st_mtime)
        keep = G / "adjoint_matched"
        if keep.exists():
            shutil.rmtree(keep)
        shutil.copytree(runs[-1], keep, ignore=shutil.ignore_patterns("processor*"))
        info["run_dir_kept"] = str(keep)
        save_forces(str(keep), "adjoint_matched_primal")
    (R / f"adjoint{tag}.json").write_text(json.dumps(info, indent=1, default=str))
    print("adjoint done", tag, len(s), round(time.time() - t), "s", flush=True)


def save_forces(run, name):
    """The force histories of a run (D20 is the mean of the last 20 % of forces/0/force.dat),
    kept so each number's own error bar can be recomputed after the run folder is deleted."""
    if not run:
        return
    o = R / "forces" / name
    o.mkdir(parents=True, exist_ok=True)
    for f in ("forces", "forces_car"):
        src = Path(run) / "postProcessing" / f / "0" / "force.dat"
        if src.exists():
            shutil.copy(src, o / f"{f}.dat")


def latest_run_of(pid):
    runs = sorted((P2 / "cfd_case_template/runs").glob(f"run_{pid}_*"), key=lambda p: p.stat().st_mtime)
    return str(runs[-1]) if runs else None


def adjoint_on_base(base, tag=""):
    """The adjoint as saved is one value per STL triangle CORNER, each the value of the nearest
    CFD surface point (openfoam_adjoint.map_sensitivity_to_stl_vertices): kinematic dD_half/dn per
    unit AREA (ESI default, includeSurfaceArea false, as Part 3's known-answer check reads it).
    Per vertex: the mean of its corners (g) and its area (1/3 of its faces). On another machine
    whose re-meshed original differs, g is taken from the nearest vertex of the adjoint's mesh
    (adjoint_g.npy + adjoint_verts.npy)."""
    s = np.load(ADJ / f"adjoint_sens{tag}.npy")
    vid = base.faces.reshape(-1)
    area = np.bincount(vid, weights=np.repeat(base.area_faces / 3, 3), minlength=len(base.vertices))
    if len(base.faces) * 3 == len(s) and np.allclose(base.vertices, np.load(ADJ / f"adjoint_verts{tag}.npy")):
        g = np.bincount(vid, weights=s, minlength=len(base.vertices)) / np.bincount(vid, minlength=len(base.vertices))
        if not (ADJ / f"adjoint_g{tag}.npy").exists():
            np.save(ADJ / f"adjoint_g{tag}.npy", g)
        return g, area
    from scipy.spatial import cKDTree
    V = np.load(ADJ / f"adjoint_verts{tag}.npy")
    d, i = cKDTree(V).query(base.vertices)
    if np.median(d) > 2e-4:
        raise SystemExit(f"this original differs from the adjoint's (median {np.median(d)*1e3:.2f} mm)")
    return np.load(ADJ / f"adjoint_g{tag}.npy")[i], area


def run_stderr_mN(name, rec_):
    """Standard error of a run's D20 (mean of the last 20 %, autocorrelation-corrected, Part 2's
    force_mean_convergence) in mN: from the json if recorded, else from its saved force history."""
    if rec_.get("force_mean_stderr") is not None:
        return float(rec_["force_mean_stderr"]) * rec_["D20_half_N"] * 1e3
    from openfoam_case import force_mean_convergence
    f = R / "forces" / name / "forces.dat"
    if not f.exists():
        for jt in (G / "forces_live").glob("run_*/job.txt"):   # saved live by gate_forcesaver.sh
            if jt.read_text().split()[-1:] == [name[5:]] and (jt.parent / "forces.dat").exists():
                f.parent.mkdir(parents=True, exist_ok=True)
                for x in ("forces.dat", "forces_car.dat"):
                    if (jt.parent / x).exists():
                        shutil.copy(jt.parent / x, f.parent / x)
    if not f.exists():
        return None
    return float(force_mean_convergence(f.read_text())[0]) * rec_["D20_half_N"] * 1e3


def cmd_judge():
    """Measured dD (bump - zero, morph path) vs adjoint prediction rho * sum(g dn A).
    Three readings, because one zero run shifts every row by the same unknown amount:
      rows      each bump minus the zero run (r is immune to the shared offset; signs, slope are not)
      pairs     (D+ - D-)/2 for +/- pairs at one site: no zero needed
      noise     null - zero (a second zero sample) and each run's own standard error"""
    import trimesh
    zrec = json.loads((R / "zero.json").read_text())
    zero = zrec["D20_half_N"]
    base_run = json.loads((R / "base.json").read_text())["D20_half_N"]
    meta = json.loads((R / "bumps.json").read_text())
    base = trimesh.load(ORIG / "car_half.stl")
    g, area = adjoint_on_base(base)
    gm = adjoint_on_base(base, "_matched")[0] if (ADJ / "adjoint_sens_matched.npy").exists() else None
    rows, by = [], {}
    for p in sorted(R.glob("bump_*.json")):
        k = p.stem[5:]
        b = json.loads(p.read_text())
        dn = ((trimesh.load(G / f"bump_{k}" / "car_half.stl").vertices - base.vertices) * base.vertex_normals).sum(1)
        site = meta.get(k, {}).get("site", k); amp = meta.get(k, {}).get("amp_mm", 1.0)
        r = {"bump": k, "site": site, "amp_mm": amp, "measured_mN": (b["D20_half_N"] - zero) * 1e3,
             "predicted_mN": float(1.225 * (g * dn * area).sum()) * 1e3,
             **({"predicted_matched_mN": float(1.225 * (gm * dn * area).sum()) * 1e3} if gm is not None else {}),
             "stderr_mN": run_stderr_mN(f"bump_{k}", b), "dV_mm3": float((dn * area).sum() * 1e9),
             "usable": bool(not b["morph_fallback"] and b["converged"]),
             "_D": b["D20_half_N"] * 1e3}
        rows.append(r)
        by[k] = r
    out = {"zero_minus_base_mN (fresh mesh vs morph path)": (zero - base_run) * 1e3,
           "zero_stderr_mN": run_stderr_mN("zero", zrec)}
    nulls = [r for r in rows if r["usable"] and abs(r["predicted_mN"]) < 0.01 and abs(r["amp_mm"]) < 0.1]
    if nulls:
        out["null_minus_zero_mN (second zero sample)"] = {r["bump"]: r["measured_mN"] for r in nulls}
    pairs = []
    sites = {}
    for r in rows:
        if r["usable"] and r not in nulls:
            sites.setdefault(r["site"], []).append(r)
    for site, rs in sites.items():
        for rp in [x for x in rs if x["amp_mm"] > 0]:
            for rm in [x for x in rs if x["amp_mm"] < 0 and abs(abs(x["amp_mm"]) - rp["amp_mm"]) < 1e-9]:
                se = [x["stderr_mN"] for x in (rp, rm)]
                pairs.append({"site": site, "amp_mm": rp["amp_mm"], "plus": rp["bump"], "minus": rm["bump"],
                              "half_diff_measured_mN": (rp["_D"] - rm["_D"]) / 2,
                              "half_diff_predicted_mN": (rp["predicted_mN"] - rm["predicted_mN"]) / 2,
                              **({"half_diff_predicted_matched_mN": (rp["predicted_matched_mN"] - rm["predicted_matched_mN"]) / 2}
                                 if gm is not None else {}),
                              "half_diff_stderr_mN": 0.5 * np.hypot(*[x if x is not None else 0.2 for x in se]),
                              "stderr_assumed_0.2mN_for": [x["bump"] for x in (rp, rm) if x["stderr_mN"] is None],
                              "sum_minus_2zero_mN (curvature + zero offset)": rp["measured_mN"] + rm["measured_mN"]})
    out["pairs"] = pairs
    for r in rows:
        r.pop("_D")
    out["rows"] = rows
    use = [r for r in rows if r["usable"] and r not in nulls]
    if len(use) >= 3:
        m = np.array([r["measured_mN"] for r in use])
        for key, lab in (("predicted_mN", ""), ("predicted_matched_mN", "matched_")):
            if key not in use[0]:
                continue
            pr = np.array([r[key] for r in use])
            rr = float(np.corrcoef(m, pr)[0, 1]); sg = (np.sign(m) == np.sign(pr))
            out[lab + "map"] = dict(pearson_r=rr, signs=f"{int(sg.sum())}/{len(use)}",
                                    slope_measured_per_predicted=float((m @ pr) / (pr @ pr)),
                                    passed_part3_marks=bool(rr >= 0.9 and sg.mean() >= 0.9))
        out["note"] = ("signs and slope use the zero run (checked by the null run); the pairs do not. "
                       "map = first adjoint (3 wall layers, 1000-it primal: NOT the bumps' mesh); "
                       "matched_map = adjoint on the bumps' own mesh and primal")
    (R / "judge.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    c = sys.argv[1]
    npar = lambda i: int(sys.argv[i]) if len(sys.argv) > i else 2
    if c == "base":
        cmd_base(npar(2))
    elif c == "remesh":
        cmd_remesh()
    elif c == "bumps":
        cmd_bumps()
    elif c == "bump":
        cmd_bump(sys.argv[2], npar(3))
    elif c == "zero":
        cmd_reference_repeat(npar(2))
    elif c == "adjoint":
        cmd_adjoint(npar(2))
    elif c == "adjoint_matched":
        cmd_adjoint(npar(2), matched=True)
    elif c == "gradvariant":
        cmd_gradvariant(sys.argv[2], sys.argv[3])
    elif c == "variant":
        cmd_variant(sys.argv[2], sys.argv[3], sys.argv[4])
    elif c == "judge":
        cmd_judge()
