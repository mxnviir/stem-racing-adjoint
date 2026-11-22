"""Close-up pictures of one car's wheel supports (support_engine.py), to inspect every design by eye.

    python search/layout/support_render.py CAR_DIR [PNG]

Per axle: the section through the axle (body, saddle, arm, disc, axle, wheel), the section along the
arm, the support seen from below and from the front three-quarter with the body, and the support alone.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
import repo_paths  # noqa: E402,F401
import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

import layout_render as LR  # noqa: E402

LR.COLOURS.setdefault("supports", "#e8892b")
LR.COLOURS.setdefault("hubcaps", "#c0602a")


def _full(path, scale=1e3):
    import trimesh
    m = trimesh.load(str(path), force="mesh"); m.apply_scale(scale)
    mir = m.copy(); mir.vertices[:, 1] *= -1; mir.invert()
    return trimesh.util.concatenate([m, mir])


def _crop(m, lo, hi):
    """Faces of m whose centre is inside the box (a picture crop, not a solid)."""
    c = m.triangles_center
    keep = np.all((c >= lo) & (c <= hi), axis=1)
    out = m.copy(); out.update_faces(keep); out.remove_unreferenced_vertices()
    return out


def render(folder: Path, png: Path | None = None) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    folder = Path(folder)
    asm = json.loads((folder / "parts" / "assembly.json").read_text())
    info = asm.get("info", {}).get("support_engine", {})
    M = {"body": _full(folder / "body_half.stl"), "supports": _full(folder / "parts" / "supports.stl")}
    for w in ("wheelF", "wheelR"):
        M[w] = _full(folder / "parts" / f"{w}.stl")
    caps = [p for p in (folder / "parts").glob("hubcap_*.stl")]
    if caps:
        import trimesh
        M["hubcaps"] = trimesh.util.concatenate([_full(p) for p in caps])
    # sections: each half its own closed mesh (two halves fused into one mesh cut badly on the centre plane)
    import trimesh
    H = {}
    for k, p in [("body", folder / "body_half.stl"), ("supports", folder / "parts" / "supports.stl"),
                 ("wheelF", folder / "parts" / "wheelF.stl"), ("wheelR", folder / "parts" / "wheelR.stl")] + \
            [("hubcaps", p) for p in caps]:
        m = trimesh.load(str(p), force="mesh"); m.apply_scale(1e3)
        mir = m.copy(); mir.vertices[:, 1] *= -1; mir.invert()
        H[k + "_r" + p.stem] = m
        H[k + "_l" + p.stem] = mir
    for k in list(H):
        LR.COLOURS.setdefault(k, LR.COLOURS.get(k.split("_")[0], "#888"))
    X, Y, Z = np.eye(3)
    below34 = np.array([[0.80, 0.60, 0.0], [-0.26, 0.35, -0.90], [-0.54, 0.72, 0.44]])
    below34 /= np.linalg.norm(below34, axis=1)[:, None]
    front34 = np.array([[0.60, -0.80, 0.0], [0.30, 0.22, 0.93], [-0.74, -0.56, 0.37]])
    front34 /= np.linalg.norm(front34, axis=1)[:, None]
    xs = {"front": asm["x_front_mm"], "rear": asm["x_front_mm"] + asm["W_mm"]}
    fig = plt.figure(figsize=(26, 12))
    gs = fig.add_gridspec(2, 5)
    for row, tag in enumerate(("front", "rear")):
        x = xs[tag]
        lo, hi = np.array([x - 24, -45, -1]), np.array([x + 24, 45, 50])
        C = {k: _crop(m, lo, hi) for k, m in M.items()}
        C = {k: m for k, m in C.items() if len(m.faces)}
        LR.section(fig.add_subplot(gs[row, 0]), H, [x, 0, 0], [1, 0, 0], Y, Z,
                   f"{tag}: section through the axle (x {x:.1f})")
        st = info.get(tag, {})
        ymid = 0.5 * (st.get("y_body_side_mm", 14) + st.get("y_disc_inner_mm", 20))
        ax = fig.add_subplot(gs[row, 1])
        LR.section(ax, H, [0, ymid, 0], [0, 1, 0], X, Z,
                   f"{tag}: section along the arm (y {ymid:.1f})")
        ax.set_xlim(x - 22, x + 22); ax.set_ylim(-1, 32)
        Cr = {k: m for k, m in C.items() if not k.startswith("wheel")}
        for col, (name, R, mm) in enumerate((("from below (wheels off)", np.array([X, Y, -Z]), Cr),
                                              ("front three-quarter, from below", below34, C),
                                              ("the support alone", front34,
                                               {k: m for k, m in C.items() if k in ("supports", "hubcaps")}))):
            img, ext = LR.shaded(mm, R, n_per_mm2=220)
            ax = fig.add_subplot(gs[row, 2 + col]); ax.imshow(img, extent=ext); ax.axis("off")
            ax.set_title(f"{tag}: {name}", fontsize=10)
    d = info.get("design", {})
    fig.suptitle("generated wheel supports: " + ", ".join(f"{k} {v:.3g}" if isinstance(v, float) else f"{k} {v}"
                                                            for k, v in d.items()), fontsize=10)
    fig.tight_layout()
    png = Path(png) if png else folder / "supports.png"
    fig.savefig(png, dpi=80); plt.close(fig)
    return png


if __name__ == "__main__":
    print(render(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None))
