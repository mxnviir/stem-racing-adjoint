"""Ported from the evolution branch (ccr-a4f3e46d-23atrh: search/sidepod/methods.py, 2026-11-23) for hybrid/: the
batch ask/tell CMA-ES that drove its SimScale sidepod search. Kept as the interface hybrid/guided_es.py follows and
for the global (population) level. NOT ported: the 72-number lattice (design.py, shape parameters), the milling and
rule masks (geometry.py), SimScale (fresh mesh per car). See hybrid/EVOLUTION_ADJOINT_PLAN.md for why.

    m = make("cma", rep, start, rng, **opts); xs = m.ask(n); m.tell(xs, values, info)
"""
from __future__ import annotations

import numpy as np


class Method:
    def __init__(self, rep, start, rng, **o):
        self.rep, self.rng, self.o = rep, rng, o
        self.x0 = rep.x0(start)
        self.X, self.Y = [], []                 # target-fidelity observations
        self.prior = []                         # (x, y, s)

    def best(self):
        if not self.Y:
            return None, np.inf
        i = int(np.argmin(self.Y)); return self.X[i], self.Y[i]

    def add_prior(self, xs, ys, s=0.0):
        self.prior += [(np.asarray(x), y, s) for x, y in zip(xs, ys) if y is not None]

    def tell(self, xs, ys, info=None):
        for x, y in zip(xs, ys):
            if y is not None:
                self.X.append(np.asarray(x)); self.Y.append(float(y))


class CMA(Method):
    """CMA-ES, one generation at a time: ask() hands out the current generation's samples (an
    empty list once all are out), and the ES is told only when every sample of THAT generation
    has a result, in its own order. Illegal cars (None) get the generation's worst + 0.05 s."""

    def __init__(self, rep, start, rng, **o):
        super().__init__(rep, start, rng, **o)
        import cma
        self.es = cma.CMAEvolutionStrategy(self.x0, o.get("sigma", 1.0),
                                           {"seed": int(rng.integers(1, 1 << 30)), "verbose": -9,
                                            "popsize": o.get("popsize", 12)})
        self._new_generation()

    def _new_generation(self):
        self.gen = [np.asarray(x) for x in self.es.ask()]
        self.gen_y = [False] * len(self.gen)                     # False = no result yet
        self.handed = 0

    def ask(self, n):
        out = self.gen[self.handed: self.handed + n]
        self.handed += len(out)
        return [x.copy() for x in out]

    def tell(self, xs, ys, info=None):
        super().tell(xs, ys)
        for x, y in zip(xs, ys):
            x = np.asarray(x)
            i = next((i for i, g in enumerate(self.gen) if self.gen_y[i] is False and np.allclose(g, x)), None)
            if i is not None:
                self.gen_y[i] = y                                # results from an older generation are ignored
        if all(y is not False for y in self.gen_y):
            good = [y for y in self.gen_y if y is not None]
            worst = max(good, default=1.0)
            self.es.tell(self.gen, [y if y is not None else worst + 0.05 for y in self.gen_y])
            self._new_generation()


MAKERS = {"cma": CMA}


def make(name, rep, start, rng, **o):
    return MAKERS[name](rep, start, rng, **o)
