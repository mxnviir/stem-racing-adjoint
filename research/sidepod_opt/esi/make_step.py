"""Step-test candidates (esi/STEP_TEST.md): a design-scale normal move of the team pod along a smoothed field.

    python esi/make_step.py <name> <field> <amp_mm>      (run from research/sidepod_opt)
      field: esi_frozen | esi_sst   downhill (-ESI sensitivity)
             opp_frozen             uphill control (+ESI frozen)
             rnd1 | rnd2            random smooth control (numpy default_rng seed 1 / 2)
             zero                   no move (the base, same pipeline)
    -> gate/bump_<name>/car_half.stl (+ move_m.npy, step_info.json), and an entry in $GATE_RESULTS/bumps.json,
       the same folder layout as `gate.py variant`, so `gate.py bump <name>` morphs and solves it unchanged.

Field, as fixed in STEP_TEST.md: values on the ESI surface points (the wall-resolved ESI map, or random normals on
the same points) -> Gaussian smoothing sigma 4.5 mm, area-weighted, evaluated at each STL vertex -> taper to the
sidepod region (x 0.07-0.20 m, y > 0.012 m; smoothstep over 5 mm inside its edges) -> mean removed with the same
taper (volume-neutral to first order) -> / 95th percentile of |value| in the region -> clipped to +/-1 -> x amp.
Downhill = against the sensitivity (s_out is dJ per unit OUTWARD move).
"""
import json, os, shutil, sys
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / "part2-simulation"))
import gate                      # noqa: E402  (ORIG, G, R, as the bumps use them)
import cadio as CI               # noqa: E402

SIGMA, TAPER = 4.5e-3, 5e-3
X0, X1, Y0 = 0.07, 0.20, 0.012
SENS = HERE / "gate_results_resolved_up" / "esi"


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def vertex_area(m):
    a = np.zeros(len(m.vertices))
    np.add.at(a, m.faces.ravel(), np.repeat(m.area_faces / 3.0, 3))
    return a


def field_on_vertices(field, V):
    S = np.load(SENS / ("esi_sens_sst.npz" if field == "esi_sst" else "esi_sens_frozen.npz"))
    X, area = S["Xs"], S["area"]
    if field in ("esi_frozen", "esi_sst"):
        val = -S["s_out"]                                  # downhill
    elif field == "opp_frozen":
        val = S["s_out"].copy()                            # uphill control
    elif field in ("rnd1", "rnd2"):
        val = np.random.default_rng(int(field[-1])).standard_normal(len(X))
    else:
        raise SystemExit(f"unknown field {field}")
    out = np.zeros(len(V))
    tree = cKDTree(X)
    idx = np.where((V[:, 0] > X0) & (V[:, 0] < X1) & (V[:, 1] > Y0))[0]
    for i, nb in zip(idx, tree.query_ball_point(V[idx], 3 * SIGMA)):
        if nb:
            w = np.exp(-((X[nb] - V[i]) ** 2).sum(1) / SIGMA ** 2) * area[nb]
            out[i] = (w * val[nb]).sum() / w.sum()
    return out


def main(name, field, amp_mm):
    amp = float(amp_mm) * 1e-3
    base = trimesh.load(gate.ORIG / "car_half.stl")       # as gate.cmd_variant loads it
    V, N = base.vertices, base.vertex_normals
    A = vertex_area(base)
    taper = (smoothstep((V[:, 0] - X0) / TAPER) * smoothstep((X1 - V[:, 0]) / TAPER)
             * smoothstep((V[:, 1] - Y0) / TAPER))
    info = {"field": field, "amp_mm": float(amp_mm), "sigma_mm": SIGMA * 1e3, "taper_mm": TAPER * 1e3,
            "region": {"x": [X0, X1], "y_min": Y0}}
    if field == "zero" or amp == 0.0:
        w = np.zeros(len(V))
    else:
        f = taper * field_on_vertices(field, V)
        f -= taper * (A * f).sum() / (A * taper).sum()   # volume-neutral (first order)
        core = taper > 0.5
        f /= np.percentile(np.abs(f[core]), 95)
        w = np.clip(f, -1.0, 1.0) * amp
        info.update(moved_gt_0p1mm_frac=float(np.mean(np.abs(w[core]) > 1e-4)),
                    max_out_mm=float(w.max() * 1e3), max_in_mm=float(-w.min() * 1e3))
    m = base.copy()
    nv = V + N * w[:, None]
    nv[np.abs(V[:, 1]) < 1e-9, 1] = 0.0
    m.vertices = nv
    folder = gate.G / f"bump_{name}"
    if folder.exists():
        shutil.rmtree(folder)
    shutil.copytree(gate.ORIG, folder, ignore=shutil.ignore_patterns("_body_half.stl"))
    CI.write_ascii_named(m, folder / "car_half.stl", "car", m.volume, 0.01)
    np.save(folder / "move_m.npy", w)
    info["dV_mm3"] = float((m.volume - base.volume) * 1e9)
    (folder / "step_info.json").write_text(json.dumps(info, indent=1))
    p = gate.R / "bumps.json"
    meta = json.loads(p.read_text()) if p.exists() else {}
    meta[name] = {"site": f"step:{field}", **info}
    p.write_text(json.dumps(meta, indent=1))
    print(name, json.dumps(info), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
