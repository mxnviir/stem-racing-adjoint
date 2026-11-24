"""Agreement of two DAFoam gradients through what they predict for the round-1 moves (hybrid/pred_r1.json specs),
the measure that matters for a step proposer. Also the cosine of the raw point gradients when the points match.
    python hybrid/compare_gradients.py <new dafoam_sens.npz> <ref dafoam_sens.npz> <out.json>"""
import json, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "esi"))
import predict_candidates as PC   # noqa: E402

new, ref = np.load(sys.argv[1]), np.load(sys.argv[2])
specs = json.loads((HERE / "hybrid/pred_r1.json").read_text())
pn, pr = [], []
for k, s in specs.items():
    w = PC.move(s["field"], s["amp_mm"])
    for S, lst in ((new, pn), (ref, pr)):
        lst.append(float((S["dD_dXs"] * PC.displacement_at(S["Xs"], PC.V, PC.N * w[:, None])).sum()) * 1e3)
pn, pr = np.array(pn), np.array(pr)
out = {"moves": list(specs), "pred_new_mN": pn.tolist(), "pred_ref_mN": pr.tolist(),
       "r": float(np.corrcoef(pn, pr)[0, 1]), "slope_new_per_ref": float(pn @ pr / (pr @ pr)),
       "D_new_N": float(new["D_N"]), "D_ref_N": float(ref["D_N"])}
if new["Xs"].shape == ref["Xs"].shape and np.allclose(new["Xs"], ref["Xs"], atol=1e-7):
    a, b = new["dD_dXs"].ravel(), ref["dD_dXs"].ravel()
    out["cos_points"] = float(a @ b / np.linalg.norm(a) / np.linalg.norm(b))
Path(sys.argv[3]).write_text(json.dumps(out, indent=1))
print("COMPARE", json.dumps({k: v for k, v in out.items() if not isinstance(v, list)}), flush=True)
