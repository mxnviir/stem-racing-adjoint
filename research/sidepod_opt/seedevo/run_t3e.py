"""Test T3e (SEED_EVOLUTION_PLAN.md section 7): does the trust check protect the end polish from an adjoint whose
quality differs from design to design?

    python -m seedevo.run_t3e <out.json> [--problems 5 6 7] [--seeds 1 2 3 4 5]

Scenarios (the adjoint's correlation with the truth, per design; 'open' = the design has a through-opening):
    S1 good everywhere          0.85
    S2 good closed, useless open 0.85 closed / 0 open
    S3 good closed, misleading open 0.85 closed / -0.5 open
    S4 useless everywhere       0
    S5 misleading everywhere    -0.3
Arms (all: amendment B, 12 runs reserved for the hand-over, budget 300):
    evo        evolution only
    plain      evolve 70 %, then the adjoint polish as before (no check)
    tc         the same, with the trust check, stop rule and gradient-free fallback
    gf         the same, gradient-free polish only (no adjoint at all)
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from .engine import Config, Engine
from .run_t3 import AMEND, ARMS, POLISH
from .space import ToySpace
from .toy import ToyEvaluator, make_seeds, make_target

SCEN = {"S1": (0.85, 0.85), "S2": (0.85, 0.0), "S3": (0.85, -0.5), "S4": (0.0, 0.0), "S5": (-0.3, -0.3)}
ARM_CFG = {"evo": None, "plain": {}, "tc": {"trust_check": True}, "gf": {"adjoint": False}}


def run(arm, sp, seeds, target, sigma, scen, seed, budget=300.0, reserve=12.0):
    closed, opn = SCEN[scen]
    ev = ToyEvaluator(sp, target, rho=lambda ind: opn if ind.desc[1] > 0 else closed, sigma_fresh=sigma, seed=seed)
    floor = 0.1 * sigma
    base = {**AMEND["B"], **ARMS["evo"]}
    eng = Engine(sp, ev, np.random.default_rng(seed), Config(floor=floor, **base))
    eng.census(seeds); eng.spent = 0.0
    B = budget - reserve
    switched, idle = False, 0
    while eng.spent < B and idle < 3:
        before = eng.spent
        if ARM_CFG[arm] is not None and not switched and eng.spent >= 0.7 * B:
            eng.cfg = Config(floor=floor, **{**AMEND["B"], **POLISH, **ARM_CFG[arm]}); switched = True
        eng.generation(B)
        idle = idle + 1 if eng.spent == before else 0
    best = eng.handover(budget)
    ref = [x for r in eng.log if r.get("gen", 0) > 0 for x in r.get("refine", [])]
    tcs = [x["trust_check"] for x in ref if "trust_check" in x]
    return {"arm": arm, "scen": scen, "seed": seed, "true_best": ev.true(best.f), "best_open": int(best.desc[1]),
            "refine_n": len(ref), "refine_acc": sum(1 for x in ref if x.get("result") == "accepted"),
            "trust_checks": len(tcs), "trusted": sum(1 for t in tcs if t["trusted"]),
            "undecided": sum(1 for t in tcs if t["trusted"] is None),
            "stopped": sum(1 for x in ref if x.get("stopped")),
            "rho_seen_open_share": float(np.mean([o > 0 for o, _ in ev.rho_seen])) if ev.rho_seen else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--problems", type=int, nargs="+", default=[5, 6, 7])
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    ap.add_argument("--scens", nargs="+", default=list(SCEN)); ap.add_argument("--arms", nargs="+", default=list(ARM_CFG))
    ap.add_argument("--open-share", type=float, default=0.0)
    a = ap.parse_args()
    sp = ToySpace(); rows, heads = [], {}
    for pr in a.problems:
        seeds = make_seeds(sp, 12, pr, open_share=a.open_share); target = make_target(sp, seeds, pr, force_open=a.open_share > 0)
        J = [ToyEvaluator(sp, target).true(f) for f in seeds.values()]
        sigma = 0.25 * float(np.std(J))
        heads[pr] = {"sigma": sigma, "best_seed": min(J), "target_open": int(sp.describe(sp.build(target)["B"])[1]),
                     "seeds_open": int(sum(sp.describe(sp.build(f)["B"])[1] > 0 for f in seeds.values()))}
        print("problem", pr, json.dumps(heads[pr]), flush=True)
        for sc in a.scens:
            for arm in a.arms:
                if arm in ("evo", "gf") and sc != a.scens[0]:
                    continue                                          # no adjoint: the scenario does not matter
                for s in a.seeds:
                    r = run(arm, sp, seeds, target, sigma, sc, s); r["problem"] = pr; rows.append(r)
                    print(f"p{pr} {sc} {arm:5s} s{s}: {r['true_best']:.3f} open {r['best_open']} refine {r['refine_acc']}/{r['refine_n']} "
                          f"trusted {r['trusted']}/{r['trust_checks']} stopped {r['stopped']}", flush=True)
    json.dump({"heads": heads, "rows": rows}, open(a.out, "w"), indent=1, default=float)


if __name__ == "__main__":
    sys.exit(main())
