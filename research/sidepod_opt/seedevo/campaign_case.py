"""One campaign case on a runner: rebuild the design from its field, fresh wall-resolved mesh on meshing frame k,
production scheme 1000 iterations, optionally the steady model 1200 more; write case_<id>_k<k>.json.

    python -m seedevo.campaign_case <campaign dir> <id> <k> <out dir> [prod|steady]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]


def forces(path):
    rows = [[float(x) for x in re.sub(r"[()]", " ", l).split()] for l in open(path) if l.strip() and not l.startswith("#")]
    return np.array([r[1] for r in rows]) * 1e3


def main(cdir, i, k, out, mode="steady"):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=True)
    rec = {"id": int(i), "k": int(k), "mode": mode, "converged": False}
    car = out / "design"
    py = sys.executable
    r = subprocess.run([py, "-W", "ignore", "-m", "seedevo.campaign", "build", cdir, str(i), str(car)], cwd=HERE,
                       capture_output=True, text=True)
    (out / "build.log").write_text(r.stdout[-5000:] + r.stderr[-5000:])
    if r.returncode != 0:
        rec["error"] = "build: " + (r.stdout + r.stderr)[-300:]
        (out / f"case_{i}_k{k}.json").write_text(json.dumps(rec, indent=1)); return 1
    env = dict(os.environ, GATE_DOMAIN_DX_MM=f"{int(k) * 0.37:.4f}", PRODCHECK_WALL_RESOLVED="1", PRODCHECK_RES="resolved",
               PRODCHECK_RESULTS=str(out), PRODCHECK_KEEP=str(out / "state_prod"), PRODCHECK_ITERS="1000", PRODCHECK_TIMEOUT="16000")
    r = subprocess.run([py, "-W", "ignore", "-u", "prodcheck.py", str(car / "car"), f"c{i}_k{k}", "4", "cold"], cwd=HERE, env=env,
                       capture_output=True, text=True)
    (out / "prodcheck.log").write_text(r.stdout[-20000:] + r.stderr[-20000:])
    f = sorted((out / "state_prod" / "postProcessing" / "forces").glob("*/force.dat"))
    if r.returncode != 0 or not f:
        rec["error"] = "production: " + (r.stdout + r.stderr)[-300:]
        (out / f"case_{i}_k{k}.json").write_text(json.dumps(rec, indent=1)); return 1
    D = forces(f[-1])[-1000:]
    rec["prod"] = float(D.reshape(5, 200).mean(1).mean())
    rec["prod_block_se"] = float(D.reshape(5, 200).mean(1).std(ddof=1) / np.sqrt(5))
    pj = next(out.glob("prodcheck_*.json"), None)
    if pj:
        j = json.loads(pj.read_text()); rec.update(cells=j.get("n_cells"), y_plus_max=j.get("y_plus_max"), prod_converged=j.get("converged"))
    rec["converged"] = True
    if mode == "steady":
        sp = out / "state_prod"
        for t in sorted((p for p in sp.iterdir() if re.fullmatch(r"\d+", p.name)), key=lambda p: -int(p.name)):
            if (t / "polyMesh" / "points").exists():
                (sp / "constant" / "polyMesh" / "points").write_bytes((t / "polyMesh" / "points").read_bytes()); break
        r = subprocess.run([py, "-W", "ignore", "-u", "fine_campaign/steady_base.py", str(sp), str(out / "state_steady"),
                            str(out / "steady"), "4", "1200"], cwd=HERE, capture_output=True, text=True)
        (out / "steady.log").write_text(r.stdout[-5000:] + r.stderr[-5000:])
        f = sorted((out / "state_steady" / "postProcessing" / "forces").glob("*/force.dat"))
        if r.returncode != 0 or not f:
            rec["converged"] = False; rec["error"] = "steady: " + (r.stdout + r.stderr)[-300:]
        else:
            D = forces(f[-1])[-404:]
            rec["steady"] = float(D.mean()); rec["steady_block_se"] = float(D.reshape(4, 101).mean(1).std(ddof=1) / 2)
            b = json.loads((out / "steady" / "base.json").read_text())
            rec["A1_span_mN"], rec["A1_pass"] = b["block_span_last1000_mN"], b["steady_pass"]
    (out / f"case_{i}_k{k}.json").write_text(json.dumps(rec, indent=1, default=float))
    print(json.dumps(rec, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:6]))
