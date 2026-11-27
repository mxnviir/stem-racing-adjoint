"""Render seed fields (.npz with f) as built cars: each field goes through space.build() (the rules) and the
exact body mesh is drawn from three views.

    python -m seedevo.render_fields <out.png> <title> <field.npz> [...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import trimesh

LIGHT = np.array([0.4, -0.6, 0.7]); LIGHT /= np.linalg.norm(LIGHT)
VIEWS = [("3/4 front", 22, -55), ("top", 89, -90), ("side", 0, -90)]


def as_mm(m):
    m = m.copy() if isinstance(m, trimesh.Trimesh) else trimesh.Trimesh(*m)
    if m.extents.max() < 2.0:
        m.apply_scale(1000.0)
    if len(m.faces) > 70000:
        try:
            m = m.simplify_quadric_decimation(face_count=70000)
        except Exception:
            pass
    return m


def draw(ax, m, rgb, elev, azim, title):
    tri = m.vertices[m.faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    s = 0.35 + 0.65 * np.clip(np.abs(n @ LIGHT), 0, 1)
    ax.add_collection3d(Poly3DCollection(tri, facecolors=np.c_[rgb[None] * s[:, None], np.ones(len(tri))], linewidths=0))
    ax.set_xlim(0, 260); ax.set_ylim(-45, 45); ax.set_zlim(0, 45)
    ax.set_box_aspect((260, 90, 45), zoom=1.3); ax.view_init(elev, azim); ax.set_axis_off()
    ax.set_title(title, fontsize=11)


def main(out, title, *paths):
    from .space import RealSpace
    sp = RealSpace()
    rows = []
    for p in paths:
        f = np.load(p)["f"].astype(np.float64)
        b = sp.build(f)
        mesh = b["mesh"]
        if isinstance(mesh, dict):
            mesh = mesh.get("full") or mesh.get("body") or next(iter(mesh.values()))
        desc = sp.describe(b["B"])
        rows.append((Path(p).stem, as_mm(mesh), desc, b["ok"]))
    fig = plt.figure(figsize=(18, 4.1 * len(rows)), dpi=130)
    for r, (name, m, desc, ok) in enumerate(rows):
        for c, (vn, e, a) in enumerate(VIEWS):
            ax = fig.add_subplot(len(rows), 3, 3 * r + c + 1, projection="3d")
            lab = f"{name}: pod {desc[0]:.1f} cm3, {desc[1]} through-opening(s){'' if ok else ' (NOT LEGAL)'}" if c == 0 else vn
            draw(ax, m, np.array([0.55, 0.72, 0.62]), e, a, lab)
    fig.suptitle(title, fontsize=13)
    fig.savefig(out, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    main(*sys.argv[1:])
