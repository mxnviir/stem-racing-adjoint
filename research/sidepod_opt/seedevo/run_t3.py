"""Tests T3a-T3d on the known-answer bench (toy.py). Marks: SEED_EVOLUTION_PLAN.md section 7.

    python -m seedevo.run_t3 <out.json> [--problem 1] [--seeds 1 2 3 4 5] [--budget 300] [--smoke]

Arms (all start from the same census of 12 seeds, which is not counted in the budget):
    evo          crossover + mutation + map, 16 children and 4 control children a generation
    randpar      every child bred from census seeds (no selection)
    mutonly      evo without crossover
    polish       the adjoint only: refine the best seeds, nothing else
    evo_polish   evo for 70 % of the budget, then the adjoint on the best three
    memetic      the adjoint inside the loop: 9 children + 2 control + 3 elites refined a generation
    memetic_g    memetic, with sensitivities also guiding where mutations are placed
    evo60        evo with 60 % of the budget (the yardstick for T3c)
The score reported for an arm is the TRUE (noise-free) objective of the design it would hand over: the
archive's best by its own noisy estimate.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np

from . import operators as OP
from .engine import Config, Engine
from .space import ToySpace
from .toy import ToyEvaluator, make_seeds, make_target

POLISH = dict(n_explore=0, n_control=0, n_refine=3, refine_top=3)
ARMS = {
    "evo": dict(n_explore=16, n_control=4),
    "randpar": dict(n_explore=20, selection=False),
    "mutonly": dict(n_explore=16, n_control=4, ops=tuple(OP.MUTATION)),
    "polish": POLISH,
    "evo_polish": dict(n_explore=16, n_control=4),
    "memetic": dict(n_explore=9, n_control=2, n_refine=3, refine_top=2),
    "memetic_g": dict(n_explore=9, n_control=2, n_refine=3, refine_top=2, guided=True),
    "evo60": dict(n_explore=16, n_control=4),
}


AMEND = {"A": dict(tournament=3), "B": dict(tournament=3, duel_se=0.0, duel_min_runs=2, morph_explore=True)}


def run_arm(arm, sp, seeds, target, sigma, rho, seed, budget, tournament=1, reserve=0.0, amend=None):
    """tournament and reserve are amendment A (after instance 1 failed as registered): parents by tournament,
    and `reserve` runs kept back to re-run the best few before hand-over. 1 and 0 reproduce the registered run."""
    ev = ToyEvaluator(sp, target, rho=rho, sigma_fresh=sigma, seed=seed)
    floor = 0.1 * sigma
    extra = dict(AMEND[amend]) if amend else dict(tournament=tournament)
    eng = Engine(sp, ev, np.random.default_rng(seed), Config(floor=floor, **{**extra, **ARMS[arm]}))
    eng.census(seeds)
    eng.spent = 0.0
    Btot = budget * (0.6 if arm == "evo60" else 1.0)
    B = Btot - reserve
    switched = False
    idle = 0
    while eng.spent < B and idle < 3:
        before = eng.spent
        if arm == "evo_polish" and not switched and eng.spent >= 0.7 * B:
            eng.cfg = Config(floor=floor, **{**extra, **POLISH}); switched = True
        eng.generation(B)
        idle = idle + 1 if eng.spent == before else 0
    best = eng.handover(Btot) if reserve > 0 else eng.best()
    expl = [c["est"] for r in eng.log if r.get("gen", 0) > 0 for c in r.get("explore", [])]
    ctrl = [c["est"] for r in eng.log if r.get("gen", 0) > 0 for c in r.get("control", [])]
    half = eng.gen // 2
    e2 = [c["est"] for r in eng.log if r.get("gen", 0) > half for c in r.get("explore", [])]
    c2 = [c["est"] for r in eng.log if r.get("gen", 0) > half for c in r.get("control", [])]
    ref = [x for r in eng.log if r.get("gen", 0) > 0 for x in r.get("refine", [])]
    scored = [i for i in eng.all.values() if i.n > 0]
    kids = [i for i in scored if i.kind == "explore"]
    return {"arm": arm, "seed": seed, "rho": rho, "true_best": ev.true(best.f), "est_best": best.est, "best_kind": best.kind,
            "oracle_true": min(ev.true(i.f) for i in scored), "explore_true_mean": float(np.mean([ev.true(i.f) for i in kids])) if kids else None,
            "best_n": best.n,
            "best_openings": best.desc[1], "spent": eng.spent, "generations": eng.gen, "niches": len(eng.archive),
            "calls": ev.calls, "explore_mean_late": float(np.mean(e2)) if e2 else None,
            "control_mean_late": float(np.mean(c2)) if c2 else None, "n_explore": len(expl), "n_control": len(ctrl),
            "refine_accepted": sum(1 for x in ref if x.get("result") == "accepted"), "refine_tried": len(ref),
            "refine_gain": float(sum(x.get("delta", 0.0) for x in ref if x.get("result") == "accepted")),
            "op_stats": eng.op_stats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--problem", type=int, default=1)
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    ap.add_argument("--budget", type=float, default=300.0)
    ap.add_argument("--arms", nargs="+", default=list(ARMS))
    ap.add_argument("--rhos", type=float, nargs="+", default=[0.85])
    ap.add_argument("--tournament", type=int, default=1)
    ap.add_argument("--reserve", type=float, default=0.0)
    ap.add_argument("--amend", default=None, choices=[None, "A", "B"])
    a = ap.parse_args()
    sp = ToySpace()
    seeds = make_seeds(sp, 12, a.problem)
    target = make_target(sp, seeds, a.problem)
    ev0 = ToyEvaluator(sp, target)
    J = {k: ev0.true(f) for k, f in seeds.items()}
    sigma = 0.25 * float(np.std(list(J.values())))
    head = {"problem": a.problem, "budget": a.budget, "tournament": a.tournament, "reserve": a.reserve, "amend": a.amend, "sigma_fresh": sigma, "seed_true": J, "best_seed_true": min(J.values()),
            "target_openings": int(sp.describe(sp.build(target)["B"])[1]),
            "seed_openings": {k: int(sp.describe(sp.build(f)["B"])[1]) for k, f in seeds.items()}}
    print(json.dumps({k: v for k, v in head.items() if k != "seed_true"}), flush=True)
    rows = []
    for rho in a.rhos:
        for arm in a.arms:
            if rho != a.rhos[0] and arm not in ("memetic", "memetic_g", "polish", "evo_polish"):
                continue                                         # arms without an adjoint do not depend on rho
            for s in a.seeds:
                t = time.time()
                r = run_arm(arm, sp, seeds, target, sigma, rho, s, a.budget, a.tournament, a.reserve, a.amend)
                r["wall_s"] = round(time.time() - t, 1)
                rows.append(r)
                print(f"rho {rho:+.2f} {arm:11s} seed {s}: true {r['true_best']:.3f} (est {r['est_best']:.3f}) niches {r['niches']} "
                      f"gens {r['generations']} refine {r['refine_accepted']}/{r['refine_tried']} {r['wall_s']} s", flush=True)
    json.dump({"head": head, "rows": rows}, open(a.out, "w"), indent=1, default=float)


if __name__ == "__main__":
    sys.exit(main())
