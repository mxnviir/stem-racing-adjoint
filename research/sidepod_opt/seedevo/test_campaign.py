"""Dry run of the campaign driver on the bench (no CFD): init -> batch -> results -> next, budget 300 runs after the
census, against the engine's evolution (amendment B without morph-scored children) on the same instance.
    python -m seedevo.test_campaign [problem] [seeds...]"""
import json, shutil, sys, tempfile
import numpy as np
from . import campaign as C
from .engine import Config, Engine
from .run_t3 import AMEND, ARMS
from .space import ToySpace
from .toy import ToyEvaluator, make_seeds, make_target

pr = int(sys.argv[1]) if len(sys.argv) > 1 else 2
rs = [int(x) for x in sys.argv[2:]] or [1, 2, 3]
sp = ToySpace()
seeds = make_seeds(sp, 12, pr); target = make_target(sp, seeds, pr)
J = [ToyEvaluator(sp, target).true(f) for f in seeds.values()]; sigma = 0.25 * float(np.std(J))
for r in rs:
    ev = ToyEvaluator(sp, target, sigma_fresh=sigma, seed=r)
    d = tempfile.mkdtemp()
    S = C.cmd_init(d, seeds, sp, n_explore=16, n_control=4, score="steady", rng_seed=r)
    spent, gens, problems = 0, 0, []
    req = json.loads(open(f"{d}/request.json").read())
    while True:
        res = []
        for c in req["cases"]:
            f = C.Store(d, sp).field(c["id"])
            res.append({"id": c["id"], "k": c["k"], "steady": ev.true(f) + ev.rng.normal(0, sigma), "converged": True})
        if req["gen"] > 0:
            spent += len(res)
        C.cmd_ingest(d, sp, res)
        if spent >= 288:
            break
        req = C.cmd_next(d, sp); gens += 1
    st = json.loads(open(f"{d}/state.json").read())
    # hand-over as the engine does: the best five by estimate get up to 3 runs (12 reserved)
    D = st["designs"]
    top = sorted(st["archive"].values(), key=lambda i: C.mean_score(D[i], "steady")[0])[:5]
    for i in top:
        while C.mean_score(D[i], "steady")[1] < 3:
            D[i]["runs"].append({"k": len(D[i]["runs"]), "steady": ev.true(C.Store(d, sp).field(i)) + ev.rng.normal(0, sigma), "converged": True})
    best = min(top, key=lambda i: C.mean_score(D[i], "steady")[0])
    drv = ev.true(C.Store(d, sp).field(best))
    lost = [i for i in D if D[i]["kind"] != "control" and not D[i]["runs"]]
    ev2 = ToyEvaluator(sp, target, sigma_fresh=sigma, seed=r)
    eng = Engine(sp, ev2, np.random.default_rng(r), Config(floor=0.1 * sigma, **{**AMEND["B"], "morph_explore": False, **ARMS["evo"]}))
    eng.census(seeds); eng.spent = 0
    while eng.spent < 288:
        b = eng.spent; eng.generation(288)
        if eng.spent == b: break
    engv = ev2.true(eng.handover(300).f)
    print(f"problem {pr} seed {r}: driver {drv:.3f} ({gens} batches, {len(D)} designs, niches {len(st['archive'])}, open duels {len(st['duels'])}, "
          f"designs never scored {len(lost)}) | engine {engv:.3f} | best seed {min(J):.3f}", flush=True)
    shutil.rmtree(d)
