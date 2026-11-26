"""Tests T0 (ingest) and T0b (operators) on the real car and the real builder. No CFD.
Marks: SEED_EVOLUTION_PLAN.md section 7.

    python -m seedevo.run_t0 ingest   <out.json>
    python -m seedevo.run_t0 seeds    <dir>                 # the test seeds (fields), built once
    python -m seedevo.run_t0 ops      <dir> <out.json> [--draws 40] [--procs 4]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))


def _surf_dist(a, b, car, n=40000, seed=0):
    """Distance (mm) from points on a's surface inside the region box (one side) to b's surface: p50, p99, max."""
    import trimesh
    P, _ = trimesh.sample.sample_surface(a, n, seed=seed)
    s = car.s
    k = ((P[:, 0] > s.region_x[0] + 1) & (P[:, 0] < s.region_x[1] - 1) & (P[:, 1] > s.spine_y + 1)
         & (P[:, 1] < s.region_ymax) & (P[:, 2] > s.region_z[0]))
    P = P[k]
    _, d, _ = trimesh.proximity.closest_point(b, P)
    return {"n": int(len(P)), "p50": float(np.median(d)), "p99": float(np.quantile(d, 0.99)), "max": float(d.max())}


def cmd_ingest(out):
    import trimesh
    import shape_loop as SL
    from seedevo import ingest
    car = SL.load_car()
    res = {}
    # (a) known answer: the trial car's own STEP
    t = time.time()
    f, info = ingest.field_from_step(car, car.s.step)
    b = SL.build_design(car, f)
    res["a_trial_car"] = {"ingest": info, "ok": b["check"]["ok"], "rules_changed_mm3": b["rules_changed_mm3"],
                          "built_volume_cm3": b["mesh"].volume / 1e3, "cad_volume_cm3": car.body_mesh.volume / 1e3,
                          "built_to_cad": _surf_dist(b["mesh"], car.body_mesh, car),
                          "cad_to_built": _surf_dist(car.body_mesh, b["mesh"], car), "wall_s": round(time.time() - t, 1)}
    # the existing 'original' seed (voxel distance only), for comparison
    b0 = SL.build_design(car, SL.seeds(car)["original"])
    res["a_existing_original_seed"] = {"built_volume_cm3": b0["mesh"].volume / 1e3,
                                       "built_to_cad": _surf_dist(b0["mesh"], car.body_mesh, car)}
    # (b) round trip of a seed with a feature: the grooved pod, out as STL, back in, built again
    bc = SL.build_design(car, SL.seeds(car)["channel"])
    p = Path(out).with_suffix(".channel.stl")
    bc["mesh"].export(p)
    f2, info2 = ingest.field_from_stl(car, p)
    b2 = SL.build_design(car, f2)
    res["b_roundtrip_channel"] = {"ingest": info2, "ok": b2["check"]["ok"], "rules_changed_mm3": b2["rules_changed_mm3"],
                                  "pod_cm3_in": float((bc["voxels"] & car.region).sum() * 1e-3),
                                  "pod_cm3_back": float((b2["voxels"] & car.region).sum() * 1e-3),
                                  "volume_in_cm3": bc["mesh"].volume / 1e3, "volume_back_cm3": b2["mesh"].volume / 1e3,
                                  "back_to_in": _surf_dist(b2["mesh"], bc["mesh"], car),
                                  "in_to_back": _surf_dist(bc["mesh"], b2["mesh"], car)}
    p.unlink()
    A, R = res["a_trial_car"], res["b_roundtrip_channel"]
    res["marks"] = {
        "T0a_volume_within_0p5pct": abs(A["built_volume_cm3"] / A["cad_volume_cm3"] - 1) <= 0.005,
        "T0a_surface_p99_le_0p3mm": max(A["built_to_cad"]["p99"], A["cad_to_built"]["p99"]) <= 0.3,
        "T0b_roundtrip_p99_le_0p3mm": max(R["back_to_in"]["p99"], R["in_to_back"]["p99"]) <= 0.3,
        "T0b_roundtrip_volume_within_0p5pct": abs(R["volume_back_cm3"] / R["volume_in_cm3"] - 1) <= 0.005}
    Path(out).write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res, indent=1, default=float))


def make_test_seeds(space, n=10, seed=5):
    """Ten different legal pods on the real car, made from the code's own seeds plus fixed random features."""
    import shape_loop as SL
    from seedevo import operators as OP
    car = space.car
    S = SL.seeds(car)
    rng = np.random.default_rng(seed)
    out = {}
    for name in ("original", "channel"):
        out[name] = space.build(S[name])["f"]
    bases = [S["original"], S["original"] - 2.5, 0.75 * S["original"] + 0.25 * S["lean"], np.minimum(S["block"], S["original"] + 4.0)]
    while len(out) < n:
        f = bases[int(rng.integers(len(bases)))].astype(float)
        for _ in range(int(rng.integers(1, 3))):
            b = space.build(f)
            if not b["ok"]:
                break
            f, _m = OP.OPS[str(rng.choice(["cut", "pattern", "bump", "fill"], p=[0.4, 0.3, 0.2, 0.1]))](space, rng, b["f"], None, None)
        b = space.build(f)
        if b["ok"] and b["pod_mm3"] > 15000:
            out[f"t{len(out):02d}"] = b["f"]
    return out


