"""Reported, not marked (test TR): the coarse DAFoam gradient's first-order prediction for each probe move, beside
the measured change. Rebuilds each move exactly as the workflow did (seedevo.probe_step, peak 0.5 mm, smoothed
normals, 1.5 mm clearance) from the committed design and the run's DAFoam gradient.

    python -m seedevo.tr_predict <gate results folder>   -> <folder>/tr_predict.json
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
MOVES = {"dn": "dafnpz:{p}", "up": "dafopp:{p}", "r101": "rnd101", "r102": "rnd102"}


def main(root):
    root = Path(root).resolve()
    os.environ.update(GATE_RES="resolved", STEP_NORMAL_SIGMA_MM="1.5", STEP_ZMIN_MM="1.5")
    tmp = Path(tempfile.mkdtemp())
    os.environ["GATE_RESULTS"] = str(tmp / "gr")
    sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "esi"))
    import trimesh
    import gate
    import make_step as MS
    from seedevo import probe_step as PS
    out = {}
    for des in ("original", "channel", "slots", "window"):
        npz = root / "daf" / f"daf-{des}" / f"daf-{des}" / "dafoam_sens.npz"
        if not npz.exists():
            out[des] = {"error": "no DAFoam gradient"}; continue
        with tarfile.open(HERE / "seedevo" / "designs" / f"{des}.tgz") as t:
            t.extractall(tmp, filter="data")
        car = tmp / des / "car"
        rel = os.path.relpath(npz, HERE)
        base = trimesh.load(car / "car_half.stl")
        V, N, A = base.vertices, base.vertex_normals, MS.vertex_area(base)
        dens = MS.daf_density(V, N, A, npz)                        # dD (N, half car) per unit area per m of outward move
        rec = {}
        for mv, f in MOVES.items():
            name = f"pred_{des}_{mv}"
            PS.main(str(car), name, f.format(p=rel), "0.5")
            w = np.load(gate.G / f"bump_{name}" / "move_m.npy")
            rec[mv] = float((dens * A * w).sum() * 1e3)           # mN, half car
            shutil.rmtree(gate.G / f"bump_{name}", ignore_errors=True)
        out[des] = rec
    (root / "tr_predict.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
