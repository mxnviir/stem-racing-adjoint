"""Test TP (SEED_EVOLUTION_PLAN.md section 7): the whole chain on real coarse CFD with a real adjoint.
Plumbing only: no design conclusion from the coarse mesh (DECISIONS D6).

    GATE_RES=coarse CFD_DIV_U="bounded Gauss upwind" GATE_RESULTS=/tmp/gr \
        python -m seedevo.run_plumbing <store dir> <out.json> [--explore 4] [--refine 2]

1. Census: team pod, groove, no pod, and two test seeds with through-openings (made by the `pattern` and
   `cut` operators from the team pod), each on a fresh mesh.
2. Explore: 2 crossover + 2 mutation children, operators that passed T0b only; at least one of each whose
   through-opening count differs from both parents (chosen before any CFD is spent on them).
3. Refine: the 2 best census designs: ESI adjoint on its own converged run, steps of 1.0 and 0.5 mm, each scored
   on the elite's mesh morphed onto it (minus the elite morphed onto itself).
4. Marks P1-P4 printed and written to <out.json>.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from . import operators as OP
from .engine import Config, Engine
from .real import RealEvaluator
from .space import RealSpace

PASSED_T0B = ("splice", "graft", "line", "pattern", "offset")
TEAM_STEADY_WHOLE_mN = 449.24                     # runs/cloud_original iteration 0 (ROUTES 2026-11-20 19:55)


def test_seed(sp, rng, base, op, tries=60):
    for _ in range(tries):
        f, meta = OP.OPS[op](sp, rng, base, None, None)
        if "skip" in meta:
            continue
        b = sp.build(f)
        if b["ok"] and sp.describe(b["B"])[1] > 0:
            return b["f"], meta
    raise RuntimeError(f"no legal {op} seed with an opening in {tries} tries")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("store"); ap.add_argument("out")
    ap.add_argument("--explore", type=int, default=4); ap.add_argument("--refine", type=int, default=2)
    a = ap.parse_args()
    t0 = time.time()
    import shape_loop as SL
    sp = RealSpace()
    ev = RealEvaluator(sp, a.store)
    rng = np.random.default_rng(11)
    S = SL.seeds(sp.car)
    seeds = {k: sp.build(S[k])["f"] for k in ("original", "channel", "lean")}
    seeds["slots"], m1 = test_seed(sp, rng, seeds["original"], "pattern")
    seeds["window"], m2 = test_seed(sp, rng, seeds["original"], "cut")
    eng = Engine(sp, ev, rng, Config(n_explore=0, n_refine=0, step0=1.0, max_runs=1, ops=PASSED_T0B))
    out = {"stages": {}, "marks": {}, "errors": []}

    # 1. census
    eng.census(seeds)
    cen = {i.meta["name"]: {"id": i.id, "D_mN": i.est, "desc": i.desc, "niche": i.niche} for i in eng.seeds}
    out["stages"]["census"] = {"seeds": cen, "illegal_or_failed": [r for r in eng.log if r.get("illegal")],
                               "test_seed_ops": {"slots": m1, "window": m2}}
    print("CENSUS", json.dumps(cen, default=float), flush=True)

    # 2. explore: chosen before CFD so the opening-changing cases are present
    kids, want = [], {"crossover": args_need(a.explore), "mutation": args_need(a.explore)}
    pool = list(eng.seeds)
    for _ in range(400):
        if all(len(v["got"]) >= v["n"] for v in want.values()):
            break
        kind = "crossover" if len(want["crossover"]["got"]) < want["crossover"]["n"] else "mutation"
        ops = [o for o in PASSED_T0B if (o in OP.CROSSOVER) == (kind == "crossover")]
        op = str(rng.choice(ops))
        A = pool[rng.integers(len(pool))]
        B = [p for p in pool if p is not A][rng.integers(len(pool) - 1)] if kind == "crossover" else None
        f, meta = OP.OPS[op](sp, rng, A.f, None if B is None else B.f, None)
        if "skip" in meta:
            continue
        child, b = eng._make(f, "explore", op, (A.id,) + ((B.id,) if B else ()), meta)
        if child is None or np.array_equal(child.B, A.B) or (B is not None and np.array_equal(child.B, B.B)):
            continue
        parents_open = [A.desc[1]] + ([B.desc[1]] if B else [])
        new_open = all(child.desc[1] != o for o in parents_open)
        got = want[kind]["got"]
        if want[kind]["need_new"] > sum(1 for c in got if c[1]) and not new_open:
            continue                                            # first fill the opening-changing quota
        got.append((child, new_open))
    for kind, v in want.items():
        for child, new_open in v["got"]:
            ok = eng._fresh(child)
            entry = eng._enter(child, np.inf) if ok else "failed"
            kids.append({"id": child.id, "kind": kind, "op": child.op, "parents": child.parents, "new_openings": new_open,
                         "desc": child.desc, "D_mN": child.est if ok else None, "entry": entry})
    out["stages"]["explore"] = kids
    print("EXPLORE", json.dumps(kids, default=float), flush=True)

    # 3. refine the best census designs
    ref = []
    for e in sorted([s for s in eng.seeds if s.n > 0], key=lambda s: s.est)[: a.refine]:
        try:
            ref.append(eng.refine_one(e))
        except Exception:
            out["errors"].append(traceback.format_exc()[-1500:]); ref.append({"id": e.id, "result": "error"})
    out["stages"]["refine"] = ref
    print("REFINE", json.dumps(ref, default=float), flush=True)

    # 4. marks
    calls = [json.loads(l) for l in open(Path(a.store) / "calls.jsonl")]
    team = cen.get("original", {}).get("D_mN"); nopod = cen.get("lean", {}).get("D_mN")
    stages_ran = {c["call"] for c in calls if "error" not in c}
    out["marks"]["P1_every_stage_ran"] = {"fresh", "zero_morph", "morph", "adjoint"} <= stages_ran and not out["errors"]
    out["marks"]["P2a_team_within_1pct_of_449.24_whole"] = None if team is None else abs(2 * team / TEAM_STEADY_WHOLE_mN - 1) <= 0.01
    out["marks"]["P2b_nopod_worse_by_15_half"] = None if (team is None or nopod is None) else (nopod - team) >= 15.0
    out["marks"]["P3_each_refined_elite_decided_from_a_morphed_step"] = bool(ref) and all(
        r.get("result") in ("accepted", "rejected") and r.get("tried") for r in ref)
    out["marks"]["P4_opening_changing_crossover_and_mutation_ran"] = all(
        any(k["kind"] == kind and k["new_openings"] and k["D_mN"] is not None for k in kids) for kind in ("crossover", "mutation"))
    out["numbers"] = {"team_whole_mN": None if team is None else 2 * team, "nopod_minus_team_half_mN": None if None in (team, nopod) else nopod - team}
    out["wall_h"] = round((time.time() - t0) / 3600, 2)
    out["calls"] = calls
    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print("MARKS", json.dumps(out["marks"]), json.dumps(out["numbers"], default=float), flush=True)


def args_need(n):
    return {"n": n // 2, "need_new": 1, "got": []}


if __name__ == "__main__":
    sys.exit(main())