def cmd_seeds(d):
    from seedevo.space import RealSpace
    sp = RealSpace()
    d = Path(d); d.mkdir(parents=True, exist_ok=True)
    seeds = make_test_seeds(sp)
    info = {}
    for k, f in seeds.items():
        b = sp.build(f)
        np.savez_compressed(d / f"{k}.npz", f=b["f"], B=b["B"])
        info[k] = {"desc": sp.describe(b["B"]), "niche": sp.niche(sp.describe(b["B"])), "changed_mm3": b["changed_mm3"]}
    (d / "seeds.json").write_text(json.dumps(info, indent=1, default=float))
    print(json.dumps(info, default=float))


def _ops_worker(args):
    d, op, draws, seed = args
    from seedevo import operators as OP
    from seedevo.space import RealSpace
    sp = RealSpace()
    names = sorted(p.stem for p in Path(d).glob("*.npz"))
    F = {k: np.load(Path(d) / f"{k}.npz") for k in names}
    rng = np.random.default_rng(seed)
    rows = []
    reg = sp.region
    for _ in range(draws):
        a, b = rng.choice(len(names), 2, replace=False)
        fa, fb = F[names[a]]["f"], F[names[b]]["f"]
        Ba, Bb = F[names[a]]["B"] & reg, F[names[b]]["B"] & reg
        t = time.time()
        f, meta = OP.OPS[op](sp, rng, fa, fb if op in OP.CROSSOVER else None, None)
        if "skip" in meta:
            rows.append({"op": op, "skip": meta["skip"]}); continue
        want = float(((f > 0) & reg).sum())
        bl = sp.build(f)
        Bc = bl["B"] & reg
        iou = lambda P, Q: float((P & Q).sum() / max((P | Q).sum(), 1))
        ia, ib = iou(Bc, Ba), (iou(Bc, Bb) if op in OP.CROSSOVER else None)
        rows.append({"op": op, "a": names[a], "b": names[b] if op in OP.CROSSOVER else None, "ok": bl["ok"],
                     "iou_a": ia, "iou_b": ib, "iou_nearest": max(ia, ib or 0.0),
                     "refill_frac": float(bl["info"]["mill"].get("uncut_foam_mm3", 0.0) / max(bl["pod_mm3"], 1.0)),
                     "changed_frac": float(bl["changed_mm3"] / max(want, 1.0)), "pod_cm3": bl["pod_mm3"] / 1e3,
                     "openings": sp.describe(bl["B"])[1] if bl["ok"] else None,
                     "check": {k: v for k, v in bl["info"]["check"].items() if k != "ok"} if not bl["ok"] else None,
                     "s": round(time.time() - t, 1)})
    return rows


def cmd_ops(d, out, draws=40, procs=4, ops=None, seed_base=100):
    from multiprocessing import Pool
    from seedevo import operators as OP
    jobs = [(d, op, draws, seed_base + i) for i, op in enumerate(OP.OPS) if ops is None or op in ops]
    with Pool(procs) as p:
        rows = [r for rs in p.map(_ops_worker, jobs, chunksize=1) for r in rs]
    summ = {}
    for op in [j[1] for j in jobs]:
        R = [r for r in rows if r["op"] == op and "skip" not in r]
        L = [r for r in R if r["ok"]]
        inband = [r for r in L if 0.50 <= r["iou_nearest"] <= 0.98]
        s = {"draws": len(R), "skipped": sum(1 for r in rows if r["op"] == op and "skip" in r),
             "legal_rate": len(L) / max(len(R), 1), "inband_rate": len(inband) / max(len(L), 1),
             "clone_rate": sum(1 for r in L if r["iou_nearest"] > 0.98) / max(len(L), 1),
             "refill_median": float(np.median([r["refill_frac"] for r in L])) if L else None,
             "iou_median": float(np.median([r["iou_nearest"] for r in L])) if L else None}
        s["pass"] = bool(s["legal_rate"] >= 0.5 and s["inband_rate"] >= 0.7 and (s["refill_median"] or 0) <= 0.10)
        summ[op] = s
        print(op, json.dumps(s, default=float), flush=True)
    Path(out).write_text(json.dumps({"summary": summ, "rows": rows}, indent=1, default=float))


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "ingest":
        cmd_ingest(sys.argv[2])
    elif c == "seeds":
        cmd_seeds(sys.argv[2])
    elif c == "ops":
        kw = {}
        if "--draws" in sys.argv:
            kw["draws"] = int(sys.argv[sys.argv.index("--draws") + 1])
        if "--procs" in sys.argv:
            kw["procs"] = int(sys.argv[sys.argv.index("--procs") + 1])
        if "--ops" in sys.argv:
            kw["ops"] = sys.argv[sys.argv.index("--ops") + 1].split(",")
        if "--seed-base" in sys.argv:
            kw["seed_base"] = int(sys.argv[sys.argv.index("--seed-base") + 1])
        cmd_ops(sys.argv[2], sys.argv[3], **kw)
