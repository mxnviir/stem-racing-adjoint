"""3D preview helpers (matplotlib): marching-cubes surface of a voxel mask, fixed car view."""
from __future__ import annotations

import sys
from pathlib import Path
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
import repo_paths  # noqa: E402,F401
import matplotlib
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy import ndimage
from skimage import measure

LIGHT = np.array([0.4, -0.6, 0.7]); LIGHT /= np.linalg.norm(LIGHT)


def surf(ax, mask, origin, h, color, alpha=1.0, smooth=0.8):
    m = np.pad(mask.astype(float), 1)
    if smooth:
        m = ndimage.gaussian_filter(m, smooth)
    try:
        v, f, n, _ = measure.marching_cubes(m, 0.5)
    except (ValueError, RuntimeError):
        return
    v = (v - 1) * h + np.asarray(origin)
    tri = v[f]
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    shade = 0.35 + 0.65 * np.clip(np.abs(nrm @ LIGHT), 0, 1)
    col = np.array(matplotlib.colors.to_rgb(color))[None] * shade[:, None]
    pc = Poly3DCollection(tri, facecolors=np.c_[col, np.full(len(col), alpha)], linewidths=0)
    ax.add_collection3d(pc)


def setup(ax, elev, azim):
    ax.set_xlim(-30, 230); ax.set_ylim(-45, 45); ax.set_zlim(0, 45)
    ax.set_box_aspect((260, 90, 45), zoom=1.25); ax.view_init(elev, azim); ax.set_axis_off()


def mesh(ax, m, color, alpha=1.0, max_faces=60000):
    """An exact triangle mesh (mm), shaded like surf()."""
    if len(m.faces) > max_faces:
        m = m.simplify_quadric_decimation(face_count=max_faces) if hasattr(m, "simplify_quadric_decimation") else m
    tri = m.vertices[m.faces]
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    shade = 0.35 + 0.65 * np.clip(np.abs(nrm @ LIGHT), 0, 1)
    col = np.array(matplotlib.colors.to_rgb(color))[None] * shade[:, None]
    ax.add_collection3d(Poly3DCollection(tri, facecolors=np.c_[col, np.full(len(col), alpha)], linewidths=0))
