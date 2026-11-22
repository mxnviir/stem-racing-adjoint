"""SimScale evaluator for the evolution, STEP air-volume route, several API keys.

Every design walks:   step -> import -> mesh -> run -> done
as a state machine kept in a JSON file, so the campaign never blocks (cron `campaign.py tick`).

  step    the air volume STEP (simscale_step_domain.build_design: the team's exact CAD outside the
          sidepod region, the designed pod as ~4500 triangles, exact wheels, road 0.15 mm under the
          wheels) is written and uploaded, the import started
  import  when it finishes: the faces are found by name, a simulation and mesh operation are made
          (simscale_template.create_case) and meshing starts. If SimScale refuses the import (it
          does for some files, without a reason), the pod is rebuilt with another triangle count
          (a few hundredths of a mm of difference) and imported again, up to len(FACES) times
  mesh    when it finishes: the mesh goes on the simulation, the setup is checked, the run starts
  run     when it finishes: drag and lift from the "Forces and moments" result (x2: half car)

API keys. SIMSCALE_API_KEYS holds one or more keys (comma, space or newline separated; or just
SIMSCALE_API_KEY). Each key is used for at most `runs_per_key` runs (free accounts run out), then the
next one. A key is never written anywhere: the state file only holds a short fingerprint of it
(sha256, 10 hex digits), its project id and its run count. Every account gets its own project
("sidepod evolution"), found or made through the API.

Errors. An error that is SimScale's or the network's (quota, 401/403 after a reset, 5xx, a timeout)
never marks a design bad: the case stays and is retried on the next tick; a quota error retires the
key and the case starts again on the next key. Only a geometry that cannot be meshed or solved
fails the design.
"""
import sys
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
import repo_paths  # noqa: E402,F401
import hashlib
import json
import os
import re
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FACES = (4500, 5200, 3900, 6000, 4200, 6800, 4800, 5600, 3600, 7500)   # pod triangle counts tried in turn
PROJECT_NAME = "sidepod evolution"
QUOTA_WORDS = ("quota", "credit", "insufficient", "limit exceeded", "core hour", "cpu hour", "not enough", "exceed",
               "subscription", "plan does not", "payment")


RUN_QUOTA_WORDS = ("quota", "credit", "core hour", "core-hour", "cpu hour", "subscription", "balance")   # a failed
# run's own messages: narrower than QUOTA_WORDS, so "max run time exceeded" or "not enough memory" never retire a key


class GeometryError(ValueError):
    """The design's air volume cannot be built or meshed: the design fails, not the pipeline."""


def keys_from_env():
    raw = os.environ.get("SIMSCALE_API_KEYS") or os.environ.get("SIMSCALE_API_KEY") or ""
    return [k for k in re.split(r"[\s,;]+", raw.strip()) if k]


def fingerprint(key):
    return hashlib.sha256(key.encode()).hexdigest()[:10]


