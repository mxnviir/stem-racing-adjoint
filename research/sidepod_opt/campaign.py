"""The campaign: stages, budgets, state, and one log of every car ever built.

    python campaign.py init   <dir> <config.json>     set up (voxelises the STEP once)
    python campaign.py run    <dir>                   loop ticks until done (local evaluators)
    python campaign.py tick   <dir>                   one step: collect -> tell -> ask -> build -> submit
                                                      (cron this for Actions / SimScale)
    python campaign.py status <dir>
    python campaign.py report <dir>                   table, convergence plot, renders, STLs of the best
    python campaign.py make-refs <dir> <res>          frozen states A and B of the ORIGINAL car (OpenFOAM)
    python campaign.py gate-adjoint <dir> <res>       adjoint vs finite differences on random directions

Stage types (config "stages", run in order):
  search  methods x starts x seeds, each with its own run budget, at one fidelity / evaluator;
          optional "prior_from": [stage names] feeds cheaper results into BO/SAIL (multi-fidelity)
  pick    re-evaluate chosen designs of earlier stages at a higher fidelity
          ("how": "best" = lowest race time, distinct; "spread" = across the whole range, for calibration)
  gate    rank agreement between two fidelities on the designs both evaluated (Spearman >= min);
          a failed gate STOPS the campaign: the cheap fidelity's verdicts do not count

Every car: field -> finish -> mill -> check (one piece, nothing outside the region changed, rule
zones clear, cargo inside, track clearance) -> weigh. A car that fails a check or needs more lead
than the container holds is illegal: logged, told to the method as None, never sent to CFD.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import design as DS  # noqa: E402
import evaluators as EV  # noqa: E402
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
        key = json.dumps(spec, sort_keys=True)
        if key not in self._ev:
            k = spec["kind"]
            if k == "openfoam":
                self._ev[key] = EV.OpenFOAMEvaluator(refs=spec.get("refs"), n_subdomains=spec.get("np", 2),
                                                     iters=spec.get("iters", 1000), mode=spec.get("mode", "auto"))
            elif k == "actions":
                self._ev[key] = EV.ActionsEvaluator(self.root / "jobs", spec.get("repos", []), spec.get("ref", "main"),
                                                    spec.get("res", "medium"), spec.get("dry_run", False), spec.get("per_job", 1),
                                                    release=spec.get("release", "sidepod-jobs"), refs_tag=spec.get("refs_tag", ""),
                                                    mode=spec.get("mode", "auto"), iters=spec.get("iters", 1000))
            elif k == "simscale":
                self._ev[key] = EV.SimScaleEvaluator(spec["project_id"], spec["template_sim_id"], spec["mesh_template_id"],
                                                     self.root / "simscale_inflight.json",
                                                     speed_mps=spec.get("speed_mps", 20.0), symmetric_half=spec.get("half", True),
                                                     max_cost=spec.get("max_cost"), bodies=spec.get("bodies"))
            elif k == "simscale_step":
                import simscale_step_eval as SSE
                self._ev[key] = SSE.SimScaleStepEvaluator(self.car, self.root / "simscale_state.json",
                                                          runs_per_key=spec.get("runs_per_key", 10),   # null in the config = no limit
                                                          speed_mps=spec.get("speed_mps", 20.0), max_cost=spec.get("max_cost"),
                                                          fineness=spec.get("fineness", 6), box_mm=spec.get("box_mm", 1.5), sizing=spec.get("sizing"),
                                                          iters=spec.get("iters", 1000), project_id=spec.get("project_id"))
            elif k == "adjoint":
                self._ev[key] = EV.AdjointEvaluator(self.car, self.rm, spec.get("backend", "esi"), spec.get("res", "medium"))
            else:
                raise ValueError(k)
        return self._ev[key]

    def representation(self, method: str, o: dict):
        if method == "neat":
            return DS.CPPNInputs(self.car)
        if method in ("spsa", "adjoint") and o.get("rep", "levelset") == "levelset":
            return DS.LevelSet(self.car, o.get("levelset_mm", 2.0))
        return DS.Lattice(self.car, tuple(o.get("lattice", (10, 4, 5))), o.get("amp_mm", 12.0), o.get("seed", "blend"))

    def field(self, rep, x):
        if isinstance(rep, DS.CPPNInputs):
            gid, g = x
            return DS.cppn_field(g, self._neat_cfg, rep)
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
        done = {"search": self._tick_search, "pick": self._tick_pick, "gate": self._tick_gate}[kind](s)
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
            if mname == "sail":
                m.descriptor = lambda x, rep=m.rep: _descriptor(self.car, rep.field(x))
            return m
        rep = self.representation(mname, o)
        rng = np.random.default_rng(seed)
        kw = {k: v for k, v in o.items() if k not in ("starts", "seeds", "budget", "lattice", "amp_mm", "seed", "rep", "levelset_mm", "method")}
        if mname == "neat":
            self._neat_cfg = self._neat_config()
            m = MT.make("neat", rep, start, rng, cfg_path=self.root / "neat.cfg", seeds=_neat_seeds(start), **kw)
        elif mname == "sail":
            m = MT.make("sail", rep, start, rng, descriptor=lambda x, rep=rep: _descriptor(self.car, rep.field(x)), **kw)
        else:
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
            if mname == "neat":
                m.cfg = self._neat_cfg = getattr(self, "_neat_cfg", None) or self._neat_config()
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
                           neat_gid=(int(x[0]) if isinstance(x, tuple) else None),
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
                if x is None and mname == "neat":                    # a NEAT genome, by id (process restarted)
                    gid = next((d.get("neat_gid") for d in self.designs() if d["id"] == cid), None)
                    x = (gid, None) if gid is not None else None
                if x is None:
                    continue
                info = {}
                if "grad_vertices_m" in r and T is not None:
                    body = np.unpackbits(np.load(self.root / "cars" / cid / "body.npy"))[: self.car.body0.size].reshape(self.car.body0.shape).astype(bool)
                    mass = json.loads((self.root / "cars" / cid / "mass.json").read_text())
                    info["grad_field"] = EV.field_gradient(self.car, body, mass, self.rm, r["D20_N"], r["L20_N"] or 0.0,
                                                           r["grad_vertices_m"], r["grad_dD20_half_dn"])
                xs.append(x); ys.append(T); infos.append(info)
            if xs:
                m.tell(xs, ys, infos)
                rs = self.state["runs"][run_id]
                good = [y for y in ys if y is not None]
                if good:
                    rs["best"] = min([rs["best"]] + good) if rs["best"] is not None else min(good)
                self._save_method(run_id, m)

    # pick ----------------------------------------------------------------
    def _tick_pick(self, s):
        ev = self.evaluator(s["evaluator"])
        key = f"pick:{s['name']}"
        if key not in self.state:
            src = [d for d in self.designs() if d.get("stage") in s["from"] and d.get("T") is not None]
            src.sort(key=lambda d: d["T"])
            n = s.get("n", 10)
            if s.get("how", "best") == "best":
                chosen, seen = [], set()
                for d in src:
                    k = round(d["mass"]["foam_g"], 2), round(d["T"], 5)
                    if k not in seen:
                        seen.add(k); chosen.append(d)
                    if len(chosen) == n:
                        break
            else:
                idx = np.unique(np.linspace(0, len(src) - 1, n).round().astype(int))
                chosen = [src[i] for i in idx]
            cases = []
            for d in chosen:
                cid = f"c{self.state['n']:05d}"; self.state["n"] += 1
                folder = self.root / "cars" / d["id"]
                self.log(dict(id=cid, stage=s["name"], run=None, method=d["method"], parent=d["id"], x_file=d.get("x_file"),
                              fidelity=s.get("fidelity"), mass=d["mass"], check=d.get("check"), legal=True))
                cases.append({"id": cid, "folder": str(folder), "fidelity": s.get("fidelity"),
                              "body": np.unpackbits(np.load(folder / "body.npy"))[: self.car.body0.size].reshape(self.car.body0.shape).astype(bool)})
                self.state["inflight"][cid] = {"run": None, "stage": s["name"]}
            self.state[key] = [c["id"] for c in cases]
            ev.submit(cases)
        self._collect(ev, s)
        return not any(v["stage"] == s["name"] for v in self.state["inflight"].values())

    # gate ----------------------------------------------------------------
    def _tick_gate(self, s):
        from scipy.stats import spearmanr
        ds = self.designs()
        hi = {d["parent"]: d["T"] for d in ds if d.get("stage") == s["high"] and d.get("T") is not None and d.get("parent")}
        lo = {d["id"]: d["T"] for d in ds if d["id"] in hi and d.get("T") is not None}
        common = sorted(set(hi) & set(lo))
        rho = float(spearmanr([lo[c] for c in common], [hi[c] for c in common]).correlation) if len(common) >= 5 else float("nan")
        ok = rho >= s.get("min_spearman", 0.7)
        self.state.setdefault("gates", {})[s["name"]] = {"spearman": rho, "n": len(common), "passed": bool(ok)}
        if not ok:
            self.state["stopped"] = f"gate {s['name']} failed: Spearman {rho:.2f} on {len(common)} cars (need {s.get('min_spearman', 0.7)})"
        return True

    # ------------------------------------------------------------------ helpers
    def _neat_config(self):
        p = self.root / "neat.cfg"
        if not p.exists():
            p.write_text(NEAT_CFG)
        import neat
        return neat.Config(neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet, neat.DefaultStagnation, str(p))


def _descriptor(car, f):
    """Cheap SAIL descriptors of the FINISHED design (symmetric, cargo in, forced air out; not
    milled, which is too slow for MAP-Elites' thousands of calls): foam volume in the region (cm3)
    and the pod's mean height (mm)."""
    pod = car.finish(f) & car.region
    if not pod.any():
        return (0.0, 0.0)
    return (pod.sum() * car.h ** 3 / 1e3, float(car.Z[pod].mean()))


def _neat_seeds(start):
    """Hand-built starting networks. Inputs: 0 x, 1 |y|, 2 z, 3 d_cargo/20, 4 sdf_original/10, 5 sdf_lean/10."""
    def seed(bias, w):
        def apply(g, cfg):
            gc = cfg.genome_config; out = gc.output_keys[0]
            for k in list(g.connections):
                del g.connections[k]
            g.nodes[out].bias, g.nodes[out].activation, g.nodes[out].response = bias, "tanh", 1.0
            for i, wt in w.items():
                key = (gc.input_keys[i], out)
                try:
                    c = g.create_connection(gc, *key, gc.innovation_tracker.get_innovation_number(*key, "add_connection"))
                except AttributeError:                       # older neat-python: no innovation numbers
                    c = g.create_connection(gc, *key)
                c.weight, c.enabled = wt, True
                g.connections[key] = c
        return apply
    base = [seed(0.0, {4: 2.0}), seed(0.0, {5: 2.0}), seed(-0.2, {5: 1.0, 2: -0.8, 1: 0.4}),
            seed(0.0, {4: 1.2, 0: -0.6}), seed(0.0, {4: 1.0, 2: -0.8}), seed(0.1, {5: 1.0, 4: 0.6})]
    return base if start == "original" else base[1:] + base[:1]


NEAT_CFG = """
[NEAT]
fitness_criterion = max
fitness_threshold = 1e9
pop_size = 12
reset_on_extinction = True
no_fitness_termination = True
[DefaultGenome]
num_inputs = 6
num_hidden = 0
num_outputs = 1
initial_connection = full_direct
feed_forward = True
activation_default = tanh
activation_mutate_rate = 0.15
activation_options = sigmoid tanh sin gauss abs identity
aggregation_default = sum
aggregation_mutate_rate = 0.0
aggregation_options = sum
bias_init_mean = 0.0
bias_init_stdev = 0.5
bias_max_value = 5.0
bias_min_value = -5.0
bias_mutate_power = 0.3
bias_mutate_rate = 0.7
bias_replace_rate = 0.02
response_init_mean = 1.0
response_init_stdev = 0.0
response_max_value = 5.0
response_min_value = -5.0
response_mutate_power = 0.0
response_mutate_rate = 0.0
response_replace_rate = 0.0
weight_init_mean = 0.0
weight_init_stdev = 0.5
weight_max_value = 6
weight_min_value = -6
weight_mutate_power = 0.3
weight_mutate_rate = 0.8
weight_replace_rate = 0.02
enabled_default = True
enabled_mutate_rate = 0.02
node_add_prob = 0.2
node_delete_prob = 0.05
conn_add_prob = 0.3
conn_delete_prob = 0.1
compatibility_disjoint_coefficient = 1.0
compatibility_weight_coefficient = 0.5
single_structural_mutation = False
structural_mutation_surer = default
[DefaultSpeciesSet]
compatibility_threshold = 2.0
[DefaultStagnation]
species_fitness_func = max
max_stagnation = 8
species_elitism = 2
[DefaultReproduction]
elitism = 2
survival_threshold = 0.3
min_species_size = 2
"""


# ---------------------------------------------------------------------- CLI extras
def make_refs(c: Campaign, res: str, iters=3000, extra=1000):
    """Frozen states of THIS car's original (needs OpenFOAM): A after `iters`, B `extra` later,
    zipped as refcase-A.zip / refcase-B.zip for a release the workflow downloads."""
    import shutil
    sys.path.insert(0, str(EV.P2))
    from cfd_wrapper import run_half_car_cfd
    import stopwatch as SW
    folder = c.car.export_car_folder(c.car.body_mesh, c.root / "cars" / "original", "original")
    body = SW.body_stl(folder / "car_half.stl", folder / "_body_half.stl")
    out = {}
    prev = None
    for s, n in (("A", iters), ("B", extra)):
        kw = dict(SW.SEARCH, resolution=res, max_iterations=n, keep_run_dir=True)
        if prev:
            kw.update(warm_from=prev)
        half, health = run_half_car_cfd(str(body), n_subdomains=2, extra_surfaces=SW.extra_surfaces(folder), **kw)
        run = Path(health.run_dir) if getattr(health, "run_dir", None) else sorted((EV.P2 / "cfd_case_template/runs").glob("*"))[-1]
        dst = c.root / "refs" / s
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(run, dst, ignore=shutil.ignore_patterns("processor*", "logs"))
        shutil.make_archive(str(c.root / "refs" / f"refcase-{s}"), "zip", dst)
        out[s] = str(dst); prev = str(dst)
        print(s, "D20", half.to_full_car().D20, "converged", health.converged, flush=True)
    (c.root / "refs" / "refs.json").write_text(json.dumps(out, indent=1))


def gate_adjoint(c: Campaign, res="medium", k=10, eps_mm=1.0, min_r=0.9):
    """The adjoint is used only if it predicts finite differences: k random smooth directions on the
    level-set field around the original, each measured at +-eps (2k primal runs) and predicted by
    one adjoint gradient. Passes at r >= min_r and >= 90 % signs (Part 3's known-answer marks)."""
    rep = DS.LevelSet(c.car)
    x0 = rep.x0("original")
    ad = EV.AdjointEvaluator(c.car, c.rm, res=res)
    b0, _, f0 = c.build_and_export(rep, x0, "gate_0")
    ad.submit([{"id": "g0", "folder": str(f0)}]); r0 = ad.collect()["g0"]
    g = EV.field_gradient(c.car, b0["voxels"], b0["mass"], c.rm, r0["D20_N"], r0["L20_N"], r0["grad_vertices_m"], r0["grad_dD20_half_dn"])
    gx = rep.field_grad_to_x(g)
    of = EV.OpenFOAMEvaluator(n_subdomains=2)
    rng = np.random.default_rng(0)
    pred, meas = [], []
    from scipy import ndimage
    for i in range(k):
        d = np.sign(ndimage.gaussian_filter(rng.normal(0, 1, rep.cshape), 2.0)).ravel()
        ts = []
        for sgn in (1, -1):
            b, ok, f = c.build_and_export(rep, x0 + sgn * eps_mm * d, f"gate_{i}_{sgn}")
            of.submit([{"id": "x", "folder": str(f)}]); r = of.collect()["x"]
            ts.append(c.rm(r["D20_N"], r["L20_N"], b["mass"])[0])
        meas.append((ts[0] - ts[1]) / (2 * eps_mm)); pred.append(float(gx @ d))
    r = float(np.corrcoef(pred, meas)[0, 1]); signs = float(np.mean(np.sign(pred) == np.sign(meas)))
    out = {"r": r, "signs": signs, "passed": bool(r >= min_r and signs >= 0.9), "pred": pred, "meas": meas}
    (c.root / "gate_adjoint.json").write_text(json.dumps(out, indent=1))
    print(out)
    return out


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
               "gates": c.state.get("gates"), "stopped": c.state.get("stopped")}
        s = c.stage()
        if s and s.get("evaluator", {}).get("kind") == "simscale_step":
            out["simscale"] = c.evaluator(s["evaluator"]).status()
        print(json.dumps(out, indent=1, default=float))
    elif cmd == "report":
        import report
        report.report(c)
    elif cmd == "make-refs":
        make_refs(c, sys.argv[3])
    elif cmd == "gate-adjoint":
        gate_adjoint(c, sys.argv[3])


if __name__ == "__main__":
    main()
