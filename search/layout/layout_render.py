"""Pictures of a layout_car.py car folder: shaded views (z-buffered surface samples, so parts hide
each other correctly) and section cuts that show how the parts meet (gaps and voids are white).

    python layout_render.py <car_folder> [out.png]
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
import repo_paths  # noqa: E402,F401
import json
import sys
from pathlib import Path

import numpy as np

COLOURS = {"body": "#9aa7b4", "wheelF": "#2a2a2a", "wheelR": "#2a2a2a", "supports": "#d0862f",
           "halo": "#c03a2b", "fwing": "#2b6cb0", "rwing": "#2b6cb0", "tethers": "#6b8e23", "nose": "#7f5aa2"}
PX = 0.2          # mm per pixel


def load(folder: Path, cfd: bool = False) -> dict:
    """{name: full (both sides) mesh in mm}. cfd: the merged one-piece car that goes to the CFD
    (body_full.stl from layout_car.export_cfd) and the wheels, instead of the separate parts."""
    import trimesh
    asm = json.loads((folder / "parts" / "assembly.json").read_text())
    if cfd:
        car = trimesh.load(str(folder / "body_full.stl"), force="mesh"); car.apply_scale(1e3)
        out = {"body": car}
        for w in ("wheelF", "wheelR"):
            m = trimesh.load(str(folder / f"{w}.stl"), force="mesh"); m.apply_scale(1e3)
            mir = m.copy(); mir.vertices[:, 1] *= -1; mir.invert()
            out[w] = trimesh.util.concatenate([m, mir])
        return out
    halves = {"body": folder / "body_half.stl"}
    for s in asm["extra_surfaces"]:
        p = Path(s["stl"])
        halves[s["name"]] = p if p.exists() else folder / "parts" / p.name
    out = {}
    for k, p in halves.items():
        m = trimesh.load(str(p), force="mesh"); m.apply_scale(1e3)
        mir = m.copy(); mir.vertices[:, 1] *= -1; mir.invert()
        out[k] = trimesh.util.concatenate([m, mir])
    return out


def shaded(meshes, R, light=(0.35, -0.45, 0.82), n_per_mm2=60, clip=None):
    """Orthographic picture looking along -z' of the rotated frame R (rows = image x, image y, towards viewer)."""
    import matplotlib
    import trimesh
    P, C = [], []
    light = np.asarray(light) / np.linalg.norm(light)
    for k, m in meshes.items():
        n = int(min(6e6, max(2e4, m.area * n_per_mm2)))
        pts, fi = trimesh.sample.sample_surface(m, n, seed=0)
        nr = m.face_normals[fi]
        if clip is not None:
            keep = clip(pts); pts, nr = pts[keep], nr[keep]
        q = pts @ R.T
        sh = 0.35 + 0.65 * np.clip((nr @ R.T) @ light, 0, 1)
        P.append(q); C.append(np.array(matplotlib.colors.to_rgb(COLOURS.get(k, "#888888")))[None] * sh[:, None])
    P, C = np.vstack(P), np.vstack(C)
    lo, hi = P.min(0), P.max(0)
    w, h = int((hi[0] - lo[0]) / PX) + 3, int((hi[1] - lo[1]) / PX) + 3
    ix = ((P[:, 0] - lo[0]) / PX).astype(int) + 1
    iy = h - 2 - ((P[:, 1] - lo[1]) / PX).astype(int)
    order = np.argsort(P[:, 2])                                  # far first: nearer points overwrite
    img = np.ones((h, w, 3))
    for dx in (0, 1):                                            # 2-pixel splat closes pinholes
        for dy in (0, 1):
            img[np.clip(iy[order] + dy, 0, h - 1), np.clip(ix[order] + dx, 0, w - 1)] = C[order]
    return img, (lo[0], hi[0], lo[1], hi[1])


