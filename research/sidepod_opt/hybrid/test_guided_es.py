"""Offline checks of hybrid/guided_es.py on a synthetic problem (no CFD; tooling test, not evidence about the car).
Fields live on 1500 points of a 2D patch; smooth random fields = Gaussian-filtered noise (like the step fields).
Objective: linear + mild quadratic (steps of probe size nearly linear, as measured: rnd1 half / minus checks) + noise.
Guides: a 'good' biased guide (cos ~0.6 with the true gradient, like coarse DAFoam on the resolved mesh?) and a 'poor'
one (cos ~0.2, like ESI). Arms, same rounds, same noise: ES only; guided (both); adjoint-only line search."""
import numpy as np
from scipy.ndimage import gaussian_filter
from guided_es import GuidedES

S = 40; n = S * S
A = np.ones(n) / n


def smooth(rng, sig=3.0):
    f = gaussian_filter(rng.standard_normal((S, S)), sig).ravel()
    return f / np.abs(f).max()


def with_cos(g, rng, c):
    r = smooth(rng); r -= (r @ g) / (g @ g) * g
    u = c * g / np.linalg.norm(g) + np.sqrt(1 - c * c) * r / np.linalg.norm(r)
    return u / np.abs(u).max()


def run(arm, seed, rounds=8, noise=0.05):
    rng = np.random.default_rng(seed)
    g = smooth(rng, 4.0)
    g *= 1.0 / np.std([(A * g * smooth(rng)).sum() for _ in range(50)])   # random probes change drag by ~+-1 (as measured)
    H = 0.1                                                              # curvature: ~10 % of a probe's effect
    f = lambda x: float((A * g * x).sum() + H * (A * x * x).sum() / (A * smooth(np.random.default_rng(0)) ** 2).sum())
    good, poor = with_cos(-g, rng, 0.6), with_cos(-g, rng, 0.2)   # guides point downhill
    bad = with_cos(-g, rng, -0.5)                               # a misleading guide (points uphill)
    gs = {"none": {}, "guided": {"good": good, "poor": poor}, "guided_good": {"good": good},
          "guided_bad": {"bad": bad}}.get(arm, {})
    opt = GuidedES(A, lambda r: smooth(r), guides=gs, n_random=10 if arm != "adjoint" else 0, rng=np.random.default_rng(seed + 99))
    if arm == "adjoint":
        opt.set_guides({"good": good})
    for _ in range(rounds):
        b = opt.ask()
        vals = [f(opt.x + fld) + noise * rng.standard_normal() for (_, _, fld) in b]
        opt.tell(vals, [noise] * len(vals))
    return f(opt.x) - f(np.zeros(n))


if __name__ == "__main__":
    for rounds in (1, 2, 8):
        for arm in ("none", "adjoint", "guided_good", "guided", "guided_bad"):
            r = [run(arm, s, rounds) for s in range(20)]
            print(f"{rounds} rounds  {arm:12s} mean {np.mean(r):+7.2f}  (min {np.min(r):+7.2f}, max {np.max(r):+7.2f})")
