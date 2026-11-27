"""Renders for the POC campaign: window seed (d3) vs its offset child d7 (coloured by surface change), plus a lineup."""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.spatial import cKDTree
import trimesh

SP = "/tmp/claude-0/-home-user/13e2e050-f437-5d93-8741-124a280e4b6b/scratchpad"
OUT = sys.argv[1]
LIGHT = np.array([0.4, -0.6, 0.7]); LIGHT /= np.linalg.norm(LIGHT)
DES = {0: ("Team pod (seed)", 174.75), 3: ("Window pod (best seed)", 173.50), 7: ("d7: offset of window pod", 170.11),
       10: ("d10: bump on window pod", 171.17)}


def load(i):
    m = trimesh.load(f"{SP}/bb{i}/car/body_full.stl")
    m.apply_scale(1000.0)
    if len(m.faces) > 70000:
        try:
            m = m.simplify_quadric_decimation(face_count=70000)
        except Exception:
            pass
    return m


def shade(m, rgb):
    tri = m.vertices[m.faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    s = 0.35 + 0.65 * np.clip(np.abs(n @ LIGHT), 0, 1)
    return tri, np.c_[rgb * s[:, None], np.ones(len(tri))]


def draw(ax, m, rgb, elev, azim, title=None):
    tri, col = shade(m, rgb)
    ax.add_collection3d(Poly3DCollection(tri, facecolors=col, linewidths=0))
    ax.set_xlim(0, 260); ax.set_ylim(-45, 45); ax.set_zlim(0, 45)
    ax.set_box_aspect((260, 90, 45), zoom=1.3); ax.view_init(elev, azim); ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=11)


def change(child, parent):
    """Signed distance (mm) of each child face centre from the parent surface: + = grown outward."""
    pts, fi = trimesh.sample.sample_surface_even(parent, 400000)
    tree = cKDTree(pts)
    c = child.triangles_center
    d, j = tree.query(c)
    n = parent.face_normals[fi[j]]
    sgn = np.sign(np.einsum("ij,ij->i", c - pts[j], n))
    return d * sgn


VIEWS = [("3/4 front", 22, -55), ("top", 89, -90), ("side", 0, -90)]

seed, child = load(3), load(7)
dv = change(child, seed)
cmap = plt.get_cmap("coolwarm"); lim = 1.5
rgb_child = cmap(np.clip(dv / lim, -1, 1) * 0.5 + 0.5)[:, :3]
grey = np.array([0.72, 0.74, 0.78])

fig = plt.figure(figsize=(18, 8.2), dpi=150)
for c, (name, e, a) in enumerate(VIEWS):
    ax = fig.add_subplot(2, 3, 1 + c, projection="3d")
    draw(ax, seed, np.tile(grey, (len(seed.faces), 1)), e, a, f"{DES[3][0]}  {DES[3][1]:.2f} mN  ({name})")
    ax = fig.add_subplot(2, 3, 4 + c, projection="3d")
    tri, _ = shade(child, grey)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    s = 0.45 + 0.55 * np.clip(np.abs(n @ LIGHT), 0, 1)
    ax.add_collection3d(Poly3DCollection(tri, facecolors=np.c_[rgb_child * s[:, None], np.ones(len(tri))], linewidths=0))
    ax.set_xlim(0, 260); ax.set_ylim(-45, 45); ax.set_zlim(0, 45)
    ax.set_box_aspect((260, 90, 45), zoom=1.3); ax.view_init(e, a); ax.set_axis_off()
    ax.set_title(f"{DES[7][0]}  {DES[7][1]:.2f} mN  ({name})", fontsize=11)
sm = matplotlib.cm.ScalarMappable(cmap=cmap, norm=matplotlib.colors.Normalize(-lim, lim))
cb = fig.colorbar(sm, ax=fig.axes, shrink=0.45, location="right", pad=0.01)
cb.set_label("surface moved vs window pod (mm): red = grown out, blue = moved in")
fig.suptitle("POC batch 1: best child d7 vs its parent (production drag, half car, one mesh; re-run pending)", fontsize=13)
fig.savefig(f"{OUT}/poc_d7_vs_window.png", bbox_inches="tight"); plt.close(fig)
print("changed faces: grown >0.3 mm %.0f%%, in <-0.3 mm %.0f%%, median %.2f mm" %
      (100 * (dv > 0.3).mean(), 100 * (dv < -0.3).mean(), np.median(dv[np.abs(dv) > 0.05])))

fig = plt.figure(figsize=(18, 8.2), dpi=150)
for k, i in enumerate((0, 3, 7, 10)):
    m = seed if i == 3 else child if i == 7 else load(i)
    ax = fig.add_subplot(2, 2, 1 + k, projection="3d")
    draw(ax, m, np.tile(np.array([0.95, 0.55, 0.2]) if i in (7, 10) else grey, (len(m.faces), 1)), 30, -50,
         f"{DES[i][0]}: {DES[i][1]:.2f} mN")
fig.suptitle("POC campaign: seeds (grey) and the two best children (orange); production drag, half car", fontsize=13)
fig.savefig(f"{OUT}/poc_lineup.png", bbox_inches="tight"); plt.close(fig)
