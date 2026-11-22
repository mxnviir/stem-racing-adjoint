"""One car of the layout search: genes -> Parts 1-5 build -> legality -> mass -> SimScale folder.

The whole car is made by the repo's own pipeline (part5-simulation/run_car.py, --gate-only):
Part 1's parametric body (param_body: the halo-canister loft through eight stations from Ref A
to the rear face, sidepods, the cartridge bore, the halo pocket and ballast container, milled
top and bottom with the 3.175 mm ball, 3 mm walls), Part 4's nose cone, front and rear wings,
the official halo and the team's wheels, and Part 5's referee. Wheel supports and tether guides
are left off (user, 2026-11-22: added later), and so is the T4.2 virtual cargo (team rule).

The body is built at a fixed skin (no mass sizing loop): what it weighs is what it weighs, and
below the 48.2 g floor the rest is lead in the T1.22 container under the halo (as in the
sidepod search), so a layout that saves foam is not hidden by the sizing.

    python layout_car.py <out_dir> [--x-json '[...]']      # default: the team-like start car
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
P5 = ROOT / "part5-simulation"
sys.path.insert(0, str(HERE))
import layout_genes as LG  # noqa: E402

FLOOR_G = 48.2                  # T3.6 48.0 + 0.2 margin, as the sidepod search
CARTRIDGE_SHELL_G = 21.15       # Part 2's car_weight_kg includes the empty cartridge (Appendix vi)
CARTRIDGE_OUT_MM = 12.5         # shortest cartridge 64.5 - 52 mm bore: how far it sticks out
CHAMBER_Z_MM = 31.0             # Part 1's chamber axis (geometry_contract.CHAMBER_AXIS_Z_MM)
# Rules waived because the parts are not on the car yet (user, 2026-11-22) or by team rule
WAIVED_PREFIXES = ("T6.", "T7.12", "T4.2", "P4.T6", "T3.6_mass")   # T3.6 is met by the lead below
LEAD_CAP_G = None               # read from Part 1's ballast.capacity_kg("lead") at run time


def run_car_args(d: dict, out: Path) -> list[str]:
    bp = LG.body_params(d)
    return [sys.executable, "-W", "ignore", str(P5 / "run_car.py"), "--out", str(out), "--gate-only",
            "--W", str(d["W"]), "--x-front", str(d["x_front"]), "--d-halo", str(d["d_halo"]),
            "--rear-mm", str(d["rear"]), "--no-supports", "--no-tethers", "--no-cargo", "--skin-mm", "0",
            "--body-json", json.dumps(bp), "--nose-json", json.dumps(d["nose"]),
            "--fwing-json", json.dumps(d["fwing"]), "--rwing-json", json.dumps(d["rwing"])]


def build(x, out: Path, timeout_s=3600) -> dict:
    """Genes -> a built, checked car in `out`. Returns a record (legal, mass, files, why)."""
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    d = LG.decode(x)
    rec = {"genes": [float(v) for v in np.clip(x, 0, 1)], "layout": {k: d[k] for k in ("W", "rear", "halo_rear", "x_front", "d_halo")},
           "decoded": d, "legal": False}
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "part4-simulation"), os.environ.get("PYTHONPATH", "")]))
    t0 = time.time()
    with open(out / "run_car.log", "w") as log:
        try:
            p = subprocess.run(run_car_args(d, out), cwd=P5, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout_s)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    rec["build_s"] = round(time.time() - t0)
    sp = out / "summary.json"
    if rc != 0 or not sp.exists():
        tail = (out / "run_car.log").read_text()[-600:] if (out / "run_car.log").exists() else ""
        rec["why"] = f"build failed ({rc}): {tail}"
        return _save(out, rec)
    S = json.loads(sp.read_text())
    failed = S["legality"]["summary"]["failed"]
    rec["failed_all"] = failed
    rec["failed"] = [f for f in failed if not f.startswith(WAIVED_PREFIXES)]
    rec["mass"] = mass(S, d)
    if rec["mass"]["lead_g"] > rec["mass"]["lead_cap_g"] + 1e-9:
        rec["failed"].append("T1.22_ballast_capacity (lead to reach 48.2 g)")
    rec["legal"] = not rec["failed"]
    if rec["legal"]:
        rec.update(export_cfd(out, d))
    return _save(out, rec)


def _save(out, rec):
    (Path(out) / "layout_car.json").write_text(json.dumps(rec, indent=1, default=float))
    return rec


def mass(S, d) -> dict:
    """Race mass and COM (car frame: x from the nose tip, z from the track), lead filled to 48.2 g."""
    ms = S["mass"]
    car_g = float(ms["manufactured_mass_g"])
    com = ms.get("com_m") or ms.get("com_xyz_m") or ms.get("com")
    if com is None:
        raise KeyError(f"no COM in summary mass keys {sorted(ms)}")
    cx, cz = float(com[0]) * 1e3, float(com[2]) * 1e3
    sys.path.insert(0, str(ROOT / "part1-simulation"))
    import ballast
    cap = ballast.capacity_kg("lead") * 1e3
    lead = max(0.0, FLOOR_G - car_g)
    # lead sits in the container under the halo pocket (centre 34 mm from the pocket front, 6.35 deep)
    lx = d["x_front"] - 16.0 + d["d_halo"] + 34.0
    lz = 24.0 - 6.35 / 2
    rear_face = d["x_front"] + d["W"] + d["rear"]
    ccx = rear_face + CARTRIDGE_OUT_MM - 32.5                   # cartridge centre (65 mm long)
    tot = car_g + lead + CARTRIDGE_SHELL_G
    mx = (car_g * cx + lead * lx + CARTRIDGE_SHELL_G * ccx) / tot
    mz = (car_g * cz + lead * lz + CARTRIDGE_SHELL_G * CHAMBER_Z_MM) / tot
    return dict(car_g=car_g, lead_g=lead, lead_cap_g=cap, race_mass_g=tot, com_x_car_mm=mx, com_z_mm=mz,
                parts_g=S.get("parts_mass_g"))


def export_cfd(out: Path, d) -> dict:
    """body_full.stl (body + nose + halo + wings, whole car, m, car frame) and wheelF/wheelR.stl (+y wheels)
    for simscale_step_domain.build, plus the wheel centres."""
    import manifold3d as mf
    import trimesh
    sys.path.insert(0, str(HERE))
    import cadio as CI
    out = Path(out)
    asm = json.loads((out / "parts" / "assembly.json").read_text())
    halves = [out / "body_half.stl"] + [out / "parts" / f"{n}.stl" for n in ("nose", "halo", "fwing", "rwing")
                                        if (out / "parts" / f"{n}.stl").exists()]
    whole = None
    for p in halves:
        m = trimesh.load(str(p), force="mesh"); m.apply_scale(1e3)          # m -> mm (manifold is float32)
        h = CI.to_manifold(CI.clean(m))
        mir = h.mirror([0.0, 1.0, 0.0])
        part = h + mir
        whole = part if whole is None else whole + part
    full = CI.from_manifold(whole)
    full.apply_scale(1e-3)
    full.export(str(out / "body_full.stl"))
    wheels = {}
    for s in asm["extra_surfaces"]:
        if s["name"] in ("wheelF", "wheelR"):
            wheels[s["name"]] = tuple(s["rotating"]["origin"])
            (out / f"{s['name']}.stl").write_bytes(Path(s["stl"]).read_bytes()) if Path(s["stl"]).parent != out else None
    (out / "wheels.json").write_text(json.dumps(wheels))
    return {"cfd_faces": int(len(full.faces)), "body_full_m3": float(full.volume), "wheels": wheels,
            "watertight": bool(full.is_watertight)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--x-json", default=None)
    a = ap.parse_args()
    x = np.array(json.loads(a.x_json)) if a.x_json else LG.x_default()
    r = build(x, Path(a.out))
    print(json.dumps({k: r.get(k) for k in ("legal", "layout", "failed", "mass", "build_s", "cfd_faces", "why")}, indent=1, default=float))
