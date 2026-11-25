"""The grid a design lives on, and what turns a field into a legal body.

Space interface (used by operators.py and engine.py):
    h, X, Y, Yabs, Z, axes, region, mirror
    build(f) -> dict(ok, f (the field of what is made), B (voxels), changed_mm3, pod_mm3, info)
    describe(B) -> (pod volume cm3, through-openings)       no CFD
    niche(desc) -> a hashable cell of the map

RealSpace: the trial car (geometry.Car + shape_loop.build_design: rules, 3-axis mill, 3 mm walls, checks,
exact mesh, mass). ToySpace: a small box with the same wall and one-piece rules and no mill, for the
search-machinery tests (it is NOT a model of the car's aerodynamics).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

VOL_BINS_REAL = (20.0, 40.0, 55.0, 70.0, 90.0)        # cm3 edges -> 6 bins (no pod 5, team pod 67.5, block 153)
OPEN_BINS = (1, 2, 4)                                 # through-openings: 0 | 1 | 2-3 | 4+


def sdf(B, h):
    """Signed distance (mm, + inside), slope 1 across the surface (first cells at +/- h/2)."""
    return np.where(B, ndimage.distance_transform_edt(B) - 0.5, -(ndimage.distance_transform_edt(~B) - 0.5)) * h


def _ball(r_cells):
    k = np.arange(-int(np.ceil(r_cells)), int(np.ceil(r_cells)) + 1)
    return (k[:, None, None] ** 2 + k[None, :, None] ** 2 + k[None, None, :] ** 2) <= r_cells * r_cells


def through_openings(pod):
    """Holes seen through the pod from the side (along y) and from above (along z): closed air regions in
    each silhouette. A notch open to the silhouette's edge is not counted."""
    n = 0
    for ax in (1, 2):
        sil = pod.any(axis=ax)
        n += ndimage.label(ndimage.binary_fill_holes(sil) & ~sil)[1]
    return int(n)


class _Base:
    def niche(self, desc):
        return (int(np.searchsorted(self.vol_bins, desc[0])), int(np.searchsorted(OPEN_BINS, desc[1], side="right")))


class ToySpace(_Base):
    """A 64 x 22 x 26 mm half box at 1 mm. A fixed 'body' slab at low y; the pod region is everything else.
    Rules: 3 mm minimum wall (opening), one piece attached to the body, sealed voids filled."""
    mirror = False

    def __init__(self, shape=(64, 22, 26), h=1.0):
        self.h, self.shape = h, shape
        self.axes = tuple(np.arange(n) * h + h / 2 for n in shape)
        self.X, self.Y, self.Z = np.meshgrid(*self.axes, indexing="ij")
        self.Yabs = self.Y
        self.keep = (self.Y < 4.0) & (self.Z > 8.0) & (self.Z < 20.0)
        box = (self.X > 2) & (self.X < shape[0] - 2) & (self.Y >= 4.0) & (self.Y < shape[1] - 1) & (self.Z > 1) & (self.Z < shape[2] - 1)
        self.region = box
        self._wall = _ball(1.5 / h)
        self.vol_bins = (2.0, 4.0, 6.0, 8.0, 11.0)

    def build(self, f):
        want = (f > 0) & self.region
        B = ndimage.binary_opening(want | self.keep, self._wall) & self.region
        B = (B | self.keep)
        B = B | (ndimage.binary_fill_holes(B) & self.region)
        lab, _ = ndimage.label(B)
        ids = np.unique(lab[self.keep]); ids = ids[ids > 0]
        B = B & np.isin(lab, ids)
        pod = B & self.region
        changed = float(((pod ^ want)).sum() * self.h ** 3)
        pod_mm3 = float(pod.sum() * self.h ** 3)
        agree = (pod == want) & self.region
        fr = np.where(agree, f, sdf(B, self.h))
        fr = np.where(self.region, np.clip(fr, -8.0, 8.0), sdf(B, self.h))
        ok = changed <= 0.30 * max(float(want.sum() * self.h ** 3), 1.0)
        return {"ok": bool(ok), "f": fr, "B": B, "changed_mm3": changed, "pod_mm3": pod_mm3, "info": {}}

    def describe(self, B):
        pod = B & self.region
        return (float(pod.sum() * self.h ** 3 / 1e3), through_openings(pod))


class RealSpace(_Base):
    """The trial car. build() is shape_loop.build_design (rules, mill, walls, checks, exact mesh, mass)."""
    mirror = True

    def __init__(self, car=None):
        import shape_loop as SL
        self.SL = SL
        self.car = car or SL.load_car()
        c = self.car
        self.h, self.shape = c.h, c.body0.shape
        self.axes = (c.xs, c.ys, c.zs)
        self.X, self.Y, self.Z = c.X, c.Y, c.Z
        self.Yabs = np.abs(c.Y)
        self.region = c.region
        self.vol_bins = VOL_BINS_REAL

    def build(self, f):
        c = self.car
        b = self.SL.build_design(c, f)
        pod = b["voxels"] & c.region
        return {"ok": bool(b["check"]["ok"]), "f": b["f_rules"], "B": b["voxels"],
                "changed_mm3": float(b["rules_changed_mm3"]), "pod_mm3": float(pod.sum() * c.h ** 3),
                "info": {"check": b["check"], "mill": b["mill"], "mass": b["mass"]}, "mesh": b["mesh"], "built": b}

    def describe(self, B):
        c = self.car
        pod = B & c.region & (c.Y >= 0)                       # one side
        return (float((B & c.region).sum() * c.h ** 3 / 1e3), through_openings(pod))
