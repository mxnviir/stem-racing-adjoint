"""Wheel supports for the sidepod / free-form car: a thin adapter over the engines the repo already has.

The architecture (owner, 2026-11-22, cad/example_car.step): per axle ONE printed ABS part, wheel to wheel:
  pod    a hollow shell that IS the car's lower body at the axle (flush with the body: its outside is the
         body's own surface); the foam is milled away there from below
  neck   the short flare between the body's side and the disc
  disc   a thin flat cylinder covering the wheel's open inner side
  boss   the fillet from the disc down to the axle
  stub   the axle itself, the bearing pressed onto it; the wheel (rim, spokes) turns on the bearing

Two sources, same interface:
  kind="cad"   the team's own support solids (part1-simulation/hardware_cad/*_wheel_support.stl, the same solids
               as in cad/example_car.step), placed at each axle. Exact for the trial car's layout and body.
  kind="beam"  part4-simulation/beam_support.py: the same architecture built from numbers and SIZED FOR LOADS,
               following any body and any axle position (for the layout and shape searches).

    python supports.py add <car folder> [--kind cad|beam] [--out <new folder>]
        copies the car folder, writes supports.stl (right half, metres, car frame) as a fixed CFD wall patch
        in assembly.json, hubcaps (beam), and supports.json (mass, centre of mass, rule and load gates)
    python supports.py compare
        the engine's parts against the example car's solids, by cross-section along the axle

Until now this pipeline's CFD car had NO supports: at both axles there was open air under the body where the
printed pod sits. A car with supports is therefore a NEW BASELINE; never compare it with a car without.
Nothing here changes a default: geometry.py and the running queues are untouched (opt-in).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in ("part4-simulation", "part1-simulation", "part2-simulation"):
    sys.path.insert(0, str(ROOT / p))

ABS_G_CM3 = 1.04
TRACK_CLEARANCE_MM = 1.5            # T3.7
EXAMPLE_STEP = HERE / "cad" / "example_car.step"


def _wheels(folder: Path) -> dict:
    """Axle x, wheel inner face y, width and radius of each axle, mm, from the car folder's wheel STLs."""
    import trimesh
    out = {}
    for tag, name in (("front", "wheelF"), ("rear", "wheelR")):
        b = trimesh.load(folder / f"{name}.stl").bounds * 1e3
        out[tag] = {"x": float(b[:, 0].mean()), "y_in": float(b[0, 1]), "w": float(b[1, 1] - b[0, 1]),
                    "R": float((b[1, 0] - b[0, 0]) / 2), "z_axle": float(b[:, 2].mean())}
    return out


def _half(mesh):
    """Right half (y >= 0), capped at y = 0."""
    import trimesh
    return trimesh.intersections.slice_mesh_plane(mesh, [0, 1, 0], [0, 0, 0], cap=True)


def build(body_half, wheels: dict, kind: str = "cad", bs=None) -> dict:
    """Supports for one car. body_half: right-half body mesh (metres, car frame: x from the nose, y >= 0).
    wheels: _wheels() dict. Returns {"mesh": right-half supports (one mesh), "hubcaps": [...],
    "axles": {front|rear: {mass_g (both sides), com_mm, gates, mode, ...}}, "mass_g", "com_mm", "ok"}."""
    import trimesh
    axles, meshes, caps = {}, [], []
    if kind == "cad":
        import hardware_geometry as hg
        for tag, w in wheels.items():
            m = hg.build_wheel_assembly(tag, w["x"])[f"{tag}_wheel_support_right"]
            m = _half(m) if m.bounds[0, 1] < -1e-6 else m
            low = float(m.bounds[0, 2] * 1e3)
            r = np.hypot((m.vertices[:, 0] * 1e3 - w["x"]), (m.vertices[:, 2] * 1e3 - w["z_axle"])).max()
            axles[tag] = {"mode": "team CAD", "mass_g": float(2 * m.volume * 1e9 * ABS_G_CM3 * 1e-3),
                          "com_mm": (m.center_mass * 1e3).round(3).tolist(),
                          "gates": {f"T3.7_{tag}_support_clearance": low - TRACK_CLEARANCE_MM,
                                    f"T7.12.1_{tag}_support_in_cylinder": float(w["R"] - r)}}
            meshes.append(m)
    elif kind == "beam":
        import beam_support as bsm
        import wheel as wh
        bs = bs or bsm.BeamSupport()
        for (tag, w), hub in zip(wheels.items(), wh.hub_span_mm()):
            ch = bsm.pod_channel(bs, body_half, w["x"], w["z_axle"], w["R"]) if bs.pod else {}
            bm = bsm.build(bs, w["x"], w["z_axle"], w["y_in"], w["w"], True, hub_mm=hub, R_mm=w["R"], channel=ch)
            g = {k: float(v) for k, v in bsm.gates(bs, bm, w["x"], w["z_axle"], w["R"], tag).items()}
            m = bm["support"]
            axles[tag] = {"mode": bm["support_mode"], "mass_g": float(bsm.mass_kg(bs, bm) * 1e3),
                          "com_mm": (m.center_mass * 1e3).round(3).tolist(), "gates": g,
                          "channel": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in ch.items()},
                          "structure": {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                                        for k, v in bm["_struct"].items()}}
            meshes.append(m)
            if bm["hubcap"] is not None:
                caps.append((tag, bm["hubcap"]))
    else:
        raise ValueError(f"kind must be 'cad' or 'beam', not {kind!r}")
    mass = sum(a["mass_g"] for a in axles.values())
    com = sum(np.array(a["com_mm"]) * a["mass_g"] for a in axles.values()) / mass
    com[1] = 0.0                                                    # both sides: on the centre plane
    failed = sorted(k for a in axles.values() for k, v in a["gates"].items() if v < -1e-9)
    return {"kind": kind, "mesh": trimesh.util.concatenate(meshes), "hubcaps": caps, "axles": axles,
            "mass_g": float(mass), "com_mm": com.round(3).tolist(), "failed_gates": failed, "ok": not failed}


