"""Guided evolution: the sidepod loop's optimiser, as batch ask/tell (the interface of search/sidepod/methods.py on
the evolution branch, so a campaign runner can drive it and stop/resume between rounds).

Design space: a normal-displacement field over the sidepod surface (per STL vertex). No shape parameters: every
direction is either a smoothed random field (evolution's mutation), an adjoint field (DAFoam, ESI), or a combination
of directions whose drag change was MEASURED. Every candidate is CFD'd; the adjoints only propose.

One round = one batch, all solved in parallel on the good mesh, each as a move of the current parent:
  probes   one-sided moves of size `probe` along each guide (adjoints, last accepted step) and along `n_random` new
           random smooth fields: each gives a measured directional derivative at the parent (evolution's sampling;
           Guided ES, Maheswaranathan et al. 2019, with the guides measured instead of trusted).
  steps    moves along the steepest descent inside the span of every direction measured at (or near) the parent,
           at a fan of sizes (the step size is chosen by CFD, not by a model).
  parent   one re-run of the parent itself (drift / noise check).
tell(): the best candidate (step or probe) is accepted if it beats the parent by >= `accept_se` standard errors (Lamarckian: the accepted
design becomes the parent); the archive of measured directions is kept with an age discount, since a move of
<= 0.125 mm barely changes the gradient. Guides are weighted by their measured usefulness automatically: the
least-squares combination puts weight on a guide only in proportion to the drag change it actually produced.
"""
from __future__ import annotations

import numpy as np


class GuidedES:
    def __init__(self, area, make_random, guides=None, n_random=10, probe=1.0, fan=(0.5, 1.0, 1.5),
                 ridge=1e-3, accept_se=3.0, age_discount=0.5, rng=None):
        """area: per-vertex area weights (the metric); make_random(rng) -> a smooth random field normalised like
        every other direction (peak ~1); guides: {name: field}, refreshed by set_guides() each round."""
        self.A = np.asarray(area, float)
        self.make_random, self.n_random, self.probe, self.fan = make_random, n_random, probe, tuple(fan)
        self.ridge, self.accept_se, self.age_discount = ridge, accept_se, age_discount
        self.rng = rng or np.random.default_rng(0)
        self.x = np.zeros(len(self.A))          # the parent (cumulative field)
        self.fx, self.sx = None, None             # its measured value and SE
        self.guides = dict(guides or {})
        self.archive = []                         # (direction d, measured dF per unit move, weight)
        self.history = []
        self._batch = None

    def set_guides(self, guides):
        self.guides = dict(guides)

    # -- the descent direction inside the span of measured directions --------------------------------------------
    def descent(self, keys=None):
        rows = [(d, g, w) for (k, d, g, w) in self.archive if keys is None or keys(k)]
        if not rows:
            return None
        X = np.array([d for d, _, _ in rows]); g = np.array([g for _, g, _ in rows]); wt = np.array([w for _, _, w in rows])
        M = (X * self.A) @ X.T
        Wm = np.diag(wt)
        # weighted least squares: c = -(M W + ridge)^-1 W g  (old measurements count less)
        c = -np.linalg.solve(Wm @ M + self.ridge * np.trace(M) / len(rows) * np.eye(len(rows)), Wm @ g)
        d = c @ X
        return d / max(np.abs(d).max(), 1e-12)

    def ask(self):
        """The round's batch: [(tag, kind, field)], each field a move of the parent (absolute design = x + field)."""
        b = [("parent", "parent", np.zeros_like(self.x))]
        for k, u in self.guides.items():
            b.append((f"guide:{k}", "probe", self.probe * u / max(np.abs(u).max(), 1e-12)))
        for i in range(self.n_random):
            r = self.make_random(self.rng)
            b.append((f"rnd:{len(self.history)}:{i}", "probe", self.probe * r / max(np.abs(r).max(), 1e-12)))
        d = self.descent()
        if d is not None:
            for s in self.fan:
                b.append((f"step:{s}", "step", s * self.probe * d))
        self._batch = b
        return b

    def tell(self, values, ses):
        """values/ses: measured objective and SE per batch entry, in ask() order (None = failed / folded)."""
        b = self._batch
        i0 = next(i for i, e in enumerate(b) if e[0] == "parent")
        f0, s0 = values[i0], ses[i0]
        if f0 is None:
            raise ValueError("the parent's re-run failed: nothing in this round can be read")
        # age the archive, then add this round's probes (and steps: they are measured directions too)
        self.archive = [(k, d, g, w * self.age_discount) for (k, d, g, w) in self.archive]
        for (tag, kind, fld), v in zip(b, values):
            if kind == "parent" or v is None:
                continue
            n = np.sqrt((self.A * fld ** 2).sum())
            self.archive.append((tag, fld / n, (v - f0) / n, 1.0))
        # Lamarckian acceptance of the best step
        # selection over the whole population: a probe is a candidate design too (round 1 has no step yet)
        steps = [(v, s, fld, tag) for (tag, kind, fld), v, s in zip(b, values, ses) if kind != "parent" and v is not None]
        acc = None
        if steps:
            v, s, fld, tag = min(steps, key=lambda t: t[0])
            if v - f0 <= -self.accept_se * np.hypot(s, s0):
                acc = tag
                self.x = self.x + fld
                self.fx, self.sx = v, s
        if acc is None:
            self.fx, self.sx = f0, s0
        self.history.append({"parent_value": f0, "accepted": acc, "value_after": self.fx, "n_archive": len(self.archive)})
        return acc
