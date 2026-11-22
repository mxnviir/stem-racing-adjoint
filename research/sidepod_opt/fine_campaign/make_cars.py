"""Rebuild every car of the fine-mesh campaign from code, on any machine (the run folders are not in git).

    python fine_campaign/make_cars.py [out_dir]      (default: runs/fine_cars)  -> <out>/<tag>/car
    python fine_campaign/make_cars.py --check        rebuild into a temp dir, compare with runs/ here

Every recipe is the one used on 2026-11-20/21 (ROUTES.md): the shape-loop seeds, the blends, the window
cut, design 8 of run cloud_original (its field is in git), and the "_p05 / _m05" copies whose field is
nudged by +/-0.05 mm. Those copies are NOT repeat meshes: through the 1 mm voxel builder the nudge moves parts
of the surface by 0.2-1.5 mm (the script prints the distance for each). Repeat meshes use the unchanged car
with the meshing frame shifted: campaign tags "<design>~k" (ROUTES.md 2026-11-21 16:05).
"""
import sys
from pathlib import Path
import numpy as np
from scipy import ndimage

HERE = Path(__file__).resolve().parent
SP = HERE.parent
sys.path.insert(0, str(SP)); sys.path.insert(0, str(SP.parents[1] / "part2-simulation"))
import shape_loop as SL  # noqa: E402

FIELD_IT8 = SP / "runs" / "cloud_original" / "it_008" / "field.npz"
# tag -> existing local folder it must match (for --check)
LOCAL = {"team": "runs/cloud_original/it_000/car", "nopod": "runs/cloud_lean/it_000/car", "groove": "runs/concepts/channel/car",
         "blend50": "runs/concepts/blend50/car", "blend75": "runs/concepts/blend75/car", "win3": "runs/concepts/win3/car",
         "win5": "runs/concepts/win5/car", "adjoint8": "runs/cloud_original/it_008/car", "team_p05": "runs/concepts/seed_p05/car",
         "team_m05": "runs/concepts/seed_m05/car", "groove_p05": "runs/concepts/channel_p05/car", "adjoint8_p05": "runs/concepts/it8_p05/car"}


def windows(car, f0, xs_list, wall=3.0):
    """Vertical through-windows between the cargo cover + wall and the pod's outer skin - wall (as built 2026-11-21)."""
    s = car.s
    X, AY = car.X, np.abs(car.Y)
    hw = 5.0 + (X - s.cargo_x[0]) / (s.cargo_x[1] - s.cargo_x[0]) * 22.5
    B0 = car.finish(f0) & car.region
    ymax_pod = np.where(B0.any(2), AY[:, :, 0], 0).max(1)
    cut = np.zeros(f0.shape, bool)
    yin = np.where(X < s.cargo_x[0], s.spine_y + wall, np.maximum(hw, s.spine_y) + wall)
    yout = ymax_pod[:, None, None] - wall
    for x0, x1 in xs_list:
        cut |= (X >= x0) & (X <= x1) & (AY >= yin) & (AY <= yout)
    d = ndimage.distance_transform_edt(~cut) * car.h
    return np.minimum(f0, d - 0.5 * car.h - 1e-6 + np.where(cut, -50.0, 0.0))


def fields(car):
    S = SL.seeds(car)
    so, sl = car.sdf_original.astype(float), car.sdf_lean.astype(float)
    team_rules = SL.build_design(car, S["original"])["f_rules"]
    f8 = np.load(FIELD_IT8)["f"]
    out = {
        "team": S["original"], "nopod": S["lean"], "groove": S["channel"],
        "blend50": 0.5 * so + 0.5 * sl, "blend75": 0.75 * so + 0.25 * sl,
        "win3": windows(car, so, [(60, 72), (80, 92), (100, 112)]),
        "win5": windows(car, so, [(55, 63), (67, 75), (79, 87), (91, 99), (103, 111)]),
        "adjoint8": f8,
        "adjoint8_p05": f8 + 0.05 * car.region, "adjoint8_m05": f8 - 0.05 * car.region,
    }
    # repeat-mesh copies: the RAW field shifted by +/-0.05 mm, so the surface moves by ~0.05 mm everywhere
    # (measured: 99.9 % of win3_p05 within 0.04 mm). The earlier copies (medium mesh, 2026-11-21) shifted the
    # rule-folded field instead, which also moves parts of the surface by up to 0.25-0.45 mm (team_m05 0.33,
    # old win3_p05 0.61 mm at the window edges): ROUTES.md 2026-11-21 16:00.
    for k, sh in (("team", 0.05), ("team", -0.05), ("groove", 0.05), ("groove", -0.05), ("nopod", 0.05),
                  ("win3", 0.05), ("blend50", 0.05), ("blend75", 0.05)):
        out[f"{k}_{'p' if sh > 0 else 'm'}05"] = np.asarray(out[k], float) + sh * car.region
    return out


def main():
    check = "--check" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0]) if args else SP / "runs" / "fine_cars"
    if check:
        import tempfile
        out = Path(tempfile.mkdtemp())
    car = SL.load_car()
    vox = {}
    for tag, f in fields(car).items():
        b = SL.build_design(car, np.asarray(f, float))
        if not b["check"]["ok"]:
            print(tag, "FAILED the build check", b["check"], flush=True)
            continue
        folder = SL.export_design(car, b, out / tag, tag)
        if tag.endswith(("_p05", "_m05")) and tag[:-4] in vox:
            # a repeat copy must be the same surface moved by ~0.05 mm: every sampled point within 0.2 mm
            pts = b["mesh"].sample(20000, return_index=False) if hasattr(b["mesh"], "sample") else b["mesh"].vertices
            import trimesh
            d = np.abs(trimesh.proximity.signed_distance(vox[tag[:-4]], pts))
            q99, q999, mx = np.percentile(d, 99), np.percentile(d, 99.9), d.max()
            flag = "OK" if q99 <= 0.1 else "NOT A CLEAN REPEAT"
            print(f"   {tag}: surface vs {tag[:-4]}: p99 {q99:.3f} p99.9 {q999:.3f} max {mx:.3f} mm -> {flag}", flush=True)
            if q99 > 0.1 and "--strict" in sys.argv:
                raise SystemExit(f"{tag} is not a clean repeat of {tag[:-4]}")
        vox[tag] = b["mesh"]
        line = f"{tag:14s} pod {(b['voxels'] & car.region).sum() * 1e-3:5.1f} cm3  mass {b['mass']['race_mass_g']:.2f} g  lead {b['mass']['lead_g']:.2f} g  volume {b['mesh'].volume:.1f} mm3"
        if check and tag in LOCAL and (SP / LOCAL[tag] / "car_half.stl").exists():
            import trimesh
            a = trimesh.load(folder / "car_half.stl"); r = trimesh.load(SP / LOCAL[tag] / "car_half.stl")
            line += f"  | vs {LOCAL[tag]}: dV {a.volume - r.volume:+.3f} mm3, verts {len(a.vertices)} vs {len(r.vertices)}"
        print(line, flush=True)


if __name__ == "__main__":
    main()
