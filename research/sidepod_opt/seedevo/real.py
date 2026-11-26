"""The real evaluator for engine.py: OpenFOAM through gate.py's own pipeline, and OpenFOAM's (ESI) adjoint.

    ev = RealEvaluator(space, store_dir)          # env: GATE_RES (coarse), CFD_DIV_U (steady model), GATE_RESULTS
    ev.fresh(ind, k)        fresh mesh (meshing frame shifted by k x 0.37 mm, DECISIONS D7) -> half-car D20, mN
    ev.morph(parent, child) the parent's kept mesh morphed onto the child, warm start; minus the parent morphed
                            onto ITSELF (cached per parent run): the morph path's own offset cancels
                            -> {"delta": mN, "move": mm} or None (the morph failed checkMesh: strict, no fallback)
    ev.adjoint(ind)         ESI frozen-turbulence adjoint on the parent's kept converged run -> sensitivity on the
                            1 mm grid: whole-car dD (N) per mm of OUTWARD move, per cell (shape_loop.grid_gradient)
Every call appends one line to <store>/calls.jsonl (what ran, its numbers, wall time), so a run can be audited.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / "part2-simulation"))

FRAME_DX_MM = 0.37


class RealEvaluator:
    cost_fresh, cost_morph, cost_adjoint = 1.0, 0.5, 0.3

    def __init__(self, space, store, n_proc=4, iters_cold=2500, iters_warm=1200, adj_iters=1000,
                 sigma_fresh=0.32, sigma_morph=0.0025):
        import gate
        self.gate, self.sp, self.n = gate, space, n_proc
        self.store = Path(store); self.store.mkdir(parents=True, exist_ok=True)
        self.iters_cold, self.iters_warm, self.adj_iters = iters_cold, iters_warm, adj_iters
        self.sigma_fresh, self.sigma_morph = sigma_fresh, sigma_morph      # coarse: fresh-mesh scatter, morph pairs (ROUTES)
        self.runs, self.zero = {}, {}                                      # ind id -> (kept run, D); run -> zero-morph D

    def _log(self, **rec):
        with open(self.store / "calls.jsonl", "a") as fh:
            fh.write(json.dumps(rec, default=float) + "\n")
        print("CALL", json.dumps(rec, default=float)[:400], flush=True)

    def folder(self, ind):
        """The car folder of a design (exported once): car_half.stl, wheels, assembly, mass."""
        import shape_loop as SL
        d = self.store / f"d{ind.id:04d}"
        if not (d / "car" / "car_half.stl").exists():
            b = ind.meta.get("built")
            if b is None:
                raise RuntimeError(f"design {ind.id} has no build to export")
            SL.export_design(self.sp.car, b, d, f"d{ind.id}")
            np.savez_compressed(d / "field.npz", f=ind.f.astype(np.float32))
        return d / "car"

    def _solve(self, folder, iters, extra=None, dx_mm=0.0, tag=""):
        g = self.gate
        os.environ["GATE_DOMAIN_DX_MM"] = f"{dx_mm:.4f}"
        t = time.time()
        try:
            half, health, secs = g.solve(folder, self.n, iters, extra=extra, keep=True)
        finally:
            os.environ["GATE_DOMAIN_DX_MM"] = "0"
        run = g.latest_run_of(os.getpid())
        fell_back = bool(run and (Path(run) / "MORPH_FALLBACK").exists())
        keep = self.store / "runs" / tag
        if run:
            if keep.exists():
                shutil.rmtree(keep)
            shutil.copytree(run, keep, ignore=shutil.ignore_patterns("processor*"))
            shutil.rmtree(run, ignore_errors=True)
        r = g.rec(half, health, secs, run_dir_kept=str(keep), morph_fallback=fell_back)
        r["D_mN"] = float(half.D20) * 1e3
        r["L_mN"] = float(half.L) * 1e3 if hasattr(half, "L") else None
        r["wall_s"] = round(time.time() - t, 1)
        return r

    # ------------------------------------------------------------------ engine interface
    def fresh(self, ind, k):
        folder = self.folder(ind)
        tag = f"d{ind.id:04d}_fresh{k}"
        try:
            r = self._solve(folder, self.iters_cold, dx_mm=k * FRAME_DX_MM, tag=tag)
        except Exception as e:                                   # a failed mesh or solve: no score
            self._log(call="fresh", id=ind.id, k=k, error=repr(e)[:300]); return None
        self._log(call="fresh", id=ind.id, k=k, kind=ind.kind, op=ind.op, parents=ind.parents, desc=ind.desc,
                  D_mN=r["D_mN"], L_mN=r["L_mN"], converged=r["converged"], osc=r["force_osc"], stderr=r["force_mean_stderr"],
                  wall_s=r["wall_s"])
        if not r["converged"]:
            return None
        self.runs[ind.id] = (r["run_dir_kept"], r["D_mN"])
        return r["D_mN"]

    def _morph_solve(self, parent, folder, tag):
        ref, _ = self.runs[parent.id]
        import stopwatch as SW
        pf = self.folder(parent)
        os.environ["P2_MORPH_REF_STL"] = str(SW.body_stl(pf / "car_half.stl", pf / "_body_half.stl"))
        os.environ["P2_MORPH_STRICT"] = "1"
        try:
            return self._solve(folder, self.iters_warm, extra={"morph_from": ref, "warm_from": ref}, tag=tag)
        finally:
            os.environ.pop("P2_MORPH_REF_STL", None); os.environ.pop("P2_MORPH_STRICT", None)

    def morph(self, parent, child):
        if parent.id not in self.runs:
            return None
        sp = self.sp
        b = sp.region & ((np.abs(parent.f) <= 1.5 * sp.h) | (np.abs(child.f) <= 1.5 * sp.h))
        move = float(np.abs(child.f - parent.f)[b].max()) if b.any() else 0.0
        ref, _ = self.runs[parent.id]
        try:
            if ref not in self.zero:                             # the parent morphed onto itself: the path's own offset
                z = self._morph_solve(parent, self.folder(parent), f"d{parent.id:04d}_zero")
                self.zero[ref] = z["D_mN"] if (z["converged"] and not z["morph_fallback"]) else None
                self._log(call="zero_morph", id=parent.id, D_mN=z["D_mN"], fresh_D_mN=self.runs[parent.id][1],
                          offset_mN=z["D_mN"] - self.runs[parent.id][1], converged=z["converged"], wall_s=z["wall_s"])
            if self.zero[ref] is None:
                return None
            r = self._morph_solve(parent, self.folder(child), f"d{child.id:04d}_on{parent.id:04d}")
        except Exception as e:
            self._log(call="morph", parent=parent.id, child=child.id, move_mm=move, error=repr(e)[:300]); return None
        ok = r["converged"] and not r["morph_fallback"]
        d = r["D_mN"] - self.zero[ref]
        self._log(call="morph", parent=parent.id, child=child.id, move_mm=move, D_mN=r["D_mN"], delta_mN=d, ok=ok,
                  pred_mN=child.meta.get("pred"), wall_s=r["wall_s"])
        if not ok:
            return None
        self.runs[child.id] = (r["run_dir_kept"], r["D_mN"])     # the child's own morphed state: it can be refined further
        self.zero[r["run_dir_kept"]] = r["D_mN"]
        return {"delta": float(d), "move": move}

    def adjoint(self, ind):
        import shape_loop as SL
        if ind.id not in self.runs:
            return None
        run, _ = self.runs[ind.id]
        out = self.store / "adjoint" / f"d{ind.id:04d}"
        t = time.time()
        p = subprocess.run([sys.executable, "-W", "ignore", str(HERE / "esi" / "esi_on_state.py"), run, str(out), "frozen",
                            str(self.n), str(self.adj_iters), "100"], capture_output=True, text=True, cwd=HERE)
        sens = out / "esi_sens.npz"
        if p.returncode != 0 or not sens.exists():
            self._log(call="adjoint", id=ind.id, error=(p.stdout + p.stderr)[-600:]); return None
        S = np.load(sens)
        g, info = SL.grid_gradient(self.sp.car, self.folder(ind), S["Xs"], S["dD_dXs"])
        self._log(call="adjoint", id=ind.id, wall_s=round(time.time() - t, 1), **info)
        for d in out.glob("processor*"):
            shutil.rmtree(d, ignore_errors=True)
        return g

    def grad_step(self, space, e, step_mm):
        from . import operators as OP
        f, pred = OP.grad_step(space, e.f, e.grad, step_mm)
        return f, pred * 1e3 / 2.0                              # whole-car N -> half-car mN (first-order prediction)
