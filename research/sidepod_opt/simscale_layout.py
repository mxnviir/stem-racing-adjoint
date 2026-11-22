"""The layout search on SimScale: CMA-ES over layout_genes (wheelbase, rear axle -> rear face,
halo -> rear face, the body loft, sidepods, nose cone and both wings), each car built whole by
layout_car.py and timed by the race model with ITS OWN wheelbase, thrust point, mass and COM.

A process of its own, in its own folder (runs/simscale_layout), next to the sidepod campaign:
the same keys (key state seeded from the sidepod run, so a retired key stays retired), the same
SimScale setup (half car, 20 m/s, k-omega SST, 1000 iterations, manual mesh max 30 / min 0.8 mm,
road 0.15 mm under the wheels), but the whole car is faceted (CAR_FACES triangles) because every
part of it is generated -- the team-layout reference goes through the same route, so the
comparison is like for like.

    python simscale_layout.py init runs/simscale_layout --budget 110
    python simscale_layout.py run  runs/simscale_layout            # ticks every 60 s
    python simscale_layout.py status runs/simscale_layout
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import layout_genes as LG  # noqa: E402
import layout_car as LC  # noqa: E402
import simscale_step_eval as SE  # noqa: E402

CAR_FACES = (12000, 15000, 9000, 18000, 10500, 21000)     # whole-car triangle counts tried in turn
SE.FACES = CAR_FACES                                         # the evaluator's retry ladder (this process only)
BOX_M = ((-0.01, 0.0, -0.001), (0.30, 0.06, 0.07))           # car <= 264 mm with the cartridge; rear wing <= 65 mm
BUILD_WORKERS = 2                                            # one Parts 1-5 build peaks at ~5.5 GB


class LayoutEvaluator(SE.SimScaleStepEvaluator):
    """The sidepod evaluator with the whole generated car as the geometry and per-car wheel centres."""

    def _build_step(self, cid, faces):
        import trimesh
        import simscale_step_domain as SD
        folder = Path(self.st["cases"][cid]["folder"])
        full = trimesh.load(folder / "body_full.stl", force="mesh")
        try:
            import fast_simplification as fs
            v, f = fs.simplify(full.vertices.astype(np.float64), full.faces, target_reduction=max(0.0, 1 - faces / len(full.faces)))
            dec = trimesh.Trimesh(v, f, process=True)
        except Exception as e:                                       # noqa: BLE001
            raise SE.GeometryError(f"decimation: {e!r}") from e
        if not dec.is_watertight or dec.volume <= 0:
            raise SE.GeometryError(f"decimated car not closed ({len(dec.faces)} faces)")
        if abs(dec.volume / full.volume - 1) > 0.01:
            raise SE.GeometryError(f"decimation changed the volume by {dec.volume / full.volume - 1:+.2%}")
        out = folder / f"domain_{faces}.step"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            dec.export(td / "body_full.stl")
            for w in ("wheelF", "wheelR"):
                (td / f"{w}.stl").write_bytes((folder / f"{w}.stl").read_bytes())
            try:
                rep = SD.build(td, out)
            except Exception as e:                                   # noqa: BLE001
                raise SE.GeometryError(f"air volume build: {e!r}") from e
        if not 0.97 < rep["removed_share"] < 1.03:
            raise SE.GeometryError(f"air volume: removed {rep['removed_share']:.3f} of the car's volume")
        return out

    def _advance(self, cid):
        c = self.st["cases"][cid]
        self._wheels = {k: tuple(v) for k, v in json.loads((Path(c["folder"]) / "wheels.json").read_text()).items()}
        return super()._advance(cid)


def race_model(d):
    """objective.RaceModel for this car's own layout. RaceModel works in the team STEP's mirrored
    frame (x decreasing to the rear); x -> -x maps the car frame (x from the nose tip) onto it."""
    from objective import RaceModel
    rear_face = d["x_front"] + d["W"] + d["rear"]
    spec = SimpleNamespace(x_nose_mm=0.0, x_front_axle=-d["x_front"], x_rear_axle=-(d["x_front"] + d["W"]),
                           tail_x=-rear_face, cartridge_out_mm=LC.CARTRIDGE_OUT_MM, thrust_z=LC.CHAMBER_Z_MM)
    return RaceModel(spec)


def race_time(rec, D20, L20):
    m = rec["mass"]
    T, _ = race_model(rec["decoded"])(D20, L20, {"race_mass_g": m["race_mass_g"], "com_z_mm": m["com_z_mm"],
                                                  "com_x_car_mm": m["com_x_car_mm"]})
    return T


def _build_one(args):
    x, folder = args
    try:
        return LC.build(np.asarray(x), Path(folder))
    except Exception as e:                                           # noqa: BLE001
        return {"legal": False, "why": f"builder crashed: {e!r}"[:500], "genes": list(map(float, x))}


class Campaign:
    def __init__(self, root):
        self.root = Path(root)
        self.cfg = json.loads((self.root / "config.json").read_text())
        self.st = json.loads((self.root / "state.json").read_text())

    def save(self):
        p = self.root / "state.json"; t = p.with_suffix(".tmp")
        t.write_text(json.dumps(self.st, indent=1)); t.replace(p)

    def log(self, row):
        with open(self.root / "designs.jsonl", "a") as f:
            f.write(json.dumps(row, default=float) + "\n")

    def es(self):
        p = self.root / "cma.pkl"
        if p.exists():
            return pickle.loads(p.read_bytes())
        import cma
        c = self.cfg["cma"]
        es = cma.CMAEvolutionStrategy(LG.x_default(), c["sigma"], {"bounds": [0, 1], "popsize": c["popsize"],
                                                                  "seed": c.get("seed", 1), "verbose": -9})
        self.save_es(es)
        return es

    def save_es(self, es):
        p = self.root / "cma.pkl"; t = p.with_suffix(".tmp")
        t.write_bytes(pickle.dumps(es)); t.replace(p)

    def evaluator(self):
        import simscale_template as ST
        ST.BOX_M = BOX_M
        e = self.cfg["evaluator"]
        return LayoutEvaluator(None, self.root / "simscale_state.json", runs_per_key=None, speed_mps=20.0,
                               fineness=6, box_mm=e.get("box_mm", 1.5), iters=e.get("iters", 1000),
                               sizing=e.get("sizing"), max_cost=e.get("max_cost"))

    def new_id(self):
        cid = f"L{self.st['n']:04d}"; self.st["n"] += 1
        return cid

    def tick(self, ev):
        # 1) the reference (team layout, Part 1 default body), once
        if "ref" not in self.st:
            cid = self.new_id(); self.st["ref"] = cid
            self.st["pending_build"] = {cid: {"x": LG.x_default().tolist(), "kind": "ref"}}
            self.save()
        # 2) a new generation when nothing of the last one is out
        es = self.es()
        if not self.st["gen"] and not self.st.get("pending_build") and self.st["used"] < self.cfg["budget"] and ev.capacity() > 0:
            xs = es.ask()
            gen = {}
            for x in xs:
                cid = self.new_id()
                gen[cid] = {"x": np.asarray(x).tolist(), "kind": "cma"}
            self.st["pending_build"] = gen
            self.st["gen_ids"] = list(gen)
            self.save()
        # 3) build what is pending (in parallel), submit the legal ones
        pb = self.st.get("pending_build") or {}
        if pb:
            jobs = [(v["x"], str(self.root / "cars" / cid)) for cid, v in pb.items()]
            with ProcessPoolExecutor(BUILD_WORKERS) as pool:
                recs = list(pool.map(_build_one, jobs))
            cases = []
            for (cid, v), rec in zip(pb.items(), recs):
                row = {"id": cid, "kind": v["kind"], "gen": self.st["g"], "legal": rec.get("legal"),
                       "layout": rec.get("layout"), "failed": rec.get("failed"), "why": rec.get("why"),
                       "mass": rec.get("mass"), "build_s": rec.get("build_s"), "cfd_faces": rec.get("cfd_faces")}
                self.log(row)
                if rec.get("legal"):
                    cases.append({"id": cid, "folder": str(self.root / "cars" / cid)})
                    self.st["inflight"][cid] = v
                    if v["kind"] == "cma":
                        self.st["used"] += 1
                elif v["kind"] == "cma":
                    self.st["gen"][cid] = None                      # illegal: told as the worst
            if cases:
                ev.submit(cases)
            self.st["pending_build"] = {}
            self.save()
        # 4) results
        res = ev.collect()
        for cid, r in res.items():
            v = self.st["inflight"].pop(cid, None)
            if v is None:
                continue
            rec = json.loads((self.root / "cars" / cid / "layout_car.json").read_text())
            T = None
            if r.get("ok") and r.get("D20_N") is not None:
                T = race_time(rec, r["D20_N"], r["L20_N"] or 0.0)
            self.log({"id": cid, "kind": v["kind"], "D20_N": r.get("D20_N"), "L20_N": r.get("L20_N"), "T": T,
                      "layout": rec.get("layout"), "mass": rec.get("mass"), "eval": r.get("info")})
            if v["kind"] == "cma":
                self.st["gen"][cid] = T
            else:
                self.st["ref_T"] = T
            if T is not None and v["kind"] == "cma" and (self.st["best"] is None or T < self.st["best"][1]):
                self.st["best"] = [cid, T]
        # 5) tell CMA when the whole generation is back
        ids = self.st.get("gen_ids") or []
        if ids and all(i in self.st["gen"] for i in ids) and not any(i in self.st["inflight"] for i in ids):
            xs, ys = [], []
            for i in ids:
                rec = json.loads((self.root / "cars" / i / "layout_car.json").read_text()) if (self.root / "cars" / i / "layout_car.json").exists() else None
                x = np.array(rec["genes"]) if rec else None
                if x is None:
                    continue
                y = self.st["gen"][i]
                xs.append(x); ys.append(y)
            good = [y for y in ys if y is not None]
            worst = (max(good) if good else 1.0) + 0.05
            es.tell(xs, [y if y is not None else worst for y in ys])
            self.save_es(es)
            self.st["g"] += 1; self.st["gen"] = {}; self.st["gen_ids"] = []
        self.save()
        return res


def init(root, budget, popsize=8, sigma=0.15, seed_keys_from="runs/simscale/simscale_state.json"):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    (root / "config.json").write_text(json.dumps({
        "_comment": "Layout search (simscale_layout.py): CMA over layout_genes in [0,1]; genes 0-2 are the layout "
                    "(wheelbase, rear axle -> rear face, halo -> rear face), decoded so every vector is a legal layout.",
        "budget": budget, "cma": {"popsize": popsize, "sigma": sigma, "seed": 1},
        "evaluator": {"iters": 1000, "box_mm": 1.5, "max_cost": 80.0, "sizing": {"max_mm": 30, "min_mm": 0.8}},
        "rules": "no supports, no tether guides (added later); no virtual cargo; milled top and bottom, 3.175 mm ball, "
                 "3 mm walls (Part 1); sidepod top <= 27.175 mm; road 0.15 mm under the wheels; lead to 48.2 g"}, indent=1))
    (root / "state.json").write_text(json.dumps({"n": 0, "g": 0, "used": 0, "gen": {}, "gen_ids": [], "inflight": {},
                                                 "best": None, "pending_build": {}}, indent=1))
    src = HERE / seed_keys_from
    if src.exists() and not (root / "simscale_state.json").exists():
        k = json.loads(src.read_text())["keys"]
        keys = {fp: {"runs": v.get("runs", 0), "project": v.get("project"), "box": None, "retired": v.get("retired")}
                for fp, v in k.items()}
        (root / "simscale_state.json").write_text(json.dumps({"keys": keys, "cases": {}, "done": {}}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("init", "run", "tick", "status"))
    ap.add_argument("root")
    ap.add_argument("--budget", type=int, default=110)
    ap.add_argument("--popsize", type=int, default=8)
    ap.add_argument("--sigma", type=float, default=0.15)
    a = ap.parse_args()
    if a.cmd == "init":
        return init(a.root, a.budget, a.popsize, a.sigma)
    c = Campaign(a.root)
    if a.cmd == "status":
        ev = c.evaluator()
        print(json.dumps({"state": {k: v for k, v in c.st.items() if k != "pending_build"}, "eval": ev.status()}, indent=1, default=str))
        return
    ev = c.evaluator()
    while True:
        c.tick(ev)
        print(time.strftime("%H:%M:%S"), "gen", c.st["g"], "used", c.st["used"], "best", c.st["best"],
              "inflight", len(c.st["inflight"]), flush=True)
        if a.cmd == "tick" or (c.st["used"] >= c.cfg["budget"] and not c.st["inflight"] and not c.st["gen"]):
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
