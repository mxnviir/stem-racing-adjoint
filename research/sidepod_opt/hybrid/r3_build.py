"""Generation 2 (round 3, hybrid/HYBRID_TEST.md): children of the accepted parent, chained explicit morph (the mesh is
morphed onto the parent first, then by each child's 0.5 mm increment), predictions on record, resolved_bumps request.
    python hybrid/r3_build.py <parent spec f@amp[+f@amp]> <fresh dafoam npz (rel. to sidepod_opt)> [amp_mm]"""
import json, subprocess, sys
from pathlib import Path
parent, fresh = sys.argv[1], sys.argv[2]
amp = sys.argv[3] if len(sys.argv) > 3 else "0.5"
kids = {"g2_zero": "zero", "g2_daffresh": f"dafnpz:{fresh}", "g2_dafbase": "daf", "g2_esi": "esi_frozen",
        "g2_guided": "vec:hybrid/r2/guided.npy", "g2_es": "vec:hybrid/r2/es.npy", **{f"g2_rnd{k}": f"rnd{k}" for k in range(11, 17)}}
E1 = dict(site="step", direct="1", nsig="1.5", mask="0", explicit="1", zmin="1.5", chainparent=parent)
cases = [dict(name=f"step_{n}", field=f, amp=("0" if f == "zero" else amp), **E1) for n, f in kids.items()]
r = {"note": f"hybrid round 3 = generation 2: parent {parent} (chained morph) + one {amp} mm move each",
     "steady_release": "resolved-steady-45125305486", "bumpgeom_run": 45188798730, "cases": cases, "attempt": 5}
Path("../../.github/resolved_bumps_request.json").write_text(json.dumps(r, indent=1))
specs = [f"{n}:{parent}+{f}@{amp}:0" for n, f in kids.items() if f != "zero"] + [f"g2_zero:{parent}:0"]
subprocess.run([sys.executable, "-W", "ignore", "esi/predict_candidates.py", "hybrid/pred_r3.json", *specs], check=True)
