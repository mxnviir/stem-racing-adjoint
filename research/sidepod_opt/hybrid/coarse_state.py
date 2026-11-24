"""A coarse steady (upwind) state of one car folder, fresh mesh, kept for DAFoam (hybrid/HYBRID_TEST.md).
    GATE_RES=coarse CFD_DIV_U="bounded Gauss upwind" python hybrid/coarse_state.py <car folder> <keep dir> <iters> <out.json>"""
import json, os, shutil, sys
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / "part2-simulation"))
import gate  # noqa: E402

folder, keep, iters, out = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), Path(sys.argv[4])
half, health, secs = gate.solve(folder, 4, iters, keep=True)
run = gate.latest_run_of(os.getpid())
if keep.exists():
    shutil.rmtree(keep)
shutil.copytree(run, keep, ignore=shutil.ignore_patterns("processor*"))
d = gate.rec(half, health, secs, run_dir_kept=str(keep), folder=str(folder), iters=iters)
out.write_text(json.dumps(d, indent=1, default=float))
print("COARSE_STATE", json.dumps(d, default=float)[:500], flush=True)
