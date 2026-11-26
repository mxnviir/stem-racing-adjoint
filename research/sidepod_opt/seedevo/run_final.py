"""Test TF (SEED_EVOLUTION_PLAN.md): the chosen configuration on the bench, with the final operators.
    python -m seedevo.run_final <out.json> --problems 11 12 13
Arms: evo (evolution only), randpar (no selection), mutonly (no crossover), tc (evolution, then the end polish with the
trust check). Scenarios for tc: S1 (adjoint good everywhere) and S3 (good on closed pods, misleading on open ones).
Instances have half the seeds windowed and a windowed target. Amendment B, 12 runs reserved, budget 300."""
from __future__ import annotations
import argparse, json, sys
import numpy as np
from .engine import Config, Engine
from .run_t3 import AMEND, ARMS, POLISH
from .run_t3e import SCEN, run as run_e
from .space import ToySpace
from .toy import ToyEvaluator, make_seeds, make_target


def run_plain(arm, sp, seeds, target, sigma, seed, budget=300.0, reserve=12.0):
    ev = ToyEvaluator(sp, target, rho=0.85, sigma_fresh=sigma, seed=seed)
    eng = Engine(sp, ev, np.random.default_rng(seed), Config(floor=0.1 * sigma, **{**AMEND["B"], **ARMS[arm]}))
    eng.census(seeds); eng.spent = 0.0
    idle = 0
    while eng.spent < budget - reserve and idle < 3:
        b = eng.spent; eng.generation(budget - reserve); idle = idle + 1 if eng.spent == b else 0
    best = eng.handover(budget)
    return {"arm": arm, "scen": "-", "seed": seed, "true_best": ev.true(best.f)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--problems", type=int, nargs="+", default=[11, 12, 13])
    a = ap.parse_args(); sp = ToySpace(); rows = []
    for pr in a.problems:
        seeds = make_seeds(sp, 12, pr, open_share=0.5); target = make_target(sp, seeds, pr, force_open=True)
        J = [ToyEvaluator(sp, target).true(f) for f in seeds.values()]; sigma = 0.25 * float(np.std(J))
        for s in (1, 2, 3, 4, 5):
            for arm in ("evo", "randpar", "mutonly"):
                r = run_plain(arm, sp, seeds, target, sigma, s); r["problem"] = pr; rows.append(r)
            for sc in ("S1", "S3"):
                r = run_e("tc", sp, seeds, target, sigma, sc, s); r["problem"] = pr; rows.append(r)
            print(pr, s, [round(r["true_best"], 3) for r in rows[-5:]], flush=True)
    json.dump({"rows": rows}, open(a.out, "w"), indent=1, default=float)
    R = rows
    def get(arm, sc="-"): return {(r["problem"], r["seed"]): r["true_best"] for r in R if r["arm"] == arm and r["scen"] == sc}
    def per_inst(A, B, strict=True):
        out = []
        for pr in a.problems:
            k = [x for x in A if x[0] == pr]
            out.append(sum((A[x] < B[x]) if strict else (A[x] <= B[x]) for x in k))
        return out
    evo, rp, mo, s1, s3 = get("evo"), get("randpar"), get("mutonly"), get("tc", "S1"), get("tc", "S3")
    m = lambda d: float(np.mean(list(d.values())))
    print(f"means: evo {m(evo):.3f} randpar {m(rp):.3f} mutonly {m(mo):.3f} tc(S1) {m(s1):.3f} tc(S3) {m(s3):.3f}")
    f1 = [x >= 4 for x in per_inst(evo, rp)]; f2 = [x >= 4 for x in per_inst(evo, mo)]
    TFa = sum(a_ and b_ for a_, b_ in zip(f1, f2)) >= 2
    TFb = sum(x >= 4 for x in per_inst(s1, evo)) >= 2
    TFc = sum(per_inst(s3, evo, strict=False)) >= 10
    print(f"TFa evolution beats random parents and mutation-only (per instance {per_inst(evo, rp)} / {per_inst(evo, mo)}): {'PASS' if TFa else 'FAIL'}")
    print(f"TFb end polish with trust check beats evolution alone, good adjoint (per instance {per_inst(s1, evo)}): {'PASS' if TFb else 'FAIL'}")
    print(f"TFc no worse than evolution alone when the adjoint misleads on open pods ({sum(per_inst(s3, evo, strict=False))}/15): {'PASS' if TFc else 'FAIL'}")


if __name__ == "__main__":
    sys.exit(main())
