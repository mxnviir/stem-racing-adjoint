"""Organic seed generator: random, smooth, deliberately unusual sidepods (owner, 2026-11-27: "interesting seeds that
are weird and sorta organic"). Each generator draws its own parameters at random, writes a field on the car's grid
(mm, + = foam) inside the sidepod region (the team pod's field outside it), and the seed is kept only if
space.build() makes it legal (mill, walls, one piece, cargo, track clearance). Nothing here is scored; the campaign does that.

    python -m seedevo.seed_gen <out dir> <n per kind> [seed]

Kinds:
  blobs    smooth union of 4-9 random balls hugging the body side (metaballs)
  lumpy    the team pod with low-frequency 3D noise added: a melted, lumpy pod
  gyroid   a gyroid lattice clipped to a rounded envelope: porous, coral-like, many openings
  snake    a tube that wanders along the car (sinuous centre line, swelling radius)
  teardrop a streamlined drop (round nose, long tapering tail), random fatness and droop
  cppn     a small random network of sines and Gaussians over (x, y, z), thresholded in an envelope
  worley   a rounded envelope with random cell-shaped voids carved out (sponge / bone)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

KINDS = ("blobs", "lumpy", "gyroid", "snake", "teardrop", "cppn", "worley")


def smin(a, b, k):
    """Smooth maximum of two 'inside-positive' fields (union with a fillet of about k mm)."""
    h = np.clip(0.5 + 0.5 * (a - b) / k, 0.0, 1.0)
    return b * (1 - h) + a * h + k * h * (1 - h)


class Gen:
    def __init__(self, space, base, rng):
        self.s, self.base, self.rng = space, base, rng
        r = space.region
        self.x0, self.x1 = float(space.X[r].min()), float(space.X[r].max())
        self.z0, self.z1 = float(space.Z[r].min()), float(space.Z[r].max())
        self.X, self.Y, self.Z = space.X, space.Yabs, space.Z

    def u(self, a, b):
        return float(self.rng.uniform(a, b))

    def env(self, xa, xb, yo, zc, ry, rz, p=2.5):
        """A rounded box-ish envelope (superellipse in y-z, rounded ends in x); + inside."""
        xm, rx = (xa + xb) / 2, (xb - xa) / 2
        q = (np.abs((self.X - xm) / rx) ** 4 + np.abs((self.Y - yo) / ry) ** p + np.abs((self.Z - zc) / rz) ** p)
        return (1.0 - q ** (1 / p)) * min(rx, ry, rz)

    def blobs(self):
        f = np.full(self.X.shape, -20.0)
        for _ in range(self.rng.integers(4, 10)):
            c = (self.u(self.x0 + 8, self.x1 - 8), self.u(16, 28), self.u(7, 28))
            r = self.u(5, 12)
            d = r - np.sqrt((self.X - c[0]) ** 2 + (self.Y - c[1]) ** 2 + (self.Z - c[2]) ** 2)
            f = smin(f, d, self.u(3, 7))
        return f

    def lumpy(self):
        n = self.rng.standard_normal(self.X.shape)
        n = ndimage.gaussian_filter(n, self.u(4, 8))
        n /= n.std() + 1e-9
        return self.base + self.u(2.5, 5.5) * n

    def gyroid(self):
        L = self.u(9, 16)
        k = 2 * np.pi / L
        g = np.sin(k * self.X) * np.cos(k * self.Y) + np.sin(k * self.Y) * np.cos(k * self.Z) + np.sin(k * self.Z) * np.cos(k * self.X)
        t = self.u(0.5, 1.1)
        lattice = (t - np.abs(g)) * L / (2 * np.pi)           # sheet of thickness ~ t, mm-ish slope
        e = self.env(self.u(self.x0 + 2, 75), self.u(130, self.x1 - 2), self.u(20, 24), self.u(14, 20), self.u(9, 13), self.u(9, 14))
        return np.minimum(e, lattice)

    def snake(self):
        xs = self.X
        a1, a2, w1, w2, p1, p2 = self.u(2, 7), self.u(2, 8), self.u(0.03, 0.09), self.u(0.03, 0.08), self.u(0, 6.3), self.u(0, 6.3)
        yc = self.u(18, 24) + a1 * np.sin(w1 * xs + p1)
        zc = self.u(12, 20) + a2 * np.sin(w2 * xs + p2)
        r = self.u(5, 9) + self.u(1, 4) * np.sin(self.u(0.04, 0.1) * xs + self.u(0, 6.3))
        tube = r - np.sqrt((self.Y - yc) ** 2 + (self.Z - zc) ** 2)
        ends = np.minimum(self.X - self.u(self.x0 + 2, 70), self.u(135, self.x1 - 2) - self.X)
        return np.minimum(tube, ends)

    def teardrop(self):
        xa, xb = self.u(self.x0 + 2, 70), self.u(135, self.x1 - 2)
        t = np.clip((self.X - xa) / (xb - xa), 0, 1)
        nose = self.u(0.15, 0.35)
        prof = np.where(t < nose, np.sqrt(np.clip(1 - ((nose - t) / nose) ** 2, 0, 1)), 1 - ((t - nose) / (1 - nose)) ** self.u(1.3, 2.5))
        R = self.u(8, 13) * prof
        yc = self.u(19, 24)
        zc = self.u(13, 20) - self.u(-4, 6) * t                   # droop (or rise) toward the tail
        sq = self.u(0.7, 1.4)                                    # flattened or tall section
        d = np.sqrt((self.Y - yc) ** 2 + ((self.Z - zc) * sq) ** 2)
        f = R - d
        return np.where((self.X < xa) | (self.X > xb), -5.0, f)

    def cppn(self):
        P = np.stack([(self.X - self.X.mean()) / 40, (self.Y - 20) / 12, (self.Z - 18) / 12])
        h = P
        for _ in range(int(self.rng.integers(2, 4))):
            W = self.rng.normal(0, self.u(1.0, 2.5), (6, h.shape[0])); b = self.rng.normal(0, 1, (6, 1, 1, 1))
            a = np.tensordot(W, h, axes=1) + b
            acts = [np.sin, lambda v: np.exp(-v * v), np.tanh]
            h = np.stack([acts[i % 3](a[i]) for i in range(6)])
        out = np.tensordot(self.rng.normal(0, 1, 6), h, axes=1)
        out = (out - np.median(out)) / (out.std() + 1e-9) * 4.0
        e = self.env(self.u(self.x0 + 2, 75), self.u(130, self.x1 - 2), self.u(20, 24), self.u(14, 20), self.u(9, 13), self.u(9, 14))
        return np.minimum(e, out + self.u(0, 3))

    def worley(self):
        e = self.env(self.u(self.x0 + 2, 72), self.u(132, self.x1 - 2), self.u(20, 24), self.u(14, 20), self.u(9, 13), self.u(9, 14))
        f = e.copy()
        for _ in range(int(self.rng.integers(5, 14))):
            c = (self.u(self.x0, self.x1), self.u(16, 32), self.u(4, 32))
            r = np.array([self.u(4, 10), self.u(3, 7), self.u(3, 7)])
            d = 1 - np.sqrt(((self.X - c[0]) / r[0]) ** 2 + ((self.Y - c[1]) / r[1]) ** 2 + ((self.Z - c[2]) / r[2]) ** 2)
            f = np.minimum(f, -d * r.min())
        return f

    def make(self, kind):
        f = np.clip(getattr(self, kind)(), -20, 20)
        return np.where(self.s.region, f, self.base)

    def attach(self, f):
        """A web from the body side (|y| ~ 13) out to the shape's inner face, column by column in (x, z):
        for a shape that floats free of the body (snake, teardrop)."""
        inside = (f > 0) & self.s.region & (self.s.Y >= 0)
        has = inside.any(axis=1)
        iy = np.where(has, inside.argmax(axis=1), 0)                     # first foam cell along +y
        ymin = np.take_along_axis(self.Y, iy[:, None, :], axis=1)[:, 0, :]
        web = np.where(has[:, None, :] & (self.Y <= ymin[:, None, :] + 1.0), 2.0, -20.0)
        return np.where(self.s.region, np.maximum(f, web), self.base)


def main(out, per_kind=2, seed=7, kinds=KINDS, tries=12):
    from .space import RealSpace
    from .campaign import shape_hash
    sp = RealSpace()
    base = np.load(sys.argv[4])["f"].astype(np.float64) if len(sys.argv) > 4 else None
    if base is None:
        raise SystemExit("pass the team pod's field (.npz with f) as the 4th argument")
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    g = Gen(sp, base, rng)
    log, seen = [], set()
    for kind in kinds:
        got = 0
        for t in range(tries):
            if got >= per_kind:
                break
            f = g.make(kind)
            b = sp.build(f)
            webbed = False
            if not b["ok"] and b["info"]["check"].get("pieces", 1) != 1:
                f = g.attach(f); b = sp.build(f); webbed = True
            info = {"kind": kind, "try": t, "ok": b["ok"], "webbed": webbed, "check": {k: v for k, v in b["info"]["check"].items()}}
            if b["ok"]:
                h = shape_hash(b["B"])
                if h in seen:
                    continue
                seen.add(h)
                desc = sp.describe(b["B"])
                name = f"{kind}{got + 1}"
                np.savez_compressed(out / f"{name}.npz", f=b["f"].astype(np.float32))
                info.update(name=name, pod_cm3=desc[0], openings=desc[1], changed_mm3=b["changed_mm3"])
                got += 1
            log.append(info)
            print(json.dumps(info, default=float), flush=True)
    (out / "seed_gen_log.json").write_text(json.dumps(log, indent=1, default=float))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2, int(sys.argv[3]) if len(sys.argv) > 3 else 7)
