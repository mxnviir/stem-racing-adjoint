"""Stage 2's loop without SimScale or the car builder: init from a stage-1 run, the base car and its
noise copy, ask a generation, build it (one car illegal, one build crashed), collect race times, tell
CMA, ask the next generation. Stubs stand in for layout_car.build / export_cfd and the evaluator."""
import json
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
import repo_paths  # noqa: E402,F401
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

import layout_genes as LG  # noqa: E402
import simscale_layout as SL  # noqa: E402
import simscale_shape as SS  # noqa: E402


class StubEvaluator:
    """Every submitted car comes back on the next collect, drag growing with the lattice's size."""
    def __init__(self):
        self.st = {"cases": {}, "keys": {}}
        self.pending = {}

    def capacity(self):
        return 100

    def submit(self, cases):
        for c in cases:
            self.st["cases"][c["id"]] = {"folder": c["folder"], "phase": "wait"}
            self.pending[c["id"]] = c["folder"]

    def collect(self):
        out = {}
        for cid, folder in list(self.pending.items()):
            rec = json.loads((Path(folder) / "layout_car.json").read_text())
            v = np.asarray((rec.get("lattice") or {}).get("values") or [0.0])
            out[cid] = {"ok": True, "D20_N": 0.40 + 0.01 * float((v ** 2).mean()), "L20_N": 0.0, "info": {}}
            self.st["cases"].pop(cid, None)
        self.pending = {}
        return out


def stub_build(x, out, timeout_s=0, lattice=None, support=None):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    v = (lattice or {}).get("values") or [0.0]
    if v[0] > 1.0:
        raise RuntimeError("builder crashed")                    # _build_one turns this into an illegal car
    d = LG.decode(x)
    rec = {"genes": list(map(float, x)), "layout": {k: d[k] for k in ("W", "rear", "halo_rear", "x_front", "d_halo")},
           "decoded": json.loads(json.dumps(d, default=float)), "lattice": lattice,
           "legal": not (v[0] < -1.0), "failed": [] if not (v[0] < -1.0) else ["T7.9.3_zone_clear"],
           "mass": {"race_mass_g": 69.35, "com_z_mm": 23.0, "com_x_car_mm": 140.0, "lead_g": 2.0},
           "cfd": {"one_piece": True, "watertight": True, "wrap_pitch_mm": 0.3}}
    (out / "layout_car.json").write_text(json.dumps(rec))
    return rec


def test_shape_loop(tmp_path, monkeypatch):
    lay = tmp_path / "layout"; lay.mkdir()
    x = LG.x_default().tolist()
    (lay / "designs.jsonl").write_text(json.dumps({"id": "L0003", "genes": x, "T": 0.7550}) + "\n")
    monkeypatch.setattr(SL.LC, "build", stub_build)
    monkeypatch.setattr(SL.LC, "export_cfd", lambda out, d, pitch_mm=None: {"cfd": {"one_piece": True, "watertight": True,
                                                                                  "wrap_pitch_mm": pitch_mm}})
    monkeypatch.setattr(SL, "ProcessPoolExecutor", _Serial)
    root = tmp_path / "shape"
    SS.init(root, lay, budget=16, popsize=8)
    c = SS.ShapeCampaign(root)
    ev = StubEvaluator()
    rng = np.random.default_rng(0)
    orig_ask = c.ask

    def ask_with_two_bad(n):                                     # one illegal car and one crashed build
        xs, info = orig_ask(n)
        xs = [np.asarray(v, float) for v in xs]
        xs[0][0], xs[1][0] = -1.5, 1.5
        return xs, info
    c.ask = ask_with_two_bad
    for _ in range(8):
        c.tick(ev)
        if c.st["g"] >= 2:
            break
    assert set(c.st["refs"]) == {"BASE24000", "BASEP25"}, c.st["refs"]
    assert all(v is not None for v in c.st["refs"].values()), c.st["refs"]
    assert c.st["g"] == 2, c.st                                  # two generations asked, built, timed and told
    assert c.es().countiter == 2
    rows = c.designs()
    assert any(r.get("legal") is False and "crashed" in (r.get("why") or "") for r in rows)
    assert any(r.get("legal") is False and r.get("failed") for r in rows)
    assert c.st["best"] is not None
    # CMA moves the lattice and the supports' shape genes together; every car's row carries both
    built = [r for r in rows if r.get("v") is not None]
    assert built and all(len(r["v"]) == c.dim() for r in built)
    assert c.dim() == 24 + len(SL.LG.SHAPE_GENES)


class _Serial:
    """ProcessPoolExecutor stand-in: the stubs are patched in this process only."""
    def __init__(self, n):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def map(self, f, jobs):
        return [f(j) for j in jobs]
