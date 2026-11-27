"""Renders of the four POC seeds (rebuilt from the campaign's stored fields), three views each, with their drag."""
import json
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import trimesh

BUILT, CAMPAIGN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
LIGHT = np.array([0.4, -0.6, 0.7]); LIGHT /= np.linalg.norm(LIGHT)
st = json.load(open(f"{CAMPAIGN}/state.json"))
NAMES = {"original": "Team pod", "channel": "Channel pod", "slots": "Slotted pod", "window": "Window pod"}
VIEWS = [("3/4 front", 22, -55), ("top", 89, -90), ("side", 0, -90)]


def load(i):
    m = trimesh.load(f"{BUILT}/bb{i}/car/body_full.stl"); m.apply_scale(1000.0)
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


seeds = [i for i in st["seeds"]]
fig = plt.figure(figsize=(18, 4.1 * len(seeds)), dpi=140)
for r, i in enumerate(seeds):
    d = st["designs"][i]
    v = [x["prod"] for x in d["runs"] if x.get("prod")]
    label = (f"{NAMES.get(d['name'], d['name'])}: {np.mean(v):.2f} mN (mean of {len(v)} meshes), "
             f"pod {d['desc'][0]:.1f} cm3, {d['desc'][1]} through-opening(s)")
    m = load(int(i))
    for c, (vn, e, a) in enumerate(VIEWS):
        ax = fig.add_subplot(len(seeds), 3, 3 * r + c + 1, projection="3d")
        draw(ax, m, np.array([0.72, 0.74, 0.78]), e, a, label if c == 0 else vn)
fig.suptitle("POC campaign seeds (production drag, half car, wall-resolved 2.1 M-cell mesh)", fontsize=13)
fig.savefig(f"{OUT}/poc_seeds.png", bbox_inches="tight"); plt.close(fig)
