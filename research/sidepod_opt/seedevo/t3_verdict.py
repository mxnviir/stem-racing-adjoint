"""Verdicts of T3a-T3d from a run_t3 result file, by the marks in SEED_EVOLUTION_PLAN.md section 7.
    python seedevo/t3_verdict.py <t3.json> [key]      key: true_best (default, the registered score) or confirmed_true"""
import json, sys
import numpy as np
D = json.load(open(sys.argv[1])); key = sys.argv[2] if len(sys.argv) > 2 else "true_best"
R = D["rows"]; H = D["head"]
rhos = sorted({r["rho"] for r in R}, reverse=True); r0 = rhos[0]
def get(arm, rho):
    rows = [r for r in R if r["arm"] == arm and r["rho"] == rho] or [r for r in R if r["arm"] == arm and r["rho"] == r0]
    return {r["seed"]: r[key] for r in rows}
def wins(a, b, rho_a, rho_b=None, tie_ok=False):
    A, B = get(a, rho_a), get(b, rho_b if rho_b is not None else rho_a)
    s = sorted(set(A) & set(B))
    return sum((A[i] <= B[i]) if tie_ok else (A[i] < B[i]) for i in s), len(s)
print(f"problem {H['problem']}, budget {H['budget']}, sigma_fresh {H['sigma_fresh']:.3f}, best seed (true) {H['best_seed_true']:.3f}, score = {key}")
for rho in rhos:
    print(f"rho {rho:+.2f}: " + "  ".join(f"{a} {np.mean(list(get(a, rho).values())):.2f}" for a in
          ("evo", "randpar", "mutonly", "polish", "evo_polish", "memetic", "memetic_g", "evo60") if any(r["arm"] == a for r in R)))
def mark(name, pairs):
    res = [wins(*p) for p in pairs]
    ok = all(w >= 4 for w, n in res)
    print(f"{name}: {'PASS' if ok else 'FAIL'}  " + "; ".join(f"{p[0]} vs {p[1]}: {w}/{n}" for p, (w, n) in zip(pairs, res)))
mark("T3a evolution works", [("evo", "randpar", r0), ("evo", "mutonly", r0)])
mark(f"T3b adjoint in the loop pays (rho {r0})", [("memetic", "evo", r0), ("memetic", "evo_polish", r0), ("memetic", "polish", r0)])
for rho in [x for x in rhos if x <= 0]:
    w, n = wins("memetic", "evo60", rho, r0, tie_ok=True)
    print(f"T3c bad adjoint is safe (rho {rho:+.2f}): {'PASS' if w >= 4 else 'FAIL'}  memetic no worse than evo60: {w}/{n}")
for rho in rhos:
    w, n = wins("memetic_g", "memetic", rho)
    print(f"T3d (reported) rho {rho:+.2f}: memetic_g better than memetic in {w}/{n}")