class SimScaleStepEvaluator:
    name = "simscale"

    def __init__(self, car, state_path: Path, runs_per_key=10, speed_mps=20.0, max_cost=None,
                 fineness=6, box_mm=1.5, iters=1000, project_id=None, sdk=None, sizing=None):
        if sdk is None:
            import simscale_sdk as sdk
        self.sim, self.car = sdk, car
        self.state_path = Path(state_path)
        self.st = json.loads(self.state_path.read_text()) if self.state_path.exists() else {"keys": {}, "cases": {}}
        self.runs_per_key, self.speed, self.max_cost = runs_per_key, speed_mps, max_cost
        self.fineness, self.box_mm, self.iters, self.sizing = fineness, box_mm, iters, sizing
        self.fixed_project = project_id
        self._clients, self._wheels = {}, None
        # finished results stay in the state file until the campaign has had them for a whole tick, so a
        # process stopped mid-collect hands them over again on restart (the campaign skips ids it already has)
        self._done = self.st.setdefault("done", {})
        self._handed = set()
        self.keys = {fingerprint(k): k for k in keys_from_env()}
        for fp in self.keys:
            self.st["keys"].setdefault(fp, {"runs": 0, "project": None, "box": None, "retired": None})

    # ------------------------------------------------------------------ keys and accounts
    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.st, indent=1, default=float))

    def _api(self, fp):
        if fp not in self._clients:
            s = self.sim
            cfg = s.Configuration()
            cfg.host = os.environ.get("SIMSCALE_API_URL", "https://api.simscale.com") + "/v0"
            cfg.api_key = {"X-API-KEY": self.keys[fp]}
            proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")   # urllib3 ignores proxy env vars
            if proxy:
                cfg.proxy = proxy
            ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
            if ca:
                cfg.ssl_ca_cert = ca
            api = s.ApiClient(cfg)
            api.rest_client.pool_manager.connection_pool_kw["timeout"] = 120
            self._clients[fp] = api
        return self._clients[fp]

    def _account(self, fp):
        """(api, project_id, box_primitive_id) for a key; the project and box are made once."""
        import simscale_template as ST
        k, api = self.st["keys"][fp], self._api(fp)
        if not k["project"]:
            if self.fixed_project and len(self.keys) == 1:
                k["project"] = str(self.fixed_project)
            else:
                p_api = self.sim.ProjectsApi(api)
                found = None
                for p in (p_api.get_projects(limit=100, page=1).embedded or []):
                    if p.name == PROJECT_NAME:
                        found = p.project_id
                if not found:
                    found = p_api.create_project(self.sim.Project(
                        name=PROJECT_NAME, description="STEM Racing sidepod evolution (automated)",
                        measurement_system="SI", tags=["sidepod"])).project_id
                k["project"] = str(found)
            self._save()
        if not k["box"]:
            k["box"] = ST.make_box(self.sim, api, k["project"])
            self._save()
        return api, k["project"], k["box"]

    def _live_keys(self):
        return [fp for fp in self.keys if not self.st["keys"][fp]["retired"]]

    def _free(self, fp):
        """Run slots left on a key: runs started count, and so do cases assigned to it that have not run yet."""
        held = sum(1 for c in self.st["cases"].values() if c.get("fp") == fp and c["phase"] != "run")
        if self.runs_per_key is None:                                  # no run limit: the key is used until SimScale
            return max(0, 1000 - held)                                  # says it is out of core-hours (then retired)
        return max(0, self.runs_per_key - self.st["keys"][fp]["runs"] - held)

    def capacity(self):
        """How many more cars may be submitted with the keys available now."""
        waiting = sum(1 for c in self.st["cases"].values() if c.get("fp") is None)
        return max(0, sum(self._free(fp) for fp in self._live_keys()) - waiting)

    def status(self):
        return {"keys": {fp: {k: v for k, v in d.items() if k != "box"} for fp, d in self.st["keys"].items()},
                "live_keys_in_env": len(self._live_keys()), "capacity": self.capacity(),
                "cases": {cid: {k: c.get(k) for k in ("phase", "fp", "attempt", "last_error")} for cid, c in self.st["cases"].items()}}

    def _assign(self, cid):
        c = self.st["cases"][cid]
        for fp in self._live_keys():
            if self._free(fp) > 0:
                c.update(fp=fp, phase="step", attempt=0)
                return True
        return False

    def _retire(self, fp, why):
        self.st["keys"][fp]["retired"] = str(why)[:200]
        self.st.setdefault("events", []).append({"t": time.time(), "event": "key_retired", "key": fp,
                                                 "runs_on_key": self.st["keys"][fp]["runs"], "why": str(why)[:200]})
        for cid, c in self.st["cases"].items():                       # its unfinished cases go to the next key
            if c.get("fp") == fp and c["phase"] != "run":
                c.update(fp=None, phase="wait", attempt=0)

    # ------------------------------------------------------------------ interface
    def submit(self, cases):
        for c in cases:
            self.st["cases"][c["id"]] = {"folder": str(c["folder"]), "phase": "wait", "fp": None, "t0": time.time()}
        self._save()

    def collect(self):
        for cid in self._handed:
            self._done.pop(cid, None)
        for cid in list(self.st["cases"]):
            c = self.st["cases"][cid]
            try:
                if c["phase"] == "wait":
                    if not self._assign(cid):
                        continue
                self._advance(cid)
                c.pop("last_error", None); c.pop("errors", None)
            except Exception as e:                                     # noqa: BLE001
                self._on_error(cid, e)
            self._save()
        self._handed = set(self._done)
        self._save()
        return dict(self._done)

    def _on_error(self, cid, e):
        c = self.st["cases"].get(cid)
        if c is None:
            return
        msg = f"{type(e).__name__}: {e}"[:400]
        c["last_error"] = msg
        status = getattr(e, "status", None)
        api_side = isinstance(e, self.sim.ApiException) or "Timeout" in msg or "Connection" in msg or "MaxRetry" in msg
        if api_side and (status == 402 or any(w in msg.lower() for w in QUOTA_WORDS)) and c.get("fp"):
            self._retire(c["fp"], msg)
            return
        if api_side and status in (401, 403) and c.get("fp"):
            self._retire(c["fp"], msg)                                  # key reset or revoked
            return
        if api_side:
            return                                                      # transient: retry next tick
        if isinstance(e, GeometryError):                                # the design itself cannot be built/imported
            c["errors"] = c.get("errors", 0) + 1
            if c["errors"] >= 2:
                self._fail(cid, msg)
        # anything else is a bug on our side: the case waits (status shows last_error), the design is not blamed

    def _fail(self, cid, why):
        self.st["cases"].pop(cid, None)
        self._done[cid] = {"D20_N": None, "L20_N": None, "ok": False, "info": {"simscale": str(why)[:500]}}

    # ------------------------------------------------------------------ the state machine
    def _build_step(self, cid, faces):
        import trimesh
        import simscale_step_domain as SD
        folder = Path(self.st["cases"][cid]["folder"])
        body = trimesh.load(folder / "body_mm.stl")                    # STEP frame, mm (Car.export_car_folder)
        out = folder / f"domain_{faces}.step"
        try:
            rep = SD.build_design(self.car, body, out, faces=faces)
        except GeometryError:
            raise
        except Exception as e:                                          # noqa: BLE001  (OCC/sewing on this pod)
            raise GeometryError(f"air volume build: {e!r}") from e
        if not rep["ok"]:
            raise GeometryError(f"air volume failed its checks: {json.dumps(rep, default=float)[:300]}")
        return out

    def _upload(self, api, P, step: Path, name):
        import zipfile
        s = self.sim
        z = step.with_suffix(".zip")
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(step, step.name)
        st = s.StorageApi(api).create_storage()
        api.rest_client.PUT(url=st.url, headers={"Content-Type": "application/octet-stream"}, body=z.read_bytes())
        req = s.GeometryImportRequest(name=name, location=s.GeometryImportRequestLocation(st.storage_id), format="STEP",
                                      input_unit="mm", options=s.GeometryImportRequestOptions(
                                          facet_split=False, sewing=False, improve=True, optimize_for_lbm_solver=False))
        return s.GeometryImportsApi(api).import_geometry(P, req).geometry_import_id

    def _advance(self, cid):
        import simscale_template as ST
        s, c = self.sim, self.st["cases"][cid]
        api, P, box = self._account(c["fp"])
        if c["phase"] == "step":
            try:
                step = self._build_step(cid, FACES[c["attempt"]])
            except GeometryError as e:                                   # try the next triangle count
                c.setdefault("tries", []).append(f"{FACES[c['attempt']]}: {str(e)[:150]}")
                if c["attempt"] + 1 < len(FACES):
                    c["attempt"] += 1
                    return
                return self._fail(cid, f"air volume could not be built: {c['tries']}")
            c.update(import_id=self._upload(api, P, step, f"{cid} try{c['attempt']}"), phase="import", project=P)
            return
        if c["phase"] == "import":
            gi = s.GeometryImportsApi(api).get_geometry_import(P, c["import_id"])
            if gi.status in ("FAILED", "CANCELED"):
                fr = api.sanitize_for_serialization(getattr(gi, "failure_reason", None)) or {}
                where = sorted({f.get("code", "") for f in (fr.get("details") or {}).get("faults", [])})
                c.setdefault("tries", []).append(f"{FACES[c['attempt']]}: import {gi.status} {fr.get('code', '')} {where}"[:300])
                if c["attempt"] + 1 < len(FACES):
                    c.update(attempt=c["attempt"] + 1, phase="step")
                    return
                return self._fail(cid, f"import refused {len(FACES)} times")
            if gi.status != "FINISHED":
                return
            if self._wheels is None:
                self._wheels = ST.wheel_centres_m()
            sid, mo = ST.create_case(s, api, P, gi.geometry_id, f"sidepod {cid}", box, None, self._wheels,
                                     self.fineness, self.box_mm, self.iters, sizing=self.sizing)
            m_api = s.MeshOperationsApi(api)
            m_api.start_mesh_operation(P, mo, simulation_id=sid)
            c.update(phase="mesh", geometry_id=gi.geometry_id, sim_id=sid, mesh_op=mo)
            return
        if c["phase"] == "mesh":
            m_api, s_api = s.MeshOperationsApi(api), s.SimulationsApi(api)
            mo = m_api.get_mesh_operation(P, c["mesh_op"])
            if mo.status in ("FAILED", "CANCELED"):
                why = ""
                try:
                    why = "; ".join(f"{e.code}: {e.message[:200]}" for e in (m_api.get_mesh_operation_event_log(P, c["mesh_op"]).entries or [])
                                    if e.severity == "ERROR")
                except Exception:                                        # noqa: BLE001
                    pass
                c.setdefault("tries", []).append(f"{FACES[c['attempt']]}: mesh {mo.status} {why}")
                if mo.status == "FAILED" and c["attempt"] + 1 < len(FACES):   # another triangle count, new import
                    c.update(attempt=c["attempt"] + 1, phase="step")
                    return
                return self._fail(cid, f"mesh failed: {c['tries']}")
            if mo.status != "FINISHED":
                return
            c["mesh_done"] = True
            try:
                c["cells"] = s.MeshesApi(api).get_mesh(P, mo.mesh_id).number_of_cells
            except Exception:                                            # noqa: BLE001
                pass
            if os.environ.get("SIMSCALE_HOLD_RUNS"):                     # smoke tests: stop before spending a run
                return
            spec = s_api.get_simulation(P, c["sim_id"]); spec.mesh_id = mo.mesh_id
            s_api.update_simulation(P, c["sim_id"], spec)
            chk = s_api.check_simulation_setup(P, c["sim_id"])
            errs = [getattr(e, "message", str(e)) for e in (chk.entries or []) if e.severity == "ERROR"]
            if errs:
                return self._fail(cid, f"simulation check: {errs}")
            cost = None
            try:
                est = s_api.estimate_simulation_setup(P, c["sim_id"])
                cost = est.compute_resource.value if est.compute_resource is not None else None
            except s.ApiException as e:
                if e.status != 422:
                    raise
            if self.max_cost is not None and cost is not None and cost > self.max_cost:
                return self._fail(cid, f"too expensive: estimate {cost} > max_cost {self.max_cost}")
            r_api = s.SimulationRunsApi(api)
            run = r_api.create_simulation_run(P, c["sim_id"], s.SimulationRun(name="run"))
            r_api.start_simulation_run(P, c["sim_id"], run.run_id)
            self.st["keys"][c["fp"]]["runs"] += 1
            c.update(phase="run", run_id=run.run_id, cost_estimate=cost)
            return
        if c["phase"] == "run":
            r_api = s.SimulationRunsApi(api)
            run = r_api.get_simulation_run(P, c["sim_id"], c["run_id"])
            if run.status in ("FAILED", "CANCELED"):
                codes = []
                try:
                    codes = [e.code for e in (r_api.get_simulation_run_event_log(P, c["sim_id"], c["run_id"]).entries or [])
                             if e.severity == "ERROR"]
                except Exception:                                        # noqa: BLE001
                    pass
                msgs = ""
                try:
                    msgs = " ".join((e.message or "") for e in (r_api.get_simulation_run_event_log(P, c["sim_id"], c["run_id"]).entries or [])
                                    if e.severity == "ERROR").lower()
                except Exception:                                        # noqa: BLE001
                    pass
                if any(w in msgs for w in RUN_QUOTA_WORDS) or any("QUOTA" in x or "CREDIT" in x for x in codes):
                    self._retire(c["fp"], f"run refused: {codes} {msgs[:150]}")   # the account, not the design
                    c.update(fp=None, phase="wait", attempt=0)
                    return
                c.setdefault("tries", []).append(f"{FACES[c['attempt']]}: run {run.status} at {run.progress} {codes}")
                # divergence in the first few % of iterations is a bad mesh element (seen at iteration 1),
                # not the design: mesh it again from another pod triangle count
                early = (run.progress or 0.0) < 0.05 and "MSG_OF_CHECK_MESH_OR_NUMERICS" in codes
                if run.status == "FAILED" and early and c["attempt"] + 1 < len(FACES):
                    c.update(attempt=c["attempt"] + 1, phase="step")
                    return
                return self._fail(cid, f"run {run.status}: {c['tries']}")
            if run.status != "FINISHED":
                c["progress"] = getattr(run, "progress", None)
                return
            try:
                Fx, Fz, info = forces(s, api, P, c["sim_id"], c["run_id"])
            except Exception as e:                                       # noqa: BLE001
                # The run finished but its forces cannot be read. An account that locks results (plan limit,
                # payment) answers 401/402/403 or a quota message, or lists no results at all: after 3 ticks
                # of that the key is retired and the car is solved again on the next key.
                msg, st = f"{type(e).__name__}: {e}"[:300], getattr(e, "status", None)
                locked = st in (401, 402, 403) or any(w in msg.lower() for w in QUOTA_WORDS) or "no force result among []" in msg
                if not locked:
                    raise
                c["result_blocked"] = c.get("result_blocked", 0) + 1
                if c["result_blocked"] < 3:
                    return
                k = self.st["keys"][c["fp"]]
                self.st.setdefault("events", []).append({"t": time.time(), "event": "results_blocked", "key": c["fp"],
                                                         "runs_on_key": k["runs"], "case": cid, "error": msg})
                self._retire(c["fp"], f"results blocked after {k['runs']} runs: {msg[:120]}")
                c.update(fp=None, phase="wait", attempt=0, result_blocked=0)
                return
            # A run can finish all its iterations without converging (c00068: Fx spread 2.66 N over the
            # last 15 %, lift 637 N; good runs spread 0.001-0.003 N). That is the mesh, not the design:
            # mesh it again from another pod triangle count, and fail the design only when none converges.
            if diverged_forces(Fx, Fz, info):
                c.setdefault("tries", []).append(f"{FACES[c['attempt']]}: not converged, Fx {Fx:.3g} spread {info.get('Fx_window_std'):.3g}, Fz {Fz:.3g}")
                if c["attempt"] + 1 < len(FACES):
                    c.update(attempt=c["attempt"] + 1, phase="step")
                    return
                return self._fail(cid, f"not converged: {c['tries']}")
            sc = 2.0 * (20.0 / self.speed) ** 2                           # half car -> whole car, at 20 m/s
            self.st["cases"].pop(cid)
            self._done[cid] = {"D20_N": Fx * sc, "L20_N": Fz * sc, "ok": True,
                               "info": {"simscale_sim": c["sim_id"], "run": c["run_id"], "project": P, "key": c["fp"],
                                        "cost_estimate": c.get("cost_estimate"), "pod_faces": FACES[c["attempt"]], "cells": c.get("cells"),
                                        "wall_s": time.time() - c["t0"], **info}}


