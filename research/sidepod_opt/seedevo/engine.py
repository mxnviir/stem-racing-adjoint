"""Seed evolution with the adjoint inside the loop (SEED_EVOLUTION_PLAN.md).

One generation spends its CFD runs on two kinds of children:

  explore   crossover / mutation children of archive members (operators.py). Any topology. Each is scored
            on a FRESH mesh (noise sigma_fresh) and enters the map by the duel rule below; with morph_explore,
            a child that is a small move of its parent with the same topology is scored on the parent's
            morphed mesh instead, like a refinement.
  refine    the adjoint's move on an archive member (an elite): the sensitivity is solved once per elite,
            steps of two sizes are built, and each is scored on the elite's own mesh MORPHED onto the child
            (noise sigma_morph, far smaller). The best step is kept only if CFD says it is better by the
            margin; the refined design then REPLACES the elite (Lamarckian), so later crossover inherits it.
            A failed step halves that elite's step size. The adjoint proposes; CFD decides.
  control   (test T4) children bred by the same operators from census seeds only; scored, never archived.

The adjoint is used a second way: an elite's sensitivity map, once solved, guides where its mutations are
placed (cuts where the surface wants in, material where it wants out).

Scores: lower is better. An individual's estimate is the mean of its own fresh runs, pooled with what it
inherits through a refinement chain (the parent's estimate plus the morph-measured change, carrying the
parent's run count). Duel rule (adaptive sampling): a child that looks better than its niche's holder gets
re-runs, as does the holder, until both have the same count (max_runs), and replaces it at >= 2 SE.

The evaluator supplies fresh(ind), morph(parent, child), adjoint(ind) and their costs; the engine never
sees how they are computed (toy objective, coarse CFD, or runners).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import operators as OP


@dataclass
class Ind:
    id: int
    f: np.ndarray
    B: np.ndarray
    desc: tuple
    niche: tuple
    kind: str                       # seed | explore | refine | control
    op: str = ""
    parents: tuple = ()
    fresh: list = field(default_factory=list)
    base: float | None = None       # estimate inherited through refinement (parent estimate + morph delta)
    n_base: int = 0
    grad: np.ndarray | None = None  # cached adjoint sensitivity on the grid
    step: float | None = None       # this elite's current refinement step (mm)
    depth: float = 0.0              # morphed distance since its last fresh mesh (mm)
    anchor: int | None = None       # the individual whose mesh this one's morph lineage hangs from
    meta: dict = field(default_factory=dict)

    @property
    def n(self):
        return self.n_base + len(self.fresh)

    @property
    def est(self):
        if self.n == 0:
            return np.inf
        return ((self.base or 0.0) * self.n_base + sum(self.fresh)) / self.n


@dataclass
class Config:
    n_explore: int = 12
    n_control: int = 0
    n_refine: int = 0               # elites refined per generation (each: one adjoint if not cached, two steps)
    refine_top: int = 3             # of which the best this many; the rest drawn from other niches
    step0: float = 1.0
    step_min: float = 0.125
    floor: float = 0.0              # a refinement must beat its parent by at least this (and 3 SE of the morph)
    max_runs: int = 3
    crossover_share: float = 0.5
    ops: tuple = tuple(OP.OPS)
    guided: bool = False            # use cached sensitivities to place mutations
    selection: bool = True          # False: every explore child is bred from census seeds (random-parents arm)
    max_depth: float = 2.0          # morph range of one mesh (mm); beyond it the elite is re-run fresh
    tournament: int = 1             # parents: best of this many drawn from the map (1 = uniform over niches)
    duel_se: float = 2.0            # a challenger replaces a niche's holder if better by this many SE ...
    duel_min_runs: int = 1          # ... once both have at least this many fresh-equivalent runs
    morph_explore: bool = False     # score a small, topology-keeping explore child on its parent's morphed mesh
    handover_top: int = 5           # before hand-over, the best this many by estimate are run up to max_runs
    build_tries: int = 6


class Engine:
    def __init__(self, space, evaluator, rng, cfg: Config):
        self.space, self.ev, self.rng, self.cfg = space, evaluator, rng, cfg
        self.archive: dict = {}
        self.seeds: list = []
        self.all: dict = {}
        self.spent = 0.0
        self.log: list = []
        self.gen = 0
        self._next = 0
        self.op_stats = {k: [0, 0, 0] for k in cfg.ops}            # asked, legal, entered

    # ---------------------------------------------------------------- individuals
    def _make(self, f, kind, op="", parents=(), meta=None):
        b = self.space.build(f)
        if not b["ok"]:
            return None, b
        desc = self.space.describe(b["B"])
        ind = Ind(self._next, b["f"], b["B"], desc, self.space.niche(desc), kind, op, tuple(parents), meta=meta or {})
        ind.meta.update(changed_mm3=b["changed_mm3"], pod_mm3=b["pod_mm3"], build=b.get("info", {}))
        if "mesh" in b:
            ind.meta["mesh"] = b["mesh"]; ind.meta["built"] = b.get("built")
        self._next += 1
        self.all[ind.id] = ind
        return ind, b

    def _fresh(self, ind):
        v = self.ev.fresh(ind, len(ind.fresh))
        self.spent += self.ev.cost_fresh
        if v is None:
            return False
        ind.fresh.append(float(v)); ind.depth = 0.0; ind.anchor = ind.id
        return True

    def _se(self, a, b):
        return self.ev.sigma_fresh * np.sqrt(1.0 / max(a.n, 1) + 1.0 / max(b.n, 1))

    def _enter(self, child, budget):
        """Duel for the child's niche. Returns new | replaced | rejected. Both sides are brought to the same
        run count m (at least duel_min_runs); the child wins if better by duel_se SE; if not and it still
        looks better, m grows by one until max_runs."""
        cfg = self.cfg
        inc = self.archive.get(child.niche)
        if inc is None:
            self.archive[child.niche] = child
            return "new"
        m = min(cfg.max_runs, max(child.n, inc.n, cfg.duel_min_runs))
        while True:
            if child.est >= inc.est:
                return "rejected"
            low = child if child.n < m else (inc if inc.n < m else None)
            if low is None:
                if child.est <= inc.est - cfg.duel_se * self._se(child, inc):
                    self.archive[child.niche] = child
                    return "replaced"
                if m >= cfg.max_runs:
                    return "rejected"
                m += 1
                continue
            if self.spent >= budget or not self._fresh(low):
                return "rejected"

    # ---------------------------------------------------------------- census
    def census(self, seed_fields: dict):
        for name, f in seed_fields.items():
            ind, b = self._make(f, "seed", meta={"name": name})
            if ind is None:
                self.log.append({"gen": 0, "seed": name, "illegal": True})
                continue
            if not self._fresh(ind):
                continue
            ind.step = self.cfg.step0
            self.seeds.append(ind)
            r = self._enter(ind, np.inf)
            self.log.append({"gen": 0, "seed": name, "id": ind.id, "est": ind.est, "niche": ind.niche, "entry": r})

    # ---------------------------------------------------------------- variation
    def _breed(self, pool, kind):
        cfg, rng = self.cfg, self.rng
        k = cfg.tournament if kind == "explore" and cfg.selection else 1       # control children: uniform, always

        def pick(cands):
            idx = rng.choice(len(cands), min(k, len(cands)), replace=False)
            return min((cands[i] for i in idx), key=lambda p: p.est)
        for _ in range(cfg.build_tries):
            a = pick(pool)
            cross = [o for o in cfg.ops if o in OP.CROSSOVER]
            mut = [o for o in cfg.ops if o in OP.MUTATION]
            others = [p for p in pool if p.niche != a.niche] or [p for p in pool if p is not a]
            use_x = bool(cross) and bool(others) and (not mut or rng.random() < cfg.crossover_share)
            name = str(rng.choice(cross if use_x else mut))
            b = pick(others) if use_x else None
            guide = a.grad if (cfg.guided and a.grad is not None) else None
            f, meta = OP.OPS[name](self.space, rng, a.f, None if b is None else b.f, guide)
            self.op_stats[name][0] += 1
            if "skip" in meta:
                continue
            child, built = self._make(f, kind, name, (a.id,) + ((b.id,) if b is not None else ()), meta)
            if child is None:
                continue
            if np.array_equal(child.B, a.B) or (b is not None and np.array_equal(child.B, b.B)):
                self.all.pop(child.id, None)                       # a clone: no CFD spent on it
                continue
            self.op_stats[name][1] += 1
            child.step = cfg.step0
            return child
        return None

    # ---------------------------------------------------------------- one generation
    def generation(self, budget):
        cfg = self.cfg
        self.gen += 1
        rec = {"gen": self.gen, "explore": [], "control": [], "refine": []}
        elites = list(self.archive.values())
        pool = elites if cfg.selection else self.seeds
        for kind, n, src in (("explore", cfg.n_explore, pool), ("control", cfg.n_control, self.seeds)):
            for _ in range(n):
                if self.spent >= budget or not src:
                    break
                child = self._breed(src, kind)
                if child is None:
                    continue
                entry = self._score_child(child, kind, budget)
                if entry is None:
                    continue
                if entry in ("new", "replaced"):
                    self.op_stats[child.op][2] += 1
                rec[kind].append({"id": child.id, "op": child.op, "est": child.est, "niche": child.niche, "entry": entry,
                                  "parents": child.parents})
        if cfg.n_refine:
            rec["refine"] = self._refine(budget)
        rec["spent"] = self.spent
        rec["best"] = min((e.est for e in self.archive.values()), default=np.inf)
        self.log.append(rec)
        return rec

    def _score_child(self, child, kind, budget):
        """Score an explore/control child and try it for the map. With morph_explore, a child that is a small
        move of its first parent with the same topology is scored on that parent's morphed mesh (low noise):
        its estimate is the parent's plus the measured change, and against its own parent the margin rule of
        the refinement applies. Otherwise: a fresh mesh and the duel."""
        cfg = self.cfg
        a = self.all.get(child.parents[0]) if child.parents else None
        if cfg.morph_explore and a is not None and a.anchor is not None:
            m = self.ev.morph(a, child)
            if m is not None and a.depth + m["move"] <= cfg.max_depth:
                self.spent += self.ev.cost_morph
                child.base, child.n_base = a.est + m["delta"], a.n
                child.depth, child.anchor = a.depth + m["move"], a.anchor
                child.meta["morph_delta"] = m["delta"]
                if kind != "explore":
                    return "control"
                margin = max(3.0 * self.ev.sigma_morph * np.sqrt(2.0), cfg.floor)
                if self.archive.get(child.niche) is a:
                    if m["delta"] <= -margin:
                        self.archive[child.niche] = child
                        return "replaced"
                    return "rejected"
                return self._enter(child, budget)
        if not self._fresh(child):
            return None
        return self._enter(child, budget) if kind == "explore" else "control"

    def _refine(self, budget):
        cfg, out = self.cfg, []
        cand = sorted((e for e in self.archive.values() if (e.step or cfg.step0) >= cfg.step_min), key=lambda e: e.est)
        chosen = cand[: cfg.refine_top]
        rest = cand[cfg.refine_top:]
        while len(chosen) < cfg.n_refine and rest:
            chosen.append(rest.pop(self.rng.integers(len(rest))))
        for e in chosen:
            if self.spent >= budget:
                break
            out.append(self.refine_one(e, budget))
        return out

    def refine_one(self, e, budget=np.inf):
        """The adjoint's move on one elite: solve (if not cached), two step sizes, morph-scored, keep or halve."""
        cfg = self.cfg
        if e.step is None:
            e.step = cfg.step0
        r = {"id": e.id, "niche": e.niche, "step": e.step}
        if e.depth + e.step > cfg.max_depth or e.anchor is None:   # the mesh is spent: a fresh mesh of this design
            if not self._fresh(e):
                return dict(r, result="rebase failed")
            r["rebased"] = True
        if e.grad is None:
            e.grad = self.ev.adjoint(e)
            self.spent += self.ev.cost_adjoint
            if e.grad is None:
                e.step = 0.0
                return dict(r, result="no gradient")
        best = None
        for s in (e.step, e.step / 2):
            if self.spent >= budget:
                break
            f_try, pred = self.ev.grad_step(self.space, e, s)
            child, built = self._make(f_try, "refine", "adjoint", (e.id,), {"step": s, "pred": pred})
            if child is None:
                r.setdefault("illegal", []).append(s)
                continue
            m = self.ev.morph(e, child)
            if m is None:                                          # the morph check refused it: no solve was spent
                r.setdefault("folded", []).append(s)
                self.all.pop(child.id, None)
                continue
            self.spent += self.ev.cost_morph
            d = m["delta"]
            r.setdefault("tried", []).append((s, float(d), float(pred)))
            if best is None or d < best[0]:
                best = (d, child, m["move"])
        margin = max(3.0 * self.ev.sigma_morph * np.sqrt(2.0), cfg.floor)
        if best is None or best[0] > -margin:
            e.step /= 2
            return dict(r, result="rejected")
        d, child, s = best
        child.base, child.n_base = e.est + d, e.n
        child.step, child.depth, child.anchor = e.step, e.depth + s, e.anchor
        if child.niche == e.niche or child.niche not in self.archive:
            if child.niche == e.niche:
                self.archive[e.niche] = child
            else:
                self.archive[child.niche] = child
        else:
            inc = self.archive[child.niche]
            if child.est <= inc.est - 2.0 * self._se(child, inc):
                self.archive[child.niche] = child
        return dict(r, result="accepted", child=child.id, delta=float(d), step_used=float(s), new_est=child.est)

    # ---------------------------------------------------------------- results
    def best(self):
        return min(self.archive.values(), key=lambda e: e.est) if self.archive else None

    def handover(self, budget=np.inf):
        """Before a design is handed over: the best few by estimate get fresh re-runs up to max_runs, so the
        pick is not simply the luckiest single run. Returns the best after that."""
        while True:
            top = sorted(self.archive.values(), key=lambda e: e.est)[: self.cfg.handover_top]
            todo = [e for e in top if len(e.fresh) < self.cfg.max_runs]
            if not todo or self.spent >= budget:
                return self.best()
            if not self._fresh(todo[0]):
                return self.best()
