"""The sidepod search: CMA-ES on the team car's sidepods, timed on SimScale. State, budgets, and one
log of every car ever built.

    python search/sidepod/campaign.py init   <dir> <config.json>   set up (voxelises the team STEP once)
    python search/sidepod/campaign.py run    <dir>                 tick once a minute until every run's budget is used
    python search/sidepod/campaign.py tick   <dir>                 one step: collect -> tell -> ask -> build -> submit
    python search/sidepod/campaign.py status <dir>
    python search/sidepod/campaign.py report <dir>                 table, convergence plot, renders, STLs of the best

The config's "stages" are run in order; each is a search: methods x starts x seeds, each with its own
budget, every car timed by one evaluator (SimScale). A method entry may name the class it runs
("method": "cma") so two CMA runs with different lattices live side by side.

Every car: field -> finish -> mill -> check (one piece, nothing outside the region changed, rule
zones clear, track clearance, 3 mm walls) -> weigh (lead to 48.2 g). A car that fails a check or
needs more lead than the container holds is illegal: logged, told to CMA as the worst, never sent to CFD.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
import repo_paths  # noqa: E402,F401
import json
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import design as DS  # noqa: E402
import methods as MT  # noqa: E402
from geometry import Car, CarSpec  # noqa: E402
from objective import RaceModel  # noqa: E402


class Campaign:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.cfg = json.loads((self.root / "config.json").read_text())
        self.state_p = self.root / "state.json"
        self.state = json.loads(self.state_p.read_text()) if self.state_p.exists() else {"stage": 0, "runs": {}, "inflight": {}, "n": 0, "log": []}
        self.car = Car(CarSpec(**self.cfg.get("car", {})), h=self.cfg.get("h_mm", 1.0))
        self.rm = RaceModel(self.car.s)
        self.db_p = self.root / "designs.jsonl"
        self._ev = {}

    # ------------------------------------------------------------------ storage
    def save(self):
        self.state_p.write_text(json.dumps(self.state, indent=1, default=float))

    def designs(self):
        if not self.db_p.exists():
            return []
        rows = {}
        for line in self.db_p.read_text().splitlines():
            if line.strip():
                r = json.loads(line); rows[r["id"]] = {**rows.get(r["id"], {}), **r}
        return list(rows.values())

    def log(self, row):
        with open(self.db_p, "a") as f:
            f.write(json.dumps(row, default=float) + "\n")

    # ------------------------------------------------------------------ pieces
    def evaluator(self, spec: dict):
        """The SimScale evaluator (cfd/simscale_step_eval.py); one per evaluator spec."""
        key = json.dumps(spec, sort_keys=True)
        if key not in self._ev:
            if spec["kind"] != "simscale_step":
                raise ValueError(f"evaluator {spec['kind']!r}: only 'simscale_step' is kept (2026-11-22)")
            import simscale_step_eval as SSE
            self._ev[key] = SSE.SimScaleStepEvaluator(self.car, self.root / "simscale_state.json",
                                                      runs_per_key=spec.get("runs_per_key", 10),   # null in the config = no limit
                                                      speed_mps=spec.get("speed_mps", 20.0), max_cost=spec.get("max_cost"),
                                                      fineness=spec.get("fineness", 6), box_mm=spec.get("box_mm", 1.5), sizing=spec.get("sizing"),
                                                      iters=spec.get("iters", 1000), project_id=spec.get("project_id"))
        return self._ev[key]

    def representation(self, method: str, o: dict):
        return DS.Lattice(self.car, tuple(o.get("lattice", (10, 4, 5))), o.get("amp_mm", 12.0), o.get("seed", "blend"))

    def field(self, rep, x):
        return rep.field(x)

    def build_and_export(self, rep, x, cid):
        b = self.car.build(self.field(rep, x))
        legal = bool(b["check"]["ok"] and b["mass"] and b["mass"]["legal"])
        folder = self.root / "cars" / cid
        if legal:
            self.car.export_car_folder(b["mesh"], folder, cid)
            np.save(folder / "body.npy", np.packbits(b["voxels"]))
            (folder / "mass.json").write_text(json.dumps(b["mass"], default=float))
        return b, legal, folder

    # ------------------------------------------------------------------ stages
    def stage(self):
        st = self.cfg["stages"]
        return st[self.state["stage"]] if self.state["stage"] < len(st) else None

    def tick(self):
        """One step of the current stage; returns False when the campaign is finished or stopped."""
        s = self.stage()
        if s is None or self.state.get("stopped"):
            return False
        kind = s.get("type", "search")
        if kind != "search":
            raise ValueError(f"stage type {kind!r}: only 'search' is kept (2026-11-22)")
        done = self._tick_search(s)
        if done:
            self.state["log"].append({"t": time.time(), "stage": s["name"], "done": True})
            self.state["stage"] += 1
        self.save()
        return True

    # search ------------------------------------------------------------
    def _runs(self, s):
        out = []
        for mname, o in s["methods"].items():
            for start in o.get("starts", s.get("starts", ["original", "lean"])):
                for seed in o.get("seeds", s.get("seeds", [1])):
                    out.append((f"{s['name']}:{mname}:{start}:s{seed}", mname, start, seed, o))
        return out

    def _method(self, run_id, mname, start, seed, o, s):
        p = self.root / "runs" / (run_id.replace(":", "_") + ".pkl")
        if p.exists():
            with open(p, "rb") as f:
                m = pickle.load(f)
            m.rep = self.representation(mname, o)
            return m
        rep = self.representation(mname, o)
        rng = np.random.default_rng(seed)
        kw = {k: v for k, v in o.items() if k not in ("starts", "seeds", "budget", "lattice", "amp_mm", "seed", "rep", "levelset_mm", "method")}
        m = MT.make(o.get("method", mname), rep, start, rng, **kw)   # "method": run a method under another name (a second CMA with its own lattice)
        for pf in s.get("prior_from", []):
            xs, ys = [], []
            for d in self.designs():
                if d.get("stage") == pf and d.get("method") == mname and d.get("T") is not None and d.get("x_file"):
                    x = np.load(self.root / d["x_file"])
                    if x.shape == m.x0.shape:
                        xs.append(x); ys.append(d["T"])
            m.add_prior(xs, ys, 0.0)
        return m

    def _save_method(self, run_id, m):
        p = self.root / "runs" / (run_id.replace(":", "_") + ".pkl")
        p.parent.mkdir(parents=True, exist_ok=True)
        detached = {}
        for attr in ("cfg", "descriptor", "rep"):         # rep holds the car (exact CAD objects): rebuilt on load
            if hasattr(m, attr):
                detached[attr] = getattr(m, attr); setattr(m, attr, None)
        try:
            with open(p, "wb") as f:
                pickle.dump(m, f)
        finally:
            for k, v in detached.items():
                setattr(m, k, v)

    def _tick_search(self, s):
        ev = self.evaluator(s["evaluator"])
        ref_key = f"ref:{s['name']}"
        if ref_key not in self.state:                     # the original car, timed the same way, once per stage
            cid = f"c{self.state['n']:05d}"; self.state["n"] += 1
            b = self.car.build(self.car.sdf_original, original=True)       # the exact CAD
            folder = self.car.export_car_folder(b["mesh"], self.root / "cars" / cid, cid)
            np.save(folder / "body.npy", np.packbits(b["voxels"]))
            (folder / "mass.json").write_text(json.dumps(b["mass"], default=float))
            self.log(dict(id=cid, stage=s["name"], run=None, method="reference", fidelity=s.get("fidelity"),
                          check=b["check"], mass={k: (float(v) if not isinstance(v, bool) else v) for k, v in b["mass"].items()}, legal=True))
            self.state["inflight"][cid] = {"run": None, "stage": s["name"]}
            self.state[ref_key] = cid
            ev.submit([{"id": cid, "folder": str(folder), "body": b["voxels"], "fidelity": s.get("fidelity")}])
        self._collect(ev, s)
        all_done = True
        for run_id, mname, start, seed, o in self._runs(s):
            rs = self.state["runs"].setdefault(run_id, {"used": 0, "illegal": 0, "best": None})
            budget = o.get("budget", s.get("budget", 30))
            if rs["used"] >= budget or rs["illegal"] > 30 * budget:
                continue
            all_done = False
            if any(v["run"] == run_id for v in self.state["inflight"].values()):
                continue
            m = self._method(run_id, mname, start, seed, o, s)
            rep = m.rep
            n = min(o.get("batch", s.get("batch", 1)), budget - rs["used"])
            if hasattr(ev, "capacity"):                       # SimScale: only as many cars as the keys can still run
                n = min(n, ev.capacity())
                if n <= 0:
                    continue
            xs = m.ask(n)
            illegal_xs, cases = [], []
            for x in xs:
                cid = f"c{self.state['n']:05d}"; self.state["n"] += 1
                b, legal, folder = self.build_and_export(rep, x, cid)
                xfile = None
                if not isinstance(x, tuple):
                    xfile = f"x/{cid}.npy"; (self.root / "x").mkdir(exist_ok=True); np.save(self.root / xfile, x)
                row = dict(id=cid, stage=s["name"], run=run_id, method=mname, start=start, seed=seed, x_file=xfile,
                           fidelity=s.get("fidelity"), check=b["check"], mill=b["mill"],
                           mass={k: (float(v) if not isinstance(v, bool) else v) for k, v in (b["mass"] or {}).items()}, legal=legal)
                self.log(row)
                if not legal:
                    rs["illegal"] += 1; illegal_xs.append(x)
                    continue
                cases.append({"id": cid, "folder": str(folder), "body": b["voxels"], "fidelity": s.get("fidelity")})
                self.state["inflight"][cid] = {"run": run_id, "stage": s["name"]}
                self._pending_x = getattr(self, "_pending_x", {}); self._pending_x[cid] = x
                rs["used"] += 1
            if illegal_xs:
                m.tell(illegal_xs, [None] * len(illegal_xs))
            self._save_method(run_id, m)
            if cases:
                ev.submit(cases)
                self._collect(ev, s)
        return all_done and not self.state["inflight"]

    def _collect(self, ev, s):
        res = ev.collect()
        if not res:
            return
        by_run = {}
        for cid, r in res.items():
            inf = self.state["inflight"].pop(cid, None)
            if inf is None:
                continue
            d = next((d for d in self.designs() if d["id"] == cid), None)
            T = None
            if r.get("ok") and r.get("D20_N") is not None:
                T, sl = self.rm(r["D20_N"], r["L20_N"] or 0.0, d["mass"])
            self.log({"id": cid, "D20_N": r.get("D20_N"), "L20_N": r.get("L20_N"), "T": T, "eval": r.get("info"),
                      "evaluator": ev.name})
            if inf["run"]:
                by_run.setdefault(inf["run"], []).append((cid, T, r))
        for run_id, items in by_run.items():
            stage = next(st for st in self.cfg["stages"] if st["name"] == run_id.split(":")[0])
            _, mname, start, seed = run_id.split(":")
            o = stage["methods"][mname]
            m = self._method(run_id, mname, start, int(seed[1:]), o, stage)
            xs, ys, infos = [], [], []
            for cid, T, r in items:
                x = getattr(self, "_pending_x", {}).get(cid)
                if x is None:
                    xf = self.root / "x" / f"{cid}.npy"
                    x = np.load(xf) if xf.exists() else None
                if x is None:
                    continue
                xs.append(x); ys.append(T); infos.append({})
            if xs:
                m.tell(xs, ys, infos)
                rs = self.state["runs"][run_id]
                good = [y for y in ys if y is not None]
                if good:
                    rs["best"] = min([rs["best"]] + good) if rs["best"] is not None else min(good)
                self._save_method(run_id, m)

def main():
    cmd, root = sys.argv[1], Path(sys.argv[2])
    if cmd == "init":
        root.mkdir(parents=True, exist_ok=True)
        (root / "config.json").write_text(Path(sys.argv[3]).read_text())
        c = Campaign(root); c.save()
        b = c.car.build(c.car.sdf_original, original=True)
        c.car.export_car_folder(b["mesh"], root / "cars" / "original", "original")
        print("ready:", root, "| original milled foam", round(float(b["mass"]["foam_g"]), 2), "g, checks", b["check"])
        return
    c = Campaign(root)
    if cmd == "tick":
        c.tick()
    elif cmd == "run":
        while c.tick():
            time.sleep(float(os.environ.get("TICK_S", "60")))        # cloud evaluators: poll once a minute
            s = c.stage()
            print(time.strftime("%H:%M:%S"), "stage", s and s["name"], "runs",
                  {k: (v["used"], round(v["best"], 5) if v["best"] else None) for k, v in c.state["runs"].items()}, flush=True)
        print("finished" if not c.state.get("stopped") else c.state["stopped"])
    elif cmd == "status":
        out = {"stage": c.stage() and c.stage()["name"], "runs": c.state["runs"], "inflight": len(c.state["inflight"]),
               "stopped": c.state.get("stopped")}
        s = c.stage()
        if s and s.get("evaluator", {}).get("kind") == "simscale_step":
            out["simscale"] = c.evaluator(s["evaluator"]).status()
        print(json.dumps(out, indent=1, default=float))
    elif cmd == "report":
        import report
        report.report(c)


if __name__ == "__main__":
    main()
