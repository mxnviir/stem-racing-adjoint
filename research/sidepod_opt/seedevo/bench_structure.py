"""Structure test (SEED_EVOLUTION_PLAN.md, "Structure test"): one evolution over numbers + field (A) against Bayesian
optimisation of the numbers with an inner field evolution per number-vector (B), on a known-answer bench. No CFD.

    python -m seedevo.bench_structure run <out.json> --instances 31 32 33 34 35 --seeds 1 2 3 4 5 [--arms ...]
    python -m seedevo.bench_structure verdict <out.json> [...]          # tables and the registered marks

THE BENCH (NOT a model of aerodynamics). A design is (x, f): x = 10 numbers in [0, 1] (8 dials, 2 switches, like the
layout + wing genes), f = a toy field (toy.py). Score (lower = better):

    J(x, f) = wf(x) * M(f, T(x)) + g(x)            measured with noise N(0, sigma)

  * M(f, T) = toy.py's weighted mismatch between the built field and a target occupancy T;
  * interaction: the target depends on the numbers. x0 moves it along the car (+-6 mm), x1 stretches it along the car
    (+-15 %), x2 moves it up/down (+-2.5 mm), switch s1 (x8) adds a through-window to it; wf(x) = 0.75 + 0.5 * x3 is
    how much the field matters at this layout. So the best field depends on the numbers, and a field evolved at one
    layout is not the best at another;
  * g(x) = A * [sum_i lam_i z_i^2 + 0.05 * sum_i (1 - cos(3 pi z_i))] + A * (d1 s1 + d2 s2), z = R (x_dials - c):
    a rotated, ill-conditioned (lam 0.3-3), slightly rippled bowl, centre c in [0.2, 0.8]^8, plus switch offsets
    d1, d2 in +-[0.1, 0.4]. A is set so that the median of g - min g over random x is 2.0 (about the gain field
    evolution makes on the toy in a few hundred runs: the two parts matter about equally);
  * known answer: J* = min g = A * (min(0, d1) + min(0, d2)) (the field term is >= 0 and ~0 at f = T(x*));
  * noise sigma = 0.3 = 15 % of the typical gain of 2.0 (real: 0.6 mN against gains of a few mN).

THE STRUCTURES. Every evaluation counts (initial designs too); evaluations go in batches of 20; what a structure hands
over at a budget is its lowest mean measured design among those evaluated within the budget; its score is that
design's TRUE J (regret = J - J*). Neither structure uses the total budget, so one run to 400 evaluations gives
the hand-overs at 100, 200 and 400 exactly as three separate runs would.

  A  one evolution (the campaign driver's rules, campaign.py, without control children): the map (niche = pod volume x
     openings) holds one design per niche; a batch = the re-runs that open duels need (a child that looks better than
     its niche's holder: both brought to 2 runs, lower mean holds), then new children up to 20. A child: parents by a
     tournament of 3 from the map; crossover (share 0.5): a field crossover operator and blend crossover of the
     numbers (BLX-0.25, switches from either parent); otherwise a mutation that changes the field (field operator),
     the numbers (Gaussian step, sd 0.03-0.2 log-uniform, switch flips p 0.15) or both, 1/3 each. Screening
     (screen.py, as in the campaign): from batch 2 on, 4 x 20 unbuilt candidates are bred and the GP (Matern ARD on
     [8 field PCs, pod volume, the 10 numbers]) + expected improvement + kriging believer picks the 20.
     `Aplain` = A without screening (reported, not marked).
  B  BO outside, evolution inside, split q x m: each outer round (= 100 evaluations = 5 batches) picks q number-vectors
     (round 1: Sobol; then a GP on (x, best inner result) with EI + kriging believer over 4000 random and 4000
     near-best candidates, as Campaign.ask in the evolution branch's layout search); each picked x gets an inner field
     evolution of m evaluations in 5 inner generations of 20/q children (all q run side by side in one batch of 20):
     generation 1 = the 20/q best distinct fields measured so far at any x (round 1: random seeds), later generations
     = children bred from that x's inner designs (tournament of 3, crossover share 0.5, the field operators). The outer
     GP is fed the best inner result (lowest measurement) of each x.
     `B5x20` (primary), `B10x10` (the registered alternative), `B2x50` (reported, not marked).
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")          # one thread per worker (4 workers on 4 cores)

import argparse
import hashlib
import json
import sys
import time
from functools import lru_cache

import numpy as np
from scipy import ndimage

from . import operators as OP
from .space import ToySpace
from .toy import _open_window, make_seeds, make_target, occ, ToyEvaluator

D_DIAL, D = 8, 10                   # 8 dials + 2 switches (x8 = s1, interacts with the target; x9 = s2, g only)
SIGMA, GAIN = 0.3, 2.0
BATCH, BUDGET, CHECKS = 20, 400, (100, 200, 400)


# ------------------------------------------------------------------ the instance
class Instance:
    def __init__(self, pr):
        self.pr = pr
        sp = self.sp = ToySpace()
        self.seeds = make_seeds(sp, 12, pr, open_share=0.5)
        T0 = make_target(sp, self.seeds, pr)
        T1 = None
        for k in range(40):
            T1 = _open_window(sp, np.random.default_rng(8800 + 100 * pr + k), T0)
            if T1 is not None:
                break
        self.variant = "window"
        if T1 is None:              # amendment (held-out run): a thin target takes no window; then any legal cut
            rng1 = np.random.default_rng(8900 + pr)         # (window or groove) that removes >= 10 % of the pod
            v0 = sp.build(T0)["pod_mm3"]
            for k in range(400):
                g, m = OP.cut(sp, rng1, T0, None, None)
                bb = sp.build(g)
                if bb["ok"] and bb["pod_mm3"] <= 0.9 * v0:
                    T1, self.variant = bb["f"], "cut:" + m.get("kind", "")
                    break
        if T1 is None:
            raise RuntimeError("no target variant")
        self.occT = [occ(T0, sp.h), occ(T1, sp.h)]
        self.w = ToyEvaluator(sp, T0).w
        self.idx = np.indices(sp.shape).astype(float)
        rng = np.random.default_rng(5000 + pr)
        self.c = rng.uniform(0.2, 0.8, D_DIAL)
        self.R = np.linalg.qr(rng.standard_normal((D_DIAL, D_DIAL)))[0]
        self.lam = np.exp(rng.uniform(np.log(0.3), np.log(3.0), D_DIAL))
        self.d = rng.choice([-1.0, 1.0], 2) * rng.uniform(0.1, 0.4, 2)
        self.A = 1.0
        X = np.random.default_rng(1).random((20000, D)); X[:, 8:] = (X[:, 8:] >= 0.5)
        self.A = GAIN / float(np.median(self.g(X) - self.g_star()))

    # numbers
    def g(self, x):
        x = np.atleast_2d(x)
        z = (x[:, :D_DIAL] - self.c) @ self.R.T
        base = (self.lam * z ** 2).sum(1) + 0.05 * (1 - np.cos(3 * np.pi * z)).sum(1)
        s = (x[:, 8:] >= 0.5).astype(float)
        out = self.A * (base + s @ self.d)
        return out if len(out) > 1 else float(out[0])

    def g_star(self):
        return float(self.A * np.minimum(self.d, 0.0).sum())

    # the interaction: where the target sits for these numbers
    def target(self, x):
        sp = self.sp
        dx, sx, dz = 6.0 * (2 * x[0] - 1), 1.0 + 0.15 * (2 * x[1] - 1), 2.5 * (2 * x[2] - 1)
        cx = 0.5 * sp.shape[0] * sp.h
        Xs = cx + (sp.X - cx - dx) / sx
        Zs = sp.Z - dz
        coords = np.array([Xs / sp.h - 0.5, self.idx[1], Zs / sp.h - 0.5])
        return ndimage.map_coordinates(self.occT[int(x[8] >= 0.5)], coords, order=1, mode="nearest")

    def field_part(self, x, f):
        return float((self.w * np.abs(occ(f, self.sp.h) - self.target(x))).sum() * self.sp.h ** 3 / 1e3)

    def true(self, x, f):
        wf = 0.75 + 0.5 * x[3]
        return wf * self.field_part(x, f) + self.g(x)


@lru_cache(maxsize=8)
def instance(pr):
    return Instance(pr)


def snap(x):
    x = np.clip(np.asarray(x, float), 0.0, 1.0).copy()
    x[8:] = (x[8:] >= 0.5).astype(float)
    return x


def key_of(x, B):
    return hashlib.sha1(np.packbits(np.asarray(B, bool)).tobytes() + np.round(x, 4).tobytes()).hexdigest()[:16]


# ------------------------------------------------------------------ bookkeeping shared by both structures
class Run:
    """Every evaluated design; the noisy instrument; hand-over at the checkpoints."""

    def __init__(self, inst, seed, tag):
        self.inst, self.sp = inst, inst.sp
        self.rng = np.random.default_rng(seed * 7919 + inst.pr * 104729 + sum(map(ord, tag)))
        self.noise = np.random.default_rng(seed * 31 + inst.pr * 1009)
        self.designs, self.spent, self.checks = [], 0, {}
        self.seen = set()

    def new(self, x, f, B, kind, parents=(), op=""):
        d = {"id": len(self.designs), "x": snap(x), "f": f, "B": B, "kind": kind, "parents": list(parents), "op": op,
             "runs": [], "desc": self.sp.describe(B)}
        d["niche"] = self.sp.niche(d["desc"])
        self.designs.append(d)
        self.seen.add(key_of(d["x"], B))
        return d

    def evaluate(self, batch):
        """One batch of <= 20 evaluations (designs, may repeat for re-runs)."""
        assert len(batch) <= BATCH
        for d in batch:
            d["runs"].append(self.inst.true(d["x"], d["f"]) + self.noise.normal(0.0, SIGMA))
            self.spent += 1
            if self.spent in CHECKS + (BATCH,):                  # (20: the starting level, reported)
                self.checks[self.spent] = self.handover()

    @staticmethod
    def est(d):
        return float(np.mean(d["runs"])) if d["runs"] else np.inf

    def handover(self):
        scored = [d for d in self.designs if d["runs"]]
        best = min(scored, key=self.est)
        x = best["x"]
        fp = self.inst.field_part(x, best["f"])
        J = self.inst.true(x, best["f"])
        trues = [self.inst.true(d["x"], d["f"]) for d in scored]
        return {"true": J, "regret": J - self.inst.g_star(), "est": self.est(best), "n_runs": len(best["runs"]),
                "field_part": (0.75 + 0.5 * x[3]) * fp, "num_regret": self.inst.g(x) - self.inst.g_star(),
                "oracle_regret": float(min(trues)) - self.inst.g_star(), "designs": len(scored),
                "x_dist": float(np.linalg.norm(x[:D_DIAL] - self.inst.c)), "s": x[8:].tolist(),
                "s_best": (self.inst.d < 0).astype(float).tolist()}

    # field breeding (the existing operators and the toy builder)
    def breed_field(self, fa, fb, crossover):
        names = list(OP.CROSSOVER) if crossover else list(OP.MUTATION)
        for _ in range(6):
            name = str(self.rng.choice(names))
            f, meta = OP.OPS[name](self.sp, self.rng, fa, fb if crossover else None, None)
            if "skip" in meta:
                continue
            b = self.sp.build(f)
            if b["ok"]:
                return b["f"], b["B"], name
        return None


def tournament(rng, pool, k=3):
    idx = rng.choice(len(pool), min(k, len(pool)), replace=False)
    return min((pool[i] for i in idx), key=Run.est)


# ------------------------------------------------------------------ A: one evolution over numbers + field
def run_A(inst, seed, screen=True):
    R = Run(inst, seed, "A" if screen else "Aplain")
    rng, sp = R.rng, R.sp
    from scipy.stats import qmc
    X0 = qmc.Sobol(D, seed=seed).random(32)[:BATCH]
    names = list(inst.seeds)
    order = names + list(rng.choice(names, BATCH - len(names), replace=False))
    first = []
    for x, nm in zip(X0, order):
        b = sp.build(inst.seeds[nm])
        first.append(R.new(x, b["f"], b["B"], "seed", op=nm))
    R.evaluate(first)
    archive, duels, placed = {}, [], set()
    screen_noise = []

    def update():
        for c in list(duels):
            ch, inc = c
            if len(ch["runs"]) >= 2 and len(inc["runs"]) >= 2:
                duels.remove(c)
                if R.est(ch) < R.est(inc) and archive.get(ch["niche"]) is inc:
                    archive[ch["niche"]] = ch
        busy = {id(d) for c in duels for d in c}
        for d in R.designs:
            if d["id"] in placed or not d["runs"]:
                continue
            placed.add(d["id"])
            inc = archive.get(d["niche"])
            if inc is None:
                archive[d["niche"]] = d
            elif id(inc) in busy or id(d) in busy:
                continue
            elif R.est(d) < R.est(inc):
                duels.append((d, inc)); busy |= {id(d), id(inc)}

    def propose(pool):
        a = tournament(rng, pool)
        others = [p for p in pool if p["niche"] != a["niche"]] or [p for p in pool if p is not a]
        if others and rng.random() < 0.5:                    # crossover: field and numbers
            b = tournament(rng, others)
            r = R.breed_field(a["f"], b["f"], True)
            if r is None:
                return None
            t = rng.uniform(-0.25, 1.25, D)
            x = a["x"] + t * (b["x"] - a["x"])
            pick = rng.random(2) < 0.5
            x[8:] = np.where(pick, a["x"][8:], b["x"][8:])
            return snap(x), r[0], r[1], (a["id"], b["id"]), r[2]
        mode = int(rng.integers(3))                          # 0 field, 1 numbers, 2 both
        x, f, B, op = a["x"].copy(), a["f"], a["B"], "numbers"
        if mode in (0, 2):
            r = R.breed_field(a["f"], None, False)
            if r is None:
                return None
            f, B, op = r
        if mode in (1, 2):
            sd = np.exp(rng.uniform(np.log(0.03), np.log(0.2)))
            x[:D_DIAL] += sd * rng.standard_normal(D_DIAL)
            flip = rng.random(2) < 0.15
            x[8:] = np.where(flip, 1.0 - x[8:], x[8:])
            op = op + "+numbers" if mode == 2 else "numbers"
        return snap(x), f, B, (a["id"],), op

    while R.spent < BUDGET:
        update()
        batch = []
        for ch, inc in duels:
            for d in (ch, inc):
                if len(d["runs"]) < 2 and d not in batch:
                    batch.append(d)
        n = BATCH - len(batch)
        pool = list(archive.values())
        nscored = sum(1 for d in R.designs if d["runs"])
        cands, tries = [], 0
        want = 4 * n if (screen and nscored >= 12) else n
        local = set()
        while len(cands) < want and tries < 20 * want:
            tries += 1
            c = propose(pool)
            if c is None:
                continue
            k = key_of(c[0], c[2])
            if k in R.seen or k in local:
                continue
            local.add(k); cands.append(c)
        if screen and nscored >= 12 and len(cands) > n:
            from .screen import Screen, block_occupancy
            scored = [d for d in R.designs if d["runs"]]
            for d in scored:
                if "occ" not in d:
                    d["occ"] = block_occupancy(sp, d["f"])
            Bs = np.array([d["occ"] for d in scored]); Bc = np.array([block_occupancy(sp, c[1]) for c in cands])
            vol = lambda f: float(((f > 0) & sp.region).sum()) * sp.h ** 3 / 1e3
            xs = lambda x: (np.asarray(x) - 0.5) / 0.29
            sc = Screen(seed=int(rng.integers(1 << 30)))
            sc.fit_basis(np.vstack([Bs, Bc]))
            Xs = sc.feats(Bs, np.array([np.r_[vol(d["f"]), xs(d["x"])] for d in scored]))
            Xc = sc.feats(Bc, np.array([np.r_[vol(c[1]), xs(c[0])] for c in cands]))
            order = sc.pick(Xs, np.array([R.est(d) for d in scored]), Xc, n)
            screen_noise.append(sc.last["noise"])
            cands = [cands[k] for k in order]
        for x, f, B, parents, op in cands[:n]:
            batch.append(R.new(x, f, B, "child", parents, op))
        R.evaluate(batch[: min(BATCH, BUDGET - R.spent)])
    ops = {}
    for d in R.designs:
        if d["kind"] == "child":
            ops[d["op"]] = ops.get(d["op"], 0) + 1
    return {"checks": R.checks, "niches": len(archive), "screen_noise_mean": float(np.mean(screen_noise)) if screen_noise else None,
            "ops": ops}


# ------------------------------------------------------------------ B: BO outside, evolution inside
def outer_pick(rng, X, y, q):
    from scipy.stats import norm
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
    X, y = np.asarray(X), np.asarray(y)
    mu0, sd0 = y.mean(), y.std() + 1e-12
    kern = ConstantKernel(1.0, (0.05, 20.0)) * Matern(length_scale=np.full(D, 0.5), length_scale_bounds=(0.05, 20.0), nu=2.5) \
        + WhiteKernel(0.05, (1e-4, 1.0))
    gp = GaussianProcessRegressor(kern, normalize_y=False, n_restarts_optimizer=6, random_state=0).fit(X, (y - mu0) / sd0)
    C = np.vstack([rng.random((4000, D)), np.clip(X[np.argmin(y)][None] + 0.08 * rng.standard_normal((4000, D)), 0, 1)])
    C[:, 8:] = (C[:, 8:] >= 0.5)
    fixed = GaussianProcessRegressor(gp.kernel_, optimizer=None, normalize_y=False)
    Xa, ya = X.copy(), (y - mu0) / sd0
    best, picks = ya.min(), []
    for _ in range(q):
        fixed.fit(Xa, ya)
        m, s = fixed.predict(C, return_std=True)
        z = (best - m) / np.maximum(s, 1e-9)
        ei = (best - m) * norm.cdf(z) + s * norm.pdf(z)
        k = int(np.argmax(ei))
        picks.append(C[k].copy())
        Xa = np.vstack([Xa, C[k]]); ya = np.append(ya, m[k])
        C = np.delete(C, k, axis=0)
    return picks


def run_B(inst, seed, q, m):
    assert q * m == 100 and BATCH % q == 0 and m % (BATCH // q) == 0
    w, gens = BATCH // q, m // (BATCH // q)
    R = Run(inst, seed, f"B{q}x{m}")
    rng, sp = R.rng, R.sp
    from scipy.stats import qmc
    sob = qmc.Sobol(D, seed=seed).random(32)
    Xo, yo = [], []
    rnd = 0
    while R.spent < BUDGET:
        if rnd == 0:
            xs = [snap(x) for x in sob[:q]]
        else:
            xs = [snap(x) for x in outer_pick(rng, Xo, yo, q)]
        inner = [[] for _ in xs]
        # inner generation 1: warm-start fields
        if rnd == 0:
            names = list(inst.seeds)
            starts = [[sp.build(inst.seeds[nm]) for nm in rng.choice(names, w, replace=False)] for _ in xs]
            starts = [[(b["f"], b["B"]) for b in s] for s in starts]
        else:
            ranked, seenB = [], set()
            for d in sorted((d for d in R.designs if d["runs"]), key=Run.est):
                h = hashlib.sha1(np.packbits(d["B"]).tobytes()).hexdigest()
                if h not in seenB:
                    seenB.add(h); ranked.append((d["f"], d["B"]))
                if len(ranked) >= w:
                    break
            starts = [ranked for _ in xs]
        batch = []
        for j, x in enumerate(xs):
            for f, B in starts[j]:
                d = R.new(x, f, B, "warm" if rnd else "seed")
                inner[j].append(d); batch.append(d)
        R.evaluate(batch)
        for _g in range(1, gens):
            batch = []
            for j, x in enumerate(xs):
                pool = inner[j]
                made, tries = 0, 0
                while made < w and tries < 30 * w:
                    tries += 1
                    a = tournament(rng, pool)
                    others = [p for p in pool if p is not a]
                    cross = bool(others) and rng.random() < 0.5
                    b = tournament(rng, others) if cross else None
                    r = R.breed_field(a["f"], None if b is None else b["f"], cross)
                    if r is None or key_of(x, r[1]) in R.seen:
                        continue
                    d = R.new(x, r[0], r[1], "inner", (a["id"],) + ((b["id"],) if b is not None else ()), r[2])
                    batch.append(d); made += 1
                inner[j].extend(batch[-made:] if made else [])
            R.evaluate(batch)
        for j, x in enumerate(xs):
            Xo.append(x); yo.append(min(R.est(d) for d in inner[j]))
        rnd += 1
    return {"checks": R.checks, "outer_points": len(Xo)}


ARMS = {"A": lambda i, s: run_A(i, s, True), "Aplain": lambda i, s: run_A(i, s, False),
        "B5x20": lambda i, s: run_B(i, s, 5, 20), "B10x10": lambda i, s: run_B(i, s, 10, 10),
        "B2x50": lambda i, s: run_B(i, s, 2, 50)}


def job(args):
    arm, pr, seed = args
    t = time.time()
    inst = instance(pr)
    r = ARMS[arm](inst, seed)
    r.update(arm=arm, instance=pr, seed=seed, wall_s=round(time.time() - t, 1))
    print(f"{arm:7s} inst {pr} seed {seed}: " + "  ".join(f"{b}: {r['checks'][b]['regret']:.3f}" for b in CHECKS)
          + f"  ({r['wall_s']} s)", flush=True)
    return r


# ------------------------------------------------------------------ verdict
MARK = 18          # of 25 pairs: one-sided sign test p = 0.022
PRIMARY = ("A", "B5x20", "B10x10")


def verdict(rows):
    from scipy.stats import binomtest, wilcoxon
    get = lambda arm, b: {(r["instance"], r["seed"]): r["checks"][str(b)]["regret"] if str(b) in r["checks"] else r["checks"][b]["regret"]
                          for r in rows if r["arm"] == arm}
    arms = [a for a in ARMS if any(r["arm"] == a for r in rows)]
    out = {"means": {}, "pairs": {}}
    for b in CHECKS:
        out["means"][b] = {a: (float(np.mean(list(get(a, b).values()))), float(np.std(list(get(a, b).values()), ddof=1)))
                           for a in arms}
        for v in [a for a in arms if a != "A"]:
            A, Bv = get("A", b), get(v, b)
            k = sorted(set(A) & set(Bv))
            wa = sum(A[i] < Bv[i] for i in k); wb = sum(Bv[i] < A[i] for i in k)
            diff = np.array([A[i] - Bv[i] for i in k])
            per = {}
            for i in k:
                per.setdefault(i[0], [0, 0]); per[i[0]][0] += A[i] < Bv[i]; per[i[0]][1] += Bv[i] < A[i]
            out["pairs"][f"{b}:{v}"] = {"n": len(k), "A_wins": wa, "B_wins": wb, "mean_diff_A_minus_B": float(diff.mean()),
                                        "se_diff": float(diff.std(ddof=1) / np.sqrt(len(k))),
                                        "sign_p_A": float(binomtest(wa, wa + wb, 0.5, "greater").pvalue) if wa + wb else 1.0,
                                        "sign_p_B": float(binomtest(wb, wa + wb, 0.5, "greater").pvalue) if wa + wb else 1.0,
                                        "wilcoxon_p": float(wilcoxon(diff).pvalue) if np.any(diff) else 1.0,
                                        "per_instance": {str(p): v_ for p, v_ in sorted(per.items())}}
    # the registered decision rule
    beats = lambda b, v, who: out["pairs"].get(f"{b}:{v}", {}).get(f"{who}_wins", 0) >= MARK
    Bvars = [v for v in ("B5x20", "B10x10") if v in arms]
    A_at = [b for b in CHECKS if beats(b, "B5x20", "A") and not any(beats(b, v, "B") for v in Bvars)]
    B_at = {v: [b for b in CHECKS if beats(b, v, "B")] for v in Bvars}
    A_lost = [b for b in CHECKS if any(beats(b, v, "B") for v in Bvars)]
    Bwin = [v for v in Bvars if len(B_at[v]) >= 2 and 400 in B_at[v] and not any(beats(b, v, "A") for b in CHECKS)]
    if len(A_at) >= 2 and 400 in A_at and not A_lost:
        dec = "A"
    elif Bwin:
        dec = "B (" + ", ".join(Bwin) + ")"
    elif A_at and A_lost:
        dec = f"budget-dependent: A at {A_at}, B at {A_lost}"
    elif A_at:
        dec = f"A ahead at {A_at} only (short of the rule): keep A (tie rule)"
    elif A_lost:
        dec = f"B ahead at {A_lost} only (short of the rule): keep A (tie rule), flagged"
    else:
        dec = "no difference shown: keep A (tie rule)"
    out["decision"] = {"A_beats_B_primary_at": A_at, "B_beats_A_at": B_at, "decision": dec}
    return out


def print_verdict(V):
    arms = list(next(iter(V["means"].values())))
    for b in CHECKS:
        print(f"\nbudget {b}: mean regret (sd)  " + "  ".join(f"{a} {m:.3f} ({s:.3f})" for a, (m, s) in V["means"][b].items()))
        for k, p in V["pairs"].items():
            if k.startswith(f"{b}:"):
                print(f"   A vs {k.split(':')[1]:7s}: A wins {p['A_wins']}/{p['n']}, B wins {p['B_wins']}, mean A-B {p['mean_diff_A_minus_B']:+.3f} "
                      f"(se {p['se_diff']:.3f}), sign p(A) {p['sign_p_A']:.3g} p(B) {p['sign_p_B']:.3g}, wilcoxon {p['wilcoxon_p']:.3g}, "
                      f"per instance {p['per_instance']}")
    print("\n" + json.dumps(V["decision"]))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("out"); r.add_argument("--instances", type=int, nargs="+", default=[31, 32, 33, 34, 35])
    r.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5]); r.add_argument("--arms", nargs="+", default=list(ARMS))
    r.add_argument("--workers", type=int, default=4)
    v = sub.add_parser("verdict"); v.add_argument("files", nargs="+")
    a = ap.parse_args()
    if a.cmd == "run":
        jobs = [(arm, pr, s) for pr in a.instances for s in a.seeds for arm in a.arms]
        jobs.sort(key=lambda j: (j[0] not in ("A",), j))          # the slow arm first
        if a.workers > 1:
            from multiprocessing import Pool
            with Pool(a.workers) as p:
                rows = list(p.imap_unordered(job, jobs))
        else:
            rows = [job(j) for j in jobs]
        heads = {}
        for pr in a.instances:
            I = instance(pr)
            heads[pr] = {"variant": I.variant, "A": I.A, "c": I.c.tolist(), "lam": I.lam.tolist(), "d": I.d.tolist(), "g_star": I.g_star(),
                         "sigma": SIGMA, "best_seed_field": min(I.field_part(np.full(D, 0.5), I.sp.build(f)["f"]) for f in I.seeds.values())}
        json.dump({"head": heads, "rows": rows}, open(a.out, "w"), indent=1, default=float)
        V = verdict(rows); print_verdict(V)
    else:
        rows = [r for f in a.files for r in json.load(open(f))["rows"]]
        V = verdict(rows); print_verdict(V)
        return V


if __name__ == "__main__":
    sys.exit(main())