def add_to_folder(folder: Path, out: Path | None = None, kind: str = "cad") -> dict:
    """Car folder -> the same car WITH supports as a fixed wall patch `supports` (assembly.json), plus supports.json."""
    import trimesh
    folder = Path(folder)
    out = Path(out) if out else folder.parent / f"{folder.name}_sup_{kind}"
    if out.resolve() != folder.resolve():
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(folder, out, ignore=shutil.ignore_patterns("_body_half.stl"))
    body = trimesh.load(out / "car_half.stl", force="mesh")
    s = build(body, _wheels(out), kind)
    _write_ascii(s["mesh"], out / "supports.stl", "supports")       # Part 2 reads ASCII STLs with a named solid
    for tag, cap in s["hubcaps"]:
        cap.export(out / f"hubcap_{tag}.stl")
    a = json.loads((out / "assembly.json").read_text())
    a["extra_surfaces"] = [e for e in a["extra_surfaces"] if e["name"] != "supports"] + \
                          [{"name": "supports", "stl": "supports.stl", "rotating": None}]
    a["supports"] = kind
    a["label"] = f"{a.get('label', folder.name)}+sup_{kind}"
    (out / "assembly.json").write_text(json.dumps(a, indent=1))
    rep = {k: v for k, v in s.items() if k not in ("mesh", "hubcaps")}
    rep["overlap_with_body_mm3"] = _overlap(body, s["mesh"])
    rep["note"] = ("mass and COM of both sides; this pipeline's other_parts_g (22.52 g, assumed) already includes "
                   "the supports, so do not add this mass on top")
    (out / "supports.json").write_text(json.dumps(rep, indent=1))
    return dict(rep, folder=str(out))


def _write_ascii(mesh, path: Path, name: str):
    import trimesh
    lines = trimesh.exchange.stl.export_stl_ascii(mesh).splitlines()
    lines[0], lines[-1] = f"solid {name}", f"endsolid {name}"
    Path(path).write_text("\n".join(lines) + "\n")


def _overlap(body, sup) -> float | None:
    """Volume (mm^3) the supports share with the body: > 0 means a pocket has to be milled there."""
    try:
        import cadio as CI
        inter = CI.to_manifold(body) ^ CI.to_manifold(sup)
        return float(CI.from_manifold(inter).volume * 1e9)
    except Exception:
        return None


def profile(mesh, ys_mm, scale: float = 1.0):
    """Cross-section area (mm^2) and extents along the axle direction: the part's signature."""
    rows = []
    for y in ys_mm:
        sec = mesh.section(plane_origin=[0, y / scale, 0], plane_normal=[0, 1, 0])
        if sec is None:
            rows.append((y, 0.0, 0.0, 0.0)); continue
        p, _ = sec.to_2D()
        b = p.bounds * scale
        rows.append((y, float(p.area * scale ** 2), float(b[1][0] - b[0][0]), float(b[1][1] - b[0][1])))
    return rows


def compare():
    """The engine (beam) and the team CAD against cad/example_car.step, by section along the axle."""
    import trimesh
    import cadio as CI
    import hardware_geometry as hg
    sol = CI.read_step_solids(str(EXAMPLE_STEP))
    for tag, name, x, y_in in (("front", "Front Wheel Support", 173.24, 19.25), ("rear", "Rear Wheel Support", 35.24, 16.25)):
        ex = CI.tessellate(sol[name])
        cad = hg.build_wheel_assembly(tag, 0.0)[f"{tag}_wheel_support_right"]
        print(f"\n== {tag}: example solid {ex.volume:.1f} mm3 = {ex.volume * ABS_G_CM3 / 1e3:.3f} g (both sides); "
              f"repo CAD right half x2 = {2 * cad.volume * 1e9 * ABS_G_CM3 / 1e3:.3f} g; lowest point {ex.bounds[0, 2]:.2f} mm "
              f"(T3.7 needs >= {TRACK_CLEARANCE_MM})")
        ys = [2, 6, 10, 14, y_in - 1.5, y_in - 0.5, y_in + 0.3, y_in + 1.2, y_in + 2.5, y_in + 5, y_in + 12]
        pe = profile(ex, ys); pc = profile(cad, ys, 1e3)
        print("   y mm | example: area, x-extent, z-extent | repo CAD: area, x-extent, z-extent")
        for (y, a, dx, dz), (_, a2, dx2, dz2) in zip(pe, pc):
            print(f"  {y:5.2f} | {a:7.1f} {dx:6.2f} {dz:6.2f} | {a2:7.1f} {dx2:6.2f} {dz2:6.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["add", "compare"])
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--kind", default="cad", choices=["cad", "beam"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.cmd == "compare":
        compare()
    else:
        r = add_to_folder(Path(a.folder), a.out, a.kind)
        print(json.dumps(r, indent=1, default=float))
