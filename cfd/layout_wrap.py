"""A clean closed surface of a merged car for the CAD import: the solid is rebuilt from its own
occupancy on a fine grid ("shrink-wrap"), then reduced with a topology-preserving edge collapse.

Why: the union of the car's parts carries hundreds of needle triangles and 0.03 mm ledges (where
parts meet, where the halves overlap at the centre plane); SimScale's importer rejects them
('fault-edge-invalid', 'fault-face-tessellation_failed', both reference uploads, 2026-11-22), and
neither simplification nor isotropic remeshing removes them. Rebuilt from the grid, nothing thinner
than about one cell survives -- which is also what guarantees there is no slit or void left.

  wrap(M, pitch)        manifold3d solid (mm) -> trimesh (mm): exact slices, 3x supersampled coverage,
                        light smoothing, marching cubes, the outer shell only
  reduce(mesh, faces)   quadric edge collapse (pymeshlab): topology and boundary kept, flat triangles avoided
"""
from __future__ import annotations

import sys
from pathlib import Path
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
import repo_paths  # noqa: E402,F401
import numpy as np

SS = 3               # in-plane supersampling of each slice


def wrap(M, pitch=0.3, sigma=0.6):
    import trimesh
    from PIL import Image, ImageChops, ImageDraw
    from scipy import ndimage
    from skimage import measure
    x0, y0, z0, x1, y1, z1 = M.bounding_box()
    pad = 4
    nx = int(np.ceil((x1 - x0) / pitch)) + 2 * pad
    ny = int(np.ceil((y1 - y0) / pitch)) + 2 * pad
    nz = int(np.ceil((z1 - z0) / pitch)) + 2 * pad
    occ = np.zeros((nz, ny, nx), np.float32)
    fine = pitch / SS
    for k in range(nz):
        z = z0 + (k - pad + 0.5) * pitch
        if z <= z0 or z >= z1:
            continue
        img = Image.new("1", (nx * SS, ny * SS), 0)
        for poly in M.slice(z).to_polygons():
            p = np.asarray(poly)
            if len(p) < 3:
                continue
            px = (p[:, 0] - x0) / fine + pad * SS - 0.5
            py = (p[:, 1] - y0) / fine + pad * SS - 0.5
            one = Image.new("1", (nx * SS, ny * SS), 0)
            ImageDraw.Draw(one).polygon(list(zip(px.tolist(), py.tolist())), fill=1)     # even-odd: holes cancel
            img = ImageChops.logical_xor(img, one)
        a = np.asarray(img, np.float32)
        occ[k] = a.reshape(ny, SS, nx, SS).mean(axis=(1, 3))                             # coverage 0..1
    f = ndimage.gaussian_filter(occ, sigma)
    v, fc, _, _ = measure.marching_cubes(f, 0.5)
    v = v[:, ::-1] * pitch + np.array([x0, y0, z0]) + (0.5 - pad) * pitch                 # (z, y, x) -> (x, y, z)
    t = trimesh.Trimesh(v, fc[:, ::-1], process=True)
    if t.volume < 0:
        t.invert()
    shells = t.split(only_watertight=False)
    if len(shells) > 1:                                         # enclosed bubbles: the outer shell only
        t = max(shells, key=lambda q: q.volume)
    return t


def reduce(mesh, faces: int):
    import pymeshlab as ml
    import trimesh
    ms = ml.MeshSet()
    ms.add_mesh(ml.Mesh(np.asarray(mesh.vertices, float), np.asarray(mesh.faces)))
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=int(faces), qualitythr=0.5, preservetopology=True,
                                                preserveboundary=True, preservenormal=True, optimalplacement=True,
                                                planarquadric=True, autoclean=True)
    m = ms.current_mesh()
    t = trimesh.Trimesh(m.vertex_matrix(), m.face_matrix(), process=True)
    if t.volume < 0:
        t.invert()
    return t


def quality(t) -> dict:
    """Shortest edge and smallest triangle height (mm), and whether a reader sees one closed surface."""
    V = t.vertices
    e = np.linalg.norm(V[t.edges_unique[:, 0]] - V[t.edges_unique[:, 1]], axis=1)
    tri = V[t.faces]
    l = np.stack([np.linalg.norm(tri[:, i] - tri[:, (i + 1) % 3], axis=1) for i in range(3)], 1)
    h = 2 * t.area_faces / np.maximum(l.max(1), 1e-12)
    return {"faces": int(len(t.faces)), "min_edge_mm": round(float(e.min()), 4), "min_height_mm": round(float(h.min()), 4),
            "needles": int((h < 0.02).sum()), "closed": bool(t.is_watertight and t.is_winding_consistent)}


def self_intersections(mesh) -> int:
    """Faces of `mesh` that cut another face of it (pymeshlab): the mesher refuses such a surface."""
    import pymeshlab as ml
    ms = ml.MeshSet()
    ms.add_mesh(ml.Mesh(np.asarray(mesh.vertices, float), np.asarray(mesh.faces)))
    ms.compute_selection_by_self_intersections_per_face()
    return int(ms.current_mesh().selected_face_number())
