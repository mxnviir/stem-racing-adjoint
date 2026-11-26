"""Tests TS and TC2 (SEED_EVOLUTION_PLAN.md): the evolution branch's mechanisms, ported, on the bench.
    python -m seedevo.run_port <out.json> --problem 14
TS : evolution (amendment B) vs the same with model-screened batches (screen.py).
TC2: evolve, then the gradient-free polish (no adjoint): random smooth moves vs CMA-ES over a lattice."""
import argparse, json, sys
import numpy as np
from . import run_t3e as R
from .run_t3 import AMEND, run_arm
from .space import ToySpace
from .toy import ToyEvaluator, make_seeds, make_target

AMEND["Bs"] = dict(AMEND["B"], screen=True)
R.ARM_CFG["gf_cma"] = {"adjoint": False, "gf_method": "cma"}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--problem", type=int, required=True)
    a = ap.parse_args(); sp = ToySpace(); pr = a.problem
    seeds = make_seeds(sp, 12, pr, open_share=0.5); target = make_target(sp, seeds, pr, force_open=True)
    J = [ToyEvaluator(sp, target).true(f) for f in seeds.values()]; sigma = 0.25 * float(np.std(J))
    rows = []
    for s in (1, 2, 3, 4, 5):
        for am, arm in (("B", "evo"), ("Bs", "evo")):
            r = run_arm(arm, sp, seeds, target, sigma, 0.85, s, 300, reserve=12, amend=am)
            rows.append({"test": "TS", "arm": "evo_screen" if am == "Bs" else "evo", "seed": s, "true_best": r["true_best"]})
        for arm in ("gf", "gf_cma"):
            r = R.run(arm, sp, seeds, target, sigma, "S4", s)
            rows.append({"test": "TC2", "arm": arm, "seed": s, "true_best": r["true_best"], "refine": f"{r['refine_acc']}/{r['refine_n']}"})
        print(pr, s, [(x["arm"], round(x["true_best"], 3)) for x in rows[-4:]], flush=True)
    json.dump({"problem": pr, "best_seed": min(J), "rows": rows}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    sys.exit(main())