def forces(s, api, P, sid, run_id):
    """(Fx, Fz, info) of the half car: the mean over the last 15 % of iterations of the total force
    on car + wheels, from the 'Forces and moments' result; info has the spread of that window."""
    res = s.SimulationRunsApi(api).get_simulation_run_results(P, sid, run_id, limit=100, page=1)
    items = [api.sanitize_for_serialization(x) for x in (res.embedded or [])]
    cand = [d for d in items if "FORCE" in (d.get("category") or "").upper() and (d.get("download") or {}).get("url")]
    if not cand:
        raise ValueError(f"no force result among {[(d.get('category'), d.get('name')) for d in items]}")
    txt = api.rest_client.GET(cand[0]["download"]["url"], headers={"X-API-KEY": api.configuration.api_key["X-API-KEY"]}).data
    txt = txt.decode() if isinstance(txt, bytes) else txt
    return parse_forces(txt)


def diverged_forces(Fx, Fz, info, max_spread=0.02, max_force=2.0):
    """True for a run whose half-car forces did not settle: not finite, an Fx spread over the averaging
    window above max(max_spread, 10 % of Fx), or forces far outside anything this car makes (N, half car,
    at the run speed)."""
    sd = info.get("Fx_window_std")
    if not (np.isfinite(Fx) and np.isfinite(Fz)) or (sd is not None and not np.isfinite(sd)):
        return True
    if abs(Fx) > max_force or abs(Fz) > max_force:
        return True
    return sd is not None and sd > max(max_spread, 0.1 * abs(Fx))