def section(ax, meshes, origin, normal, u, v, title):
    """Filled cut of every part by a plane; u, v are the picture's axes (unit vectors)."""
    import matplotlib
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MPath
    for k, m in meshes.items():
        try:
            sec = m.section(plane_origin=origin, plane_normal=normal)
        except Exception:                                        # noqa: BLE001
            sec = None
        if sec is None:
            continue
        verts, codes = [], []
        for loop in sec.discrete:
            p2 = np.c_[loop @ u, loop @ v]
            verts += list(p2); codes += [MPath.MOVETO] + [MPath.LINETO] * (len(p2) - 2) + [MPath.CLOSEPOLY]
        if verts:
            ax.add_patch(PathPatch(MPath(verts, codes), facecolor=COLOURS.get(k, "#888"), edgecolor="k", lw=0.3))
    ax.set_aspect("equal"); ax.autoscale_view(); ax.set_title(title, fontsize=9)
    ax.tick_params(labelsize=6)


def render(folder: Path, png: Path | None = None, cfd: bool = False) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    M = load(folder, cfd)
    X, Y, Z = np.eye(3)
    iso = np.array([[0.80, -0.60, 0.0], [0.26, 0.35, 0.90], [-0.54, -0.72, 0.44]])
    iso_r = np.array([[-0.80, -0.60, 0.0], [-0.26, 0.35, 0.90], [0.54, -0.72, 0.44]])
    views = [("side", np.array([X, Z, -Y])), ("top", np.array([X, -Y, Z])), ("underside", np.array([X, Y, -Z])),
             ("front", np.array([Y, Z, -X])), ("rear", np.array([-Y, Z, X])), ("front three-quarter", iso),
             ("rear three-quarter", iso_r)]
    fig = plt.figure(figsize=(20, 22))
    gs = fig.add_gridspec(6, 2, height_ratios=[1.0, 1.4, 1.4, 1.5, 1.0, 1.0])
    slots = [gs[0, 0], gs[1, 0], gs[1, 1], None, None, gs[3, 0], gs[3, 1]]
    for (name, R), slot in zip(views, slots):
        if slot is None:
            continue
        img, ext = shaded(M, R)
        ax = fig.add_subplot(slot); ax.imshow(img, extent=ext); ax.set_title(name, fontsize=10); ax.axis("off")
    sub = gs[2, :].subgridspec(1, 2)
    for i, name in enumerate(("front", "rear")):
        img, ext = shaded(M, dict(views)[name])
        ax = fig.add_subplot(sub[0, i]); ax.imshow(img, extent=ext); ax.set_title(name, fontsize=10); ax.axis("off")
    # half the car removed: what the centre plane cuts, shaded
    img, ext = shaded(M, np.array([X, Z, -Y]), clip=lambda p: p[:, 1] <= 0.0)
    ax = fig.add_subplot(gs[0, 1]); ax.imshow(img, extent=ext); ax.set_title("side, near half removed (cut at the centre plane)", fontsize=10); ax.axis("off")
    section(fig.add_subplot(gs[4, 0]), M, [0, 0.05, 0], [0, 1, 0], X, Z, "section on the centre plane (y = 0): white inside the outline is a void")
    section(fig.add_subplot(gs[4, 1]), M, [0, 0, 24.5], [0, 0, 1], X, Y, "plan section at z = 24.5 mm (halo pocket level)")
    asm = json.loads((folder / "parts" / "assembly.json").read_text())
    xf, W = asm["x_front_mm"], asm["W_mm"]
    sub2 = gs[5, :].subgridspec(1, 4)
    lay = json.loads((folder / "layout_car.json").read_text())["layout"] if (folder / "layout_car.json").exists() else {}
    rear_face = xf + W + lay.get("rear", 56.0)
    for i, (x, t) in enumerate(((xf - 10, "x: 6 mm behind Ref A"), (xf + lay.get("d_halo", 44) - 16 + 25, "x: halo pocket middle"),
                                (rear_face - 60, "x: 8 mm ahead of the bore end"), (rear_face - 20, "x: 20 mm ahead of the rear face (chamber)"))):
        section(fig.add_subplot(sub2[0, i]), M, [x, 0, 0], [1, 0, 0], Y, Z, t)
    fig.tight_layout()
    png = png or folder / ("car_cfd.png" if cfd else "car.png")
    fig.savefig(png, dpi=90); plt.close(fig)
    return png


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--cfd"]
    print(render(Path(args[0]), Path(args[1]) if len(args) > 1 else None, cfd="--cfd" in sys.argv))
