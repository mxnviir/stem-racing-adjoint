"""Round 2 directions (hybrid/HYBRID_TEST.md H2): the steepest descent inside the span of MEASURED moves.
Each measured move i is a field w_i on the base STL vertices with a measured drag change dF_i (vs step_zero). Under the
linear regime, drag change of sum_i c_i w_i = sum_i c_i dF_i; with the area-weighted Gram matrix M_ij = <w_i, w_j>_A
the steepest descent at unit norm is c = -(M + ridge)^-1 dF. Each arm uses a subset of the measured moves.
    python hybrid/combine.py <measured.json> <outdir>
measured.json: {name: {"field": ..., "amp_mm": ..., "dF_mN": ...}}. Writes <outdir>/<arm>.npy (the per-vertex field
before mean removal / p95 / clip, consumed by make_step's "vec:" field) and <outdir>/combine.json."""
import json, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "esi"))
import predict_candidates as PC   # noqa: E402

RIDGE = 1e-3
meas = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2]).resolve(); out.mkdir(parents=True, exist_ok=True)
W = {k: PC.move(m["field"], m["amp_mm"]) for k, m in meas.items()}
A = PC.A


def is_rnd(k): return meas[k]["field"].startswith("rnd")
def is_daf(k): return meas[k]["field"] in ("daf", "daf_opp")
def is_esi(k): return meas[k]["field"] in ("esi_frozen", "esi_sst", "opp_frozen")


ARMS = {"es": lambda k: is_rnd(k), "guided": lambda k: is_rnd(k) or is_daf(k) or is_esi(k),
        "guided_daf": lambda k: is_rnd(k) or is_daf(k), "guided_esi": lambda k: is_rnd(k) or is_esi(k)}
info = {}
for arm, sel in ARMS.items():
    ks = [k for k in meas if sel(k)]
    X = np.array([W[k] for k in ks])                                   # n x V
    M = (X * A) @ X.T
    dF = np.array([meas[k]["dF_mN"] for k in ks])
    c = -np.linalg.solve(M + RIDGE * np.trace(M) / len(ks) * np.eye(len(ks)), dF)
    f = c @ X
    np.save(out / f"{arm}.npy", f)
    # linear-model value of the final (normalised, clipped, 0.125 mm) step, and its RMS: on record before the solve
    w = PC.move(f"vec:{(out / f'{arm}.npy').relative_to(HERE)}", 0.125)
    lin = float(np.linalg.lstsq(X.T * np.sqrt(A)[:, None], w * np.sqrt(A), rcond=None)[0] @ dF)
    info[arm] = {"n_dirs": len(ks), "dirs": ks, "coef": c.tolist(), "linear_model_mN_at_0p125": lin,
                 "share_in_span": float(np.linalg.norm(X.T @ np.linalg.lstsq(X.T * np.sqrt(A)[:, None], w * np.sqrt(A), rcond=None)[0] * np.sqrt(A))
                                        / np.linalg.norm(w * np.sqrt(A))),
                 "predicted_mN": PC.predict(w)}
    print(arm, json.dumps({k: v for k, v in info[arm].items() if k not in ("coef", "dirs")}), flush=True)
(out / "combine.json").write_text(json.dumps(info, indent=1))
