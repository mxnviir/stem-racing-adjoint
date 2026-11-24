"""First-order predictions of candidate moves, written BEFORE their solves (HYBRID_TEST.md).
    python esi/predict_candidates.py <out.json> name:field:amp_mm [...]      (run from research/sidepod_opt)
Each move is rebuilt with make_step's own code (no files written). Predicted drag change (half car, mN) =
sum_i G_i . dX_i with dafoam/judge.py's mapping, for three gradients: coarse DAFoam (validated on coarse), coarse
ESI, wall-resolved ESI. Also the move's peak, RMS over the moved region and volume change."""
import json, sys
import numpy as np
import trimesh
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "esi")); sys.path.insert(0, str(HERE.parents[1] / "part2-simulation"))
import gate                       # noqa: E402
import make_step as MS            # noqa: E402
from dafoam.judge import displacement_at   # noqa: E402

GRADS = {"dafoam_coarse": HERE / "gate_results_coarse_up/dafoam/dafoam_sens.npz",
         "esi_coarse": HERE / "gate_results_coarse_up/esi/esi_sens_frozen.npz",
         "esi_resolved": HERE / "gate_results_resolved_up/esi/esi_sens_frozen.npz"}
base = trimesh.load(gate.ORIG / "car_half.stl")
V, N = base.vertices, base.vertex_normals
A = MS.vertex_area(base)
taper = (MS.smoothstep((V[:, 0] - MS.X0) / MS.TAPER) * MS.smoothstep((MS.X1 - V[:, 0]) / MS.TAPER)
         * MS.smoothstep((V[:, 1] - MS.Y0) / MS.TAPER))
G = {k: np.load(p) for k, p in GRADS.items()}


def move(field, amp_mm):
    if field == "zero" or float(amp_mm) == 0:
        return np.zeros(len(V))
    f = taper * MS.field_on_vertices(field, V, N, A)
    f -= taper * (A * f).sum() / (A * taper).sum()
    f /= np.percentile(np.abs(f[taper > 0.5]), 95)
    return np.clip(f, -1.0, 1.0) * float(amp_mm) * 1e-3


def predict(w):
    return {k: float((S["dD_dXs"] * displacement_at(S["Xs"], V, N * w[:, None])).sum()) * 1e3 for k, S in G.items()}


if __name__ == "__main__":
    out = {}
    moved = taper > 0.5
    for spec in sys.argv[2:]:
        name, field, amp = spec.split(":")
        w = move(field, amp)
        rms = float(np.sqrt((A[moved] * w[moved] ** 2).sum() / A[moved].sum()) * 1e3)
        out[name] = {"field": field, "amp_mm": float(amp), "peak_mm": float(np.abs(w).max() * 1e3), "rms_mm": rms,
                     "dV_mm3": float((A * w).sum() * 1e9), "predicted_mN": predict(w)}
        p = out[name]["predicted_mN"]
        print(f"{name:14s} {field:10s} amp {amp:6s} rms {rms:.4f} mm  dV {out[name]['dV_mm3']:+7.1f} mm3  "
              + "  ".join(f"{k} {v:+.3f}" for k, v in p.items()), flush=True)
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