def parse_forces(txt, tail=0.15):
    import csv
    import io
    rows = [r for r in csv.reader(io.StringIO(txt)) if r]
    head = [h.strip().lower() for h in rows[0]]

    def col(axis):
        want = [i for i, h in enumerate(head) if "force" in h and re.search(rf"(^|[^a-z]){axis}([^a-z]|$)", h)]
        tot = [i for i in want if "total" in head[i]]
        if tot:
            return tot, "total"
        pv = [i for i in want if "pressure" in head[i] or "viscous" in head[i]]
        if pv:
            return pv, "pressure+viscous"
        raise ValueError(f"no force {axis} column in {head}")
    ix, kind = col("x"); iz, _ = col("z")
    D = np.array([[float(r[0])] + [sum(float(r[i]) for i in ix), sum(float(r[i]) for i in iz)] for r in rows[1:]
                  if re.match(r"^[-+0-9.eE]+$", r[0].strip())])
    n = len(D)
    w = D[int((1 - tail) * n):]
    prev = D[int((1 - 2 * tail) * n):int((1 - tail) * n)]
    return float(w[:, 1].mean()), float(w[:, 2].mean()), {
        "iters": int(D[-1, 0]), "force_columns": kind, "Fx_window_std": float(w[:, 1].std()),
        "Fx_prev_window_mean": float(prev[:, 1].mean()) if len(prev) else None}
