"""Free-form sidepod search: level-set shape optimisation driven by the DAFoam adjoint, real walls.

Route A of ROUTES.md. Objective: RACE TIME (Part 2's race model): drag from CFD, plus the exact
mass of the design (foam beyond the 48.0 g legal minimum costs 1.22 ms per cm3; below it lead tops up,
and the race model may choose extra ballast for the COM: objective.best_ballast).

v2 (2026-11-20). A dry run of v1 with the real gradient moved 18 voxels per step, for three reasons,
all fixed here:
  * the step was normalised by max|g| and the gradient has a hot spot -> normalise by the 95th
    percentile of |g| on the surface band and clip to +/- step;
  * the field was the EDT difference of binary voxels (a jump of 2 across the surface) and was reset
    to it every step, so sub-voxel moves were lost -> a true signed distance (slope 1), re-distanced at
    4x resolution, and the CFD surface is cut from the continuous field (sub-voxel positions);
  * drag was the only objective -> race time, with the mass price as a volume multiplier (KKT of the
    kink at the floor: free while lead remains, at most the true price when it is gone).

One iteration, design field f (mm, + = foam, slope 1, the 1 mm grid of geometry.Car):
  1. candidate f_try = f - d,  d = step * clip(g / p95|g|, -1, 1),  g = smoothed race-time gradient
  2. build_design: rules + 3-axis mill + min wall + checks on the voxels of f_try; where the rules
     changed nothing the surface comes from f_try itself (sub-voxel), elsewhere from the milled voxels
  3. coarse real-wall solve, steady scheme (CFD_DIV_U): the last accepted mesh reshaped onto the new
     body (low noise; a fresh mesh if the reshaped one fails checkMesh), warm-started from its flow
  4. accept only if the solve converged on the morphed mesh (a fresh-mesh fallback is not comparable)
     and race time fell by more than the margin (0.4 mN of drag, whole car: the pairs show a
     ~0.1 mN half-car morph offset/curvature); else halve the step and retry
  5. on accept: DAFoam Krylov adjoint -> dD/dn per surface point -> grid (mirrored, region only)
Every step logs the first-order prediction next to the measured change: a running gradient check.
The level set can merge and split pods; it does not open a hole in solid on its own, and it only
takes steps that help now, so start from several seeds (`seeds()`).

    python shape_loop.py init  runs/A --seed original      # seeds: original lean blend block channel
    python shape_loop.py run   runs/A --iters 10 [--hours 6]
    python shape_loop.py show  runs/A                      # history table
Every iteration is saved (it_NNN/: field.npz, car folder, cfd.json), log.jsonl is the history.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from scipy import ndimage

HERE = Path(__file__).resolve().parent
P2 = HERE.parents[1] / "part2-simulation"
sys.path.insert(0, str(P2)); sys.path.insert(0, str(HERE))

STEADY_DIV_U = "bounded Gauss upwind"
DOMAIN = None            # set from gate.DOMAIN at import time below (same domain as every gate run)


# ------------------------------------------------------------------ seeds
def seeds(car) -> dict:
    """Starting fields (mm, + = foam). The level set never opens holes in solid, so tunnel-like
    topologies get their own seed and the search decides whether they survive."""
    out = {"original": car.sdf_original.astype(float),
           "lean": car.sdf_lean.astype(float),
           "blend": 0.5 * (car.sdf_original + car.sdf_lean).astype(float)}
    # block: the whole region foam (the mill and rules cut it back to something buildable)
    reg_sdf = (ndimage.distance_transform_edt(car.region) - ndimage.distance_transform_edt(~car.region)) * car.h
    out["block"] = np.maximum(car.sdf_original, reg_sdf).astype(float)
    # channel: the team's pod with a lengthwise groove, low and open outboard. An ENCLOSED tunnel
    # cannot be made: the 3-axis mill (top, bottom, left, right set-ups) cannot reach a hole running
    # along x, and fills it (tested 2026-11-20: a 5 mm bore came back 98.5 % solid). Open grooves can.
    s = car.s
    Ycen = 0.8 * s.region_ymax
    Zcen = s.region_z[0] + 0.35 * (min(s.region_z[1], s.ceiling_mm or 1e9) - s.region_z[0])
    r = 4.0                                   # 8 mm groove: the 6.35 mm ball must fit
    d_axis = np.sqrt((np.abs(car.Y) - Ycen) ** 2 + (car.Z - Zcen) ** 2)
    d_slot = np.where(np.abs(car.Y) >= Ycen, np.abs(car.Z - Zcen), d_axis)    # the bore, opened to the side
    out["channel"] = np.minimum(car.sdf_original, d_slot - r).astype(float)
    return out


# ------------------------------------------------------------------ CFD pieces
def solve(folder: Path, iters: int, ref: str | None, n_sub: int) -> tuple[dict, str]:
    """Coarse real-wall half-car solve of a car folder, steady scheme; returns (record, kept run dir).
    ref = the last accepted run: its mesh is reshaped onto this body (the gate's validated low-noise
    path; Part 2 falls back to a fresh mesh and writes MORPH_FALLBACK) and its flow is mapped in."""
    import stopwatch as SW
    from cfd_wrapper import run_half_car_cfd
    from evaluators import _latest_run_dir
    os.environ.setdefault("CFD_DIV_U", STEADY_DIV_U)
    body = SW.body_stl(folder / "car_half.stl", folder / "_body_half.stl")
    kw = dict(SW.SEARCH, domain_reference_bounds=DOMAIN, resolution="coarse", max_iterations=int(iters))
    if ref:
        kw.update(morph_from=ref, warm_from=ref)
    t = time.time()
    half, health = run_half_car_cfd(str(body), n_subdomains=n_sub, extra_surfaces=SW.extra_surfaces(folder),
                                    keep_run_dir=True, **kw)
    run = str(_latest_run_dir())
    full = half.to_full_car()
    return ({"D20_half_N": float(half.D20), "D20_N": float(full.D20), "L20_N": float(full.L),
             "converged": bool(health.converged), "residual_p": health.residual_final,
             "force_osc": health.force_oscillation, "force_mean_stderr": getattr(health, "force_mean_stderr", None),
             "morph_fallback": bool(ref and (Path(run) / "MORPH_FALLBACK").exists()), "fresh_mesh": not ref,
             "wall_s": round(time.time() - t, 1), "div_U": os.environ["CFD_DIV_U"]}, run)


def morph_drift(run: str, target_stl: Path) -> dict:
    """How far the CFD's car surface is from the designed one: the run's car-patch mesh points
    against the exported half-car STL (mm). A morphed mesh is smoothed (Part 2, 0.5 mm), so a large
    drift means the CFD measured a smoother body than the one the next step starts from."""
    try:
        import trimesh
        import openfoam_case as OC
        pm = Path(run) / "constant" / "polyMesh"
        start, n = OC.patch_range((pm / "boundary").read_text(), "car")
        labels = OC.patch_mesh_points(OC.read_ascii_faces((pm / "faces").read_text()), start, n)
        pts = OC.read_ascii_points((pm / "points").read_text())[labels]
        m = trimesh.load(target_stl, process=True)
        _, dist, _ = trimesh.proximity.closest_point(m, pts)
        return {"drift_mean_mm": float(dist.mean() * 1e3), "drift_p99_mm": float(np.quantile(dist, 0.99) * 1e3),
                "drift_max_mm": float(dist.max() * 1e3)}
    except UnicodeDecodeError:                                     # a fresh (binary) mesh: not measured
        return {}
    except Exception as e:                                         # a diagnostic only
        return {"drift_error": repr(e)[:200]}


def adjoint(run_dir: str, case: Path, n_proc: int, env: dict) -> dict:
    """DAFoam Krylov adjoint on a converged run: dD_half/dXs per surface point of patch `car`."""
    subprocess.run([sys.executable, str(HERE / "dafoam" / "make_case.py"), "--src", run_dir, "--out", str(case),
                    "--iters", "300"], check=True, stdout=subprocess.DEVNULL)
    e = dict(os.environ, DAF_ADJ="Krylov", DAF_PC_FILL="0", DAF_PC_LEVEL="1", DAF_GMRES_ITERS="2000",
             DAF_GMRES_RESTART="200", DAF_GMRES_TOL="1e-4", **env)
    t = time.time()
    with open(case.parent / "dafoam.out", "w") as f:
        subprocess.run(["bash", str(HERE / "dafoam" / "run_docker.sh"), str(case), str(n_proc)], env=e,
                       stdout=f, stderr=subprocess.STDOUT, check=False)
    sens = case / "dafoam_sens.npz"
    if not sens.exists():
        raise RuntimeError(f"DAFoam wrote no gradient; see {case.parent / 'dafoam.out'}")
    shutil.copy(sens, case.parent / "dafoam_sens.npz")
    S = np.load(sens)
    return {"Xs": S["Xs"], "dD_dXs": S["dD_dXs"], "D_half_dafoam_N": float(S["D_N"]), "adjoint_wall_s": round(time.time() - t, 1)}


# ------------------------------------------------------------------ gradient on the design grid
def grid_gradient(car, folder: Path, Xs: np.ndarray, dD_dXs: np.ndarray) -> tuple[np.ndarray, dict]:
    """Whole-car dD (N) per mm of outward surface move, per 1 mm cell, region only, NOT smoothed.
    Each DAFoam point's half-car value goes to its cell and to the mirror cell: the field is
    symmetric, so sum(g * outward move) over all cells is the whole-car change. Normals: nearest
    vertex normal of the exported half-car STL (the body DAFoam meshed)."""
    import trimesh
    from scipy.spatial import cKDTree
    m = trimesh.load(folder / "_body_half.stl", process=True)
    _, idx = cKDTree(m.vertices).query(Xs)
    n = m.vertex_normals[idx]
    dDdn = (dD_dXs * n).sum(1) * 1e-3                                  # N per mm of outward move
    s = car.s
    X, Y, Z = s.x_nose_mm - Xs[:, 0] * 1e3, Xs[:, 1] * 1e3, Xs[:, 2] * 1e3
    h = car.h
    i = np.clip(np.round((X - car.xs[0]) / h).astype(int), 0, len(car.xs) - 1)
    k = np.clip(np.round((Z - car.zs[0]) / h).astype(int), 0, len(car.zs) - 1)
    g = np.zeros(car.body0.shape)
    for yy in (Y, -Y):
        j = np.clip(np.round((yy - car.ys[0]) / h).astype(int), 0, len(car.ys) - 1)
        np.add.at(g, (i, j, k), dDdn)
    in_reg = car.region[i, np.clip(np.round((Y - car.ys[0]) / h).astype(int), 0, len(car.ys) - 1), k]
    info = {"points": int(len(Xs)), "points_in_region": int(in_reg.sum()),
            "dD_dn_region_sum_mN_per_mm": float(dDdn[in_reg].sum() * 1e3),
            "dD_dn_region_absmax_mN_per_mm": float(np.abs(dDdn[in_reg]).max() * 1e3) if in_reg.any() else 0.0}
    return g * car.region, info


def sdf_of(car, B: np.ndarray) -> np.ndarray:
    """Signed distance (mm, + inside) of a voxel body, slope 1 across the surface: the first cells
    are at +/- h/2 (the plain EDT difference jumps from -h to +h there)."""
    h = car.h
    return np.where(B, ndimage.distance_transform_edt(B) - 0.5, -(ndimage.distance_transform_edt(~B) - 0.5)) * h


def redistance(car, f: np.ndarray, up: int = 4, pad: int = 6) -> np.ndarray:
    """f -> a signed distance with the same zero surface, keeping sub-voxel positions: the box around
    the region is resampled `up` times finer, thresholded, distanced and averaged back."""
    lo = np.maximum(car.rlo - pad, 0); hi = np.minimum(car.rhi + pad, f.shape)
    sub = f[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
    fu = ndimage.zoom(sub, up, order=1, mode="nearest", grid_mode=True)
    Bu = fu > 0
    du = np.where(Bu, ndimage.distance_transform_edt(Bu) - 0.5, -(ndimage.distance_transform_edt(~Bu) - 0.5)) / up
    n = sub.shape
    d = du.reshape(n[0], up, n[1], up, n[2], up).mean((1, 3, 5)) * car.h
    out = f.copy()
    out[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] = d
    return out


def occupancy(car, f: np.ndarray) -> np.ndarray:
    """Foam fraction for the surface cut: a ramp over +/- one voxel. With a slope-1 field the 0.5
    level sits exactly at f = 0 and a field change of s moves it by s (a one-voxel-wide ramp
    under-responded: 0.06 mm for 0.1). Its sum over cells is the volume."""
    return np.clip(0.5 + f / (2.0 * car.h), 0.0, 1.0)


def build_design(car, f: np.ndarray) -> dict:
    """Field -> a legal, milled body. The rules, the mill, the wall rule and the checks act on the
    voxels of f (as Car.build). The surface is then cut from f itself wherever the rules left the
    voxels alone (sub-voxel moves reach the CFD), and from the milled voxels elsewhere.
    Returns voxels, check, mesh, mass, and f_rules: the field of what will actually be made."""
    import geometry as GEO
    import trimesh
    from skimage import measure
    CI = GEO.CI
    fs = 0.5 * (f + f[:, ::-1])
    B, rep = car.mill(car.finish(fs))
    B, rep["min_wall_passes"] = car.min_wall(B, rep)
    chk = car.check(B)
    agree = ((fs > 0) == B) & car.region
    out = dict(voxels=B, mill=rep, check=chk, mesh=None, mass=None,
               rules_changed_mm3=float(((~agree) & car.region).sum() * car.h ** 3))
    f_rules = np.where(agree, fs, sdf_of(car, B))
    out["f_rules"] = redistance(car, f_rules)
    if not chk["ok"]:
        return out
    occ = np.where(agree, occupancy(car, fs), B.astype(float))
    err = None
    for sigma in (0.7, 0.72, 0.68, 0.75, 0.65):                      # as Car.body_mesh_for: dodge CAD-edge slivers
        try:
            P = ndimage.gaussian_filter(np.pad(occ.astype(np.float32), 2), sigma)
            v, fa, _n, _ = measure.marching_cubes(P, 0.5)
            h = car.h
            v = np.c_[car.xs[0] + (v[:, 0] - 2) * h, car.ys[0] + (v[:, 1] - 2) * h, car.zs[0] + (v[:, 2] - 2) * h]
            m = trimesh.Trimesh(v, fa, process=True)
            if m.volume < 0:
                m.invert()
            if not m.is_watertight:
                m = CI.repair(m)
            mesh = CI.clean(CI.from_manifold(car.kept_M + (CI.to_manifold(m) ^ car.region_Me)))
            CI.accept(mesh, name="designed body")
            out["mesh"] = mesh
            out["mass"] = car.mass(mesh)
            return out
        except ValueError as e:
            err = e
    out["check"] = dict(chk, ok=False, mesh_error=repr(err)[:200])
    return out


def step_field(car, f, B, gD, mass, slopes, step_mm, sigma_mm) -> tuple[np.ndarray, dict]:
    """The field change d (f_try = f - d) for one step, and what first order says it does.
    Race-time gradient per cell (s per mm outward) = slope_D * gD + lam * (surface cells' area):
    lam is the price of foam volume. While lead remains it is 0 (lead swaps for foam); with no lead
    left it is the smallest value in [0, true mass price] that stops the step adding volume, or
    the true price if the step still wants to grow at that price (the KKT of the kink at the floor)."""
    h = car.h
    sD = slopes["drag_20_n"]                                           # s per N, whole car
    price = slopes["car_weight_kg"] * 0.163e-6                         # s per mm3 of foam beyond the floor
    surf = car.region & B & ~ndimage.binary_erosion(B)
    band = car.region & (np.abs(f) <= 1.5 * h)
    occ0 = occupancy(car, f)
    # moves the rules forbid carry no gradient (else they set the step's scale and its prediction):
    # growth where no region air touches the cell (the legal block's faces, forced air), and
    # shrinking the forced cargo foam
    can_grow = ndimage.binary_dilation(car.region & ~B, iterations=2)
    blocked = ((gD < 0) & ~can_grow) | ((gD > 0) & ndimage.binary_dilation(car.cargo))
    gD_all, gD = gD, np.where(blocked, 0.0, gD)

    # the rest of the exact race-time gradient of foam at a surface cell: its effect on the centre of
    # mass (and on the lead swap's COM), from objective.mass_cell_gradient; the mass PRICE itself is
    # the multiplier lam below (it has a kink at the weight floor). Lift has no adjoint here: its
    # slope is ~1 % of drag's (-0.002 vs 0.188 s/N) and the NACA 0015 wings sit at zero incidence.
    from objective import mass_cell_gradient
    lead_active = mass["lead_g"] > 0 and mass["lead_g"] <= mass.get("lead_min_g", mass["lead_g"]) + 1e-9
    com_part = mass_cell_gradient(car, mass, slopes) - (0.0 if lead_active else price)
    com_part = np.where(surf, com_part * h ** 3 / h, 0.0)             # s per mm of outward move (cell face area h^2)

    def make(lam):
        g = ndimage.gaussian_filter(sD * gD + com_part + lam * surf * h * h, sigma_mm / h) * car.region
        norm = np.percentile(np.abs(g[band]), 95) if band.any() else 0.0
        d = step_mm * np.clip(g / norm, -1.0, 1.0) if norm > 0 else np.zeros_like(g)
        dV = float(((occupancy(car, f - d) - occ0) * car.region).sum() * h ** 3)
        return d, dV, norm

    lam, (d, dV, norm) = 0.0, make(0.0)
    if mass["lead_g"] < 0.01 and dV > 0:
        dp, dVp, normp = make(price)
        if dVp > 0:
            lam, d, dV, norm = price, dp, dVp, normp                   # growth is worth paying for
        else:
            a, b = 0.0, price
            for _ in range(12):
                lam = 0.5 * (a + b)
                d, dV, norm = make(lam)
                a, b = (lam, b) if dV > 0 else (a, lam)
            lam = b; d, dV, norm = make(lam)
    moved = np.abs(d[band]) if band.any() else np.zeros(1)
    info = {"com_grad_share": float(np.abs(com_part).sum() / max(np.abs(sD * gD).sum(), 1e-30)),
            "grad_blocked_share": float(np.abs(gD_all[blocked]).sum() / max(np.abs(gD_all).sum(), 1e-30)),
            "lam_ms_per_cm3": lam * 1e6, "price_ms_per_cm3": price * 1e6, "pred_dV_mm3": dV,
            "pred_dD_mN": float((gD * (-d)).sum() * 1e3),               # outward move = -d
            "pred_dT_ms": float((sD * (gD * (-d)).sum() + price * max(0.0, dV - mass["lead_g"] / 0.163e-3)) * 1e3),
            "moved_gt_0p1mm_share": float((moved > 0.1).mean()), "move_median_mm": float(np.median(moved)),
            "grad_norm_p95": float(norm)}
    return d, info


# ------------------------------------------------------------------ driver
def load_car():
    from geometry import Car
    return Car(h=1.0)


def export_design(car, b, out: Path, label: str):
    if not b["check"]["ok"]:
        return None
    car.export_car_folder(b["mesh"], out / "car", label)
    return out / "car"


def race_model(car):
    from objective import RaceModel
    return RaceModel(car.s)


def cmd_init(a):
    run = Path(a.run)
    run.mkdir(parents=True, exist_ok=True)
    car = load_car()
    b = build_design(car, seeds(car)[a.seed])
    np.savez_compressed(run / "current.npz", f=b["f_rules"])          # a true distance field, rules folded in
    cfg = {"seed": a.seed, "step_mm": a.step_mm, "step_min_mm": a.step_min_mm, "sigma_mm": a.sigma_mm,
           "iters_cold": a.iters_cold, "iters_warm": a.iters_warm, "np": a.np, "div_U": os.environ.get("CFD_DIV_U", STEADY_DIV_U),
           "accept_margin_mN": a.accept_margin_mN, "version": 2}
    (run / "config.json").write_text(json.dumps(cfg, indent=1))
    (run / "state.json").write_text(json.dumps({"it": 0, "step_mm": a.step_mm, "T_current": None, "D_current": None,
                                                "run_current": None, "mass_current": None, "grad_ready": False}, indent=1))
    print(json.dumps({"seed": a.seed, "check": b["check"], "pod_cm3": float((b["voxels"] & car.region).sum() * car.h ** 3 * 1e-3),
                      "mass": b["mass"]}, default=float)[:1500])


def log(run: Path, rec: dict):
    with open(run / "log.jsonl", "a") as fh:
        fh.write(json.dumps(rec, default=float) + "\n")
    print(json.dumps(rec, default=float), flush=True)


def _adjoint_to_grid(car, run, rdir, folder, work, n_proc):
    A = adjoint(rdir, work / "dafoam_case", n_proc, {})
    gD, ginfo = grid_gradient(car, folder, A["Xs"], A["dD_dXs"])
    np.savez_compressed(run / "grad_current.npz", gD=gD)
    shutil.rmtree(work / "dafoam_case", ignore_errors=True)
    return {**{k: v for k, v in A.items() if k not in ("Xs", "dD_dXs")}, **ginfo}


MAX_STALE = 2


def _use_stale_gradient(run: Path, st: dict) -> bool:
    """An adjoint failed on the accepted design (e.g. GMRES stalled with the memory-limited
    preconditioner). Keep stepping along the last good gradient: it belongs to a design at most one
    step away, and every step is still judged by real CFD. At most MAX_STALE accepted designs in a row."""
    n = int(st.get("stale_grad", 0)) + 1
    if n > MAX_STALE or not (run / "grad_current.npz").exists():
        return False
    st.update(stale_grad=n, grad_ready=True)
    return True


def cmd_run(a):
    global DOMAIN
    import gate
    DOMAIN = gate.DOMAIN
    run = Path(a.run)
    cfg = json.loads((run / "config.json").read_text())
    if cfg.get("version") != 2:
        raise SystemExit("this run was started with shape_loop v1 (see ROUTES.md 2026-11-20 18:45): re-init it")
    os.environ.setdefault("CFD_DIV_U", cfg["div_U"])
    st = json.loads((run / "state.json").read_text())
    car = load_car()
    rm = race_model(car)
    f_cur = np.load(run / "current.npz")["f"]
    t_end = time.time() + a.hours * 3600 if a.hours else None
    save = lambda: (run / "state.json").write_text(json.dumps(st, indent=1, default=str))
    # an accepted design whose adjoint failed (crash, OOM): redo the adjoint before any step, so we
    # never step along a stale gradient (or a missing one)
    if st["T_current"] is not None and not st.get("grad_ready"):
        if not (st["run_current"] and Path(st["run_current"]).exists()):
            raise RuntimeError("accepted design has no gradient and its CFD run is gone; re-init this seed")
        d = run / "adjoint_retry"
        shutil.rmtree(d, ignore_errors=True); d.mkdir()
        try:
            info = _adjoint_to_grid(car, run, st["run_current"], run / "best_car", d, cfg["np"])
            st.update(grad_ready=True, stale_grad=0); save()
            log(run, {"it": st["it"], "step_mm": st["step_mm"], "adjoint_retry": True, **info})
        except Exception as e:
            if not _use_stale_gradient(run, st):
                raise
            save()
            log(run, {"it": st["it"], "step_mm": st["step_mm"], "adjoint_retry": True, "adjoint_error": repr(e)[:300],
                      "stale_gradient": st["stale_grad"]})
    done = 0
    while done < a.iters and (not t_end or time.time() < t_end):
        it = st["it"]
        d = run / f"it_{it:03d}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir()
        rec = {"it": it, "step_mm": st["step_mm"]}
        # ---- candidate: the current design itself (first time), or a step from it along the gradient
        if st["T_current"] is None:
            f_try = f_cur
        else:
            B_cur = car.finish(f_cur)
            _, sl = rm(st["D_current"], st["L_current"], st["mass_current"])
            dd, sinfo = step_field(car, f_cur, B_cur, np.load(run / "grad_current.npz")["gD"], st["mass_current"], sl,
                                   st["step_mm"], cfg["sigma_mm"])
            f_try = f_cur - dd
            rec.update(sinfo)
        b = build_design(car, f_try)
        folder = export_design(car, b, d, f"{run.name}_it{it:03d}")
        np.savez_compressed(d / "field.npz", f=f_try)
        rec.update(check_ok=b["check"]["ok"], pod_cm3=float((b["voxels"] & car.region).sum() * car.h ** 3 * 1e-3),
                   rules_changed_mm3=b["rules_changed_mm3"], mass_g=(b["mass"] or {}).get("race_mass_g"),
                   lead_g=(b["mass"] or {}).get("lead_g"))
        if folder is None:                                          # illegal design: shorter step
            rec.update(accepted=False, why="check failed: " + json.dumps(b["check"], default=str)[:300])
            st["step_mm"] *= 0.5
        else:
            try:
                cfd, rdir = solve(folder, cfg["iters_warm"] if st["run_current"] else cfg["iters_cold"],
                                  st["run_current"], cfg["np"])
            except Exception as e:                                  # a failed solve is a rejected step
                cfd, rdir = {"error": repr(e)[:300]}, None
            if cfd.get("morph_fallback") and st["T_current"] is not None and not rec.get("rebased"):
                # the lineage's mesh can no longer be reshaped onto this design: RE-BASE. Solve the
                # current design on a fresh mesh (its gradient stays valid: same design), make that
                # the reference, and morph the candidate from it, so both numbers share a mesh.
                if rdir:
                    shutil.rmtree(rdir, ignore_errors=True)
                try:
                    cb, rb = solve(run / "best_car", cfg["iters_cold"], None, cfg["np"])
                except Exception as e:
                    cb, rb = {"error": repr(e)[:300]}, None
                if cb.get("D20_N") is not None and cb.get("converged"):
                    Tb, _ = rm(cb["D20_N"], cb["L20_N"], st["mass_current"])
                    rec.update(rebased=True, rebase_D20_N=cb["D20_N"], rebase_from_D20_N=st["D_current"])
                    if st["run_current"] and Path(st["run_current"]).exists():
                        shutil.rmtree(st["run_current"], ignore_errors=True)
                    st.update(T_current=Tb, D_current=cb["D20_N"], L_current=cb["L20_N"], run_current=rb)
                    save()
                    try:
                        cfd, rdir = solve(folder, cfg["iters_warm"], rb, cfg["np"])
                    except Exception as e:
                        cfd, rdir = {"error": repr(e)[:300]}, None
                else:
                    rec.update(rebase_error=cb.get("error") or "re-base solve did not converge")
                    if rb:
                        shutil.rmtree(rb, ignore_errors=True)
                    cfd, rdir = dict(cfd, morph_fallback=True), None
            (d / "cfd.json").write_text(json.dumps(cfd, indent=1, default=float))
            rec.update(cfd)
            T = None
            if cfd.get("D20_N") is not None:
                from objective import best_ballast
                T, mbest = best_ballast(rm, car, b["mesh"], cfd["D20_N"], cfd["L20_N"])   # the model picks the ballast
                b["mass"] = mbest
                rec.update(T_s=T, lead_g=mbest["lead_g"], lead_min_g=mbest["lead_min_g"], car_g=mbest["car_g"],
                           mass_suspect=mbest["mass_suspect"])
                if mbest["mass_suspect"]:
                    print(f"MASS_SUSPECT: design weighs {mbest['car_g']:.2f} g (> 50 g): check the model", flush=True)
                if st["T_current"] is not None:
                    rec.update(dT_ms=(T - st["T_current"]) * 1e3, dD_mN=(cfd["D20_N"] - st["D_current"]) * 1e3)
            first = st["T_current"] is None
            if rdir:
                rec.update(morph_drift(rdir, folder / "_body_half.stl"))
            margin = cfg["accept_margin_mN"] * 1e-3 * rm(st["D_current"], st["L_current"], st["mass_current"])[1]["drag_20_n"] \
                if not first else 0.0
            why = ("solve failed" if T is None else "not converged" if not (cfd["converged"] or first)
                   else "fresh mesh (not comparable with the morph lineage)" if (not first and cfd.get("morph_fallback"))
                   else "race time not lower by the margin" if (not first and T >= st["T_current"] - margin) else None)
            if why:
                rec.update(accepted=False, why=why)
                st["step_mm"] *= 0.5
                if rdir:
                    shutil.rmtree(rdir, ignore_errors=True)
            else:
                rec.update(accepted=True)
                f_cur = b["f_rules"]                                # what will actually be milled, sub-voxel kept
                np.savez_compressed(run / "current.npz", f=f_cur)
                if st["run_current"] and Path(st["run_current"]).exists():
                    shutil.rmtree(st["run_current"], ignore_errors=True)
                st.update(T_current=T, D_current=cfd["D20_N"], L_current=cfd["L20_N"], mass_current=b["mass"],
                          run_current=rdir, best_it=it, grad_ready=False)
                shutil.copytree(folder, run / "best_car", dirs_exist_ok=True)
                try:
                    rec.update(_adjoint_to_grid(car, run, rdir, folder, d, cfg["np"]))
                    st.update(grad_ready=True, stale_grad=0)
                except Exception as e:
                    rec.update(adjoint_error=repr(e)[:300])
                    if _use_stale_gradient(run, st):                # step along the last good gradient
                        rec.update(stale_gradient=st["stale_grad"])
                    else:                                           # next start redoes the adjoint
                        st["it"] = it + 1                           # keep it_NNN (its car is best_car)
                        log(run, rec); save()
                        raise
        st["it"] = it + 1
        log(run, rec)
        save()
        done += 1
        if st["step_mm"] < cfg["step_min_mm"]:
            print("step below minimum: converged (or stuck)", flush=True)
            break


def cmd_show(a):
    for line in (Path(a.run) / "log.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r.get("adjoint_retry"):
            print(f"it {r['it']:3d}  adjoint redone"); continue
        D = f"D {1e3 * r['D20_N']:.2f} mN" if r.get("D20_N") else "(no drag)"
        T = f"T {r['T_s']:.5f} s" if r.get("T_s") else ""
        ch = f"dT {r['dT_ms']:+.3f} ms (pred {r.get('pred_dT_ms', float('nan')):+.3f})" if r.get("dT_ms") is not None else ""
        print(f"it {r['it']:3d}  step {r['step_mm']:.2f} mm  {D}  {T}  {ch}  "
              f"{'ACCEPT' if r.get('accepted') else 'reject (' + str(r.get('why')) + ')'}  pod {r.get('pod_cm3', 0):.1f} cm3"
              f"{'  FRESH MESH' if r.get('morph_fallback') else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "run", "show"]); ap.add_argument("run")
    ap.add_argument("--seed", default="original", choices=["original", "lean", "blend", "block", "channel"])
    ap.add_argument("--step_mm", type=float, default=1.5)
    ap.add_argument("--step_min_mm", type=float, default=0.1)
    ap.add_argument("--sigma_mm", type=float, default=4.5)     # the gate checked ~10 mm bumps; coarse surface ~4 mm
    ap.add_argument("--accept_margin_mN", type=float, default=0.4)   # whole car: morph offset / curvature seen in the pairs
    ap.add_argument("--iters_cold", type=int, default=2500)
    ap.add_argument("--iters_warm", type=int, default=1200)
    ap.add_argument("--np", type=int, default=4)
    ap.add_argument("--iters", type=int, default=10)
    ap.add_argument("--hours", type=float, default=None)
    a = ap.parse_args()
    {"init": cmd_init, "run": cmd_run, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
