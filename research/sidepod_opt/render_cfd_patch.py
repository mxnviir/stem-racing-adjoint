"""What the CFD mesh actually made of a car's supports: the 'supports' wall patch extracted from a kept case
(surfaceMeshExtract -> supports_cfd_0.obj) drawn over the input supports.stl, plus area capture numbers.

    python render_cfd_patch.py <case dir> <car folder> <png>

Looks for: patch faces far from the input surface (wrong snapping, e.g. onto the wheel or body), holes where
the input has surface (thin parts lost), and the captured / input area ratio."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import trimesh


def main(case: Path, car: Path, png: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    cfd = trimesh.load(case / "supports_cfd_0.obj", force="mesh", process=False)
    src = trimesh.load(car / "supports.stl", force="mesh")
    if cfd.vertices[:, 0].max() < 1.0:                     # metres -> mm
        cfd.apply_scale(1e3)
    if src.vertices[:, 0].max() < 1.0:
        src.apply_scale(1e3)
    src_half = src.slice_plane([0, 0, 0], [0, 1, 0]) if src.vertices[:, 1].min() < -1e-3 else src
    _, d, _ = trimesh.proximity.closest_point(src, cfd.triangles_center)
    far = d > 0.5                                            # mm: a patch face this far from the part is wrong
    _, d2, _ = trimesh.proximity.closest_point(cfd, src_half.triangles_center)
    # input faces that SHOULD have no supports patch: glued against or inside the body, on the symmetry plane, or
    # touching the wheel (cfd_trim leaves 0.3 mm; the wheel patch takes those cells)
    body = trimesh.load(car / "car_half.stl", force="mesh")
    if body.vertices[:, 0].max() < 1.0:
        body.apply_scale(1e3)
    tc = src_half.triangles_center
    cp, db, tri = trimesh.proximity.closest_point(body, tc)
    in_body = np.einsum("ij,ij->i", tc - cp, body.face_normals[tri]) < 0   # pocketed into the foam (by design)
    wd = []
    for w in ("wheelF", "wheelR"):
        wm = trimesh.load(car / f"{w}.stl", force="mesh")
        if wm.vertices[:, 0].max() < 1.0:
            wm.apply_scale(1e3)
        wd.append(trimesh.proximity.closest_point(wm, tc)[1])
    hidden = (db < 0.5) | in_body | (tc[:, 1] < 0.3) | (np.min(wd, axis=0) < 0.8)
    lost = (d2 > 0.5) & ~hidden                              # exposed input surface with no patch face near it
    out = {"case": str(case), "cfd_area_mm2": float(cfd.area), "input_half_area_mm2": float(src_half.area),
           "capture_ratio": float(cfd.area / src_half.area),
           "far_faces_area_mm2": float(cfd.area_faces[far].sum()),
           "lost_input_area_mm2": float(src_half.area_faces[lost].sum()),
           "exposed_input_area_mm2": float(src_half.area_faces[~hidden].sum()),
           "exposed_capture_ratio": float(1 - src_half.area_faces[lost].sum() / max(src_half.area_faces[~hidden].sum(), 1e-9)),
           "max_dist_mm": float(d.max())}
    fig = plt.figure(figsize=(16, 10))
    views = [("from below", -90, -90), ("front 3/4", 25, 210), ("rear 3/4", 25, -30)]
    xmid = src_half.vertices[:, 0].mean()
    k = 0
    for side, sel in (("front axle", lambda v: v < xmid), ("rear axle", lambda v: v >= xmid)):
        sv = src_half.vertices[sel(src_half.vertices[:, 0])]
        lo, hi = sv.min(0) - 1, sv.max(0) + 1
        span = (hi - lo).max()
        for t, el, az in views:
            k += 1
            ax = fig.add_subplot(2, 3, k, projection="3d")
            ax.add_collection3d(Poly3DCollection(src_half.triangles, facecolor=(0.6, 0.6, 0.6, 0.12), edgecolor="none"))
            col = np.where(far[:, None], [[0.9, 0.1, 0.1, 1.0]], [[0.15, 0.45, 0.85, 0.85]])
            ax.add_collection3d(Poly3DCollection(cfd.triangles, facecolors=col, edgecolor=(0, 0, 0, 0.2), linewidth=0.1))
            if lost.any():
                c = tc[lost]
                ax.scatter(c[:, 0], c[:, 1], c[:, 2], s=3, c="orange", depthshade=False)
            c0 = (lo + hi) / 2
            ax.set_xlim(c0[0] - span / 2, c0[0] + span / 2); ax.set_ylim(c0[1] - span / 2, c0[1] + span / 2)
            ax.set_zlim(c0[2] - span / 2, c0[2] + span / 2); ax.set_box_aspect((1, 1, 1))
            ax.view_init(el, az); ax.set_title(f"{side}, {t}", fontsize=9); ax.set_axis_off()
    fig.suptitle(f"{case.name}: CFD 'supports' patch (blue; red = >0.5 mm from the part) over the input (grey); "
                 f"orange = exposed input surface with no patch.\n"
                 f"exposed surface captured {out['exposed_capture_ratio']:.3f}, far {out['far_faces_area_mm2']:.1f} mm2, "
                 f"lost {out['lost_input_area_mm2']:.1f} of {out['exposed_input_area_mm2']:.0f} mm2", fontsize=10)
    fig.tight_layout(); fig.savefig(png, dpi=110); plt.close(fig)
    (png.with_suffix(".json")).write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])), indent=1))
