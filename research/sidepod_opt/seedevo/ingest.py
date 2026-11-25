"""Seed geometry in: a whole-car STEP (or STL) -> a design field on the car's grid.

    f, info = field_from_step(car, "seeds/my_pod.step")          # body solid: 'car_body', else the largest solid
    f, info = field_from_stl(car, "seeds/my_pod.stl")            # mm, the STEP frame of cad/trial_car.step

The seed must be the trial car with only the sidepod region changed: same frame (x forward, y left, z up,
mm, ground at z = 0). info["outside_region_changed_mm3"] says how much of the body differs outside the
region (a seed with more than a few mm3 there is a different car, and build() will refuse it anyway).

The field is the voxel signed distance, replaced near the surface by the exact signed distance to the
seed's own surface, so sub-voxel positions survive (as shape_loop v2 needs).
"""
from __future__ import annotations

import numpy as np


def field_from_mesh(car, mesh, exact_band=True):
    import cadio as CI
    import shape_loop as SL
    B = CI.voxelize(mesh, car.xs, car.ys, car.zs)
    info = {"outside_region_changed_mm3": float(((B ^ car.body0) & ~car.region & ~car.cargo).sum() * car.h ** 3),
            "pod_cm3": float((B & car.region).sum() * car.h ** 3 / 1e3), "mesh_volume_cm3": float(mesh.volume / 1e3)}
    f = SL.sdf_of(car, B)
    if exact_band:
        import trimesh
        band = car.region & (np.abs(f) <= 2.0 * car.h) & (car.Y >= 0)
        pts = np.c_[car.X[band], car.Y[band], car.Z[band]]
        sd = np.empty(len(pts))
        for i in range(0, len(pts), 20000):                      # + inside
            sd[i:i + 20000] = trimesh.proximity.signed_distance(mesh, pts[i:i + 20000])
        f = f.copy()
        f[band] = sd
        j0 = int(np.searchsorted(car.ys, 0.0))
        f[:, :j0] = f[:, j0:][:, ::-1][:, :j0]                   # the car is symmetric
        info["band_points"] = int(len(pts))
    return f, info


def field_from_step(car, path, body_solid=None):
    import cadio as CI
    solids = CI.read_step_solids(path)
    name = body_solid or ("car_body" if "car_body" in solids else max(solids, key=lambda k: CI.brep_volume(solids[k])))
    mesh = CI.tessellate(CI.outer_solid(solids[name]))
    f, info = field_from_mesh(car, mesh)
    return f, dict(info, solid=name, solids=sorted(solids))


def field_from_stl(car, path, scale=1.0):
    import trimesh
    m = trimesh.load(path, process=True)
    if scale != 1.0:
        m.apply_scale(scale)
    if not m.is_watertight:
        raise ValueError(f"{path}: the seed mesh is not watertight")
    return field_from_mesh(car, m)
