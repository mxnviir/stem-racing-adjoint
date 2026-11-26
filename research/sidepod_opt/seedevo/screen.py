"""Model-screened batches, ported from the evolution branch's layout search (search/layout/simscale_layout.py, ask()):
fit a Gaussian process to every design scored so far, score a large pool of candidates on it by expected
improvement, and pick the batch one at a time with the "kriging believer" (each pick is added with its predicted
value before the next, so a batch does not pile onto one spot). Only the picked candidates get CFD; the model never
scores a design in place of CFD (DECISIONS D4): it only chooses which candidates are worth a run.

Designs are fields, so the model works on a few numbers per design (`features`): occupancy averaged over coarse
blocks of the region, projected on the leading principal components of the designs seen, plus pod volume and
through-openings.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm


def block_occupancy(space, f, block_mm=6.0):
    k = max(1, int(round(block_mm / space.h)))
    occ = np.clip(0.5 + f / (2 * space.h), 0, 1) * space.region * (space.Y >= 0)
    w = np.argwhere(space.region & (space.Y >= 0))
    lo, hi = w.min(0), w.max(0) + 1
    sub = occ[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
    n = [s // k for s in sub.shape]
    sub = sub[: n[0] * k, : n[1] * k, : n[2] * k]
    return sub.reshape(n[0], k, n[1], k, n[2], k).mean((1, 3, 5)).ravel()


class Screen:
    def __init__(self, n_pc=8, seed=0):
        self.n_pc, self.rng = n_pc, np.random.default_rng(seed)

    def fit_basis(self, B):
        """B: block-occupancy rows of every design known (scored and candidates)."""
        self.mu = B.mean(0)
        U, S, Vt = np.linalg.svd(B - self.mu, full_matrices=False)
        self.V = Vt[: self.n_pc]
        self.scale = np.maximum(S[: self.n_pc] / np.sqrt(max(len(B) - 1, 1)), 1e-9)

    def feats(self, B, extra):
        return np.c_[((B - self.mu) @ self.V.T) / self.scale, extra]

    def pick(self, Xs, ys, Xc, n):
        """Indices of n candidates by expected improvement with the kriging believer (lower y is better)."""
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
        mu0, sd0 = ys.mean(), ys.std() + 1e-12
        d = Xs.shape[1]
        kern = ConstantKernel(1.0, (0.05, 20.0)) * Matern(length_scale=np.full(d, 1.0), length_scale_bounds=(0.05, 50.0), nu=2.5) \
            + WhiteKernel(0.1, (1e-4, 2.0))
        gp = GaussianProcessRegressor(kern, normalize_y=False, n_restarts_optimizer=3, random_state=0).fit(Xs, (ys - mu0) / sd0)
        fixed = GaussianProcessRegressor(gp.kernel_, optimizer=None, normalize_y=False)
        Xa, ya, best = Xs.copy(), (ys - mu0) / sd0, ((ys - mu0) / sd0).min()
        left, picks, info = list(range(len(Xc))), [], []
        for _ in range(min(n, len(Xc))):
            fixed.fit(Xa, ya)
            m, s = fixed.predict(Xc[left], return_std=True)
            z = (best - m) / np.maximum(s, 1e-9)
            ei = (best - m) * norm.cdf(z) + s * norm.pdf(z)
            j = int(np.argmax(ei)); k = left.pop(j)
            picks.append(k); info.append((float(m[j] * sd0 + mu0), float(s[j] * sd0)))
            Xa = np.vstack([Xa, Xc[k]]); ya = np.append(ya, m[j])
        self.last = {"noise": float(np.sqrt(gp.kernel_.k2.noise_level)) * sd0, "picked": info}
        return picks
