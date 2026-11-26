"""T3e verdict by the marks in SEED_EVOLUTION_PLAN.md (TC1-TC5).   python seedevo/t3e_verdict.py <t3e.json>"""
import json, sys
import numpy as np
D = json.load(open(sys.argv[1])); R = D["rows"]
def g(arm, sc):
    rows = [r for r in R if r["arm"] == arm and r["scen"] == (sc if arm in ("plain", "tc") else "S1")]
    return {(r["problem"], r["seed"]): r for r in rows}
def le(a, b): return sum(a[k]["true_best"] <= b[k]["true_best"] for k in a if k in b), len(a)
ev, gf = g("evo", "S1"), g("gf", "S1")
m = lambda d: float(np.mean([r["true_best"] for r in d.values()]))
print("mean true score of the handed design (lower = better)")
print(f"  evo {m(ev):.3f}  gf {m(gf):.3f}")
for sc in ("S1", "S2", "S3", "S4", "S5"):
    p, t = g("plain", sc), g("tc", sc)
    tr = sum(r["trusted"] for r in t.values()); n = sum(r["trust_checks"] for r in t.values())
    print(f"  {sc}: plain {m(p):.3f}  tc {m(t):.3f}   trusted {tr}/{n} ({tr / max(n, 1):.0%})  tc<=plain {le(t, p)[0]}/15  tc<=evo {le(t, ev)[0]}/15  tc<=gf {le(t, gf)[0]}/15")
P = {sc: g("plain", sc) for sc in ("S1", "S2", "S3", "S4", "S5")}; T = {sc: g("tc", sc) for sc in P}
share = lambda sc: sum(r["trusted"] for r in T[sc].values()) / max(sum(r["trust_checks"] for r in T[sc].values()), 1)
tc1 = m(T["S1"]) - m(P["S1"]) <= 0.25 * (m(ev) - m(P["S1"]))
tc2 = all(le(T[s], P[s])[0] >= 10 for s in ("S3", "S5"))
tc3 = all(le(T[s], P[s])[0] >= 8 for s in ("S2", "S4"))
tc4 = all(le(T[s], ev)[0] >= 10 for s in P)
tc5 = share("S1") >= 0.5 and share("S4") <= 0.2 and share("S5") <= 0.2
for k, v in (("TC1 cheap when good", tc1), ("TC2 misleading", tc2), ("TC3 useless", tc3), ("TC4 never worse than no polish", tc4),
             ("TC5 discriminates", tc5)):
    print(f"{k}: {'PASS' if v else 'FAIL'}")
print("T3e:", "PASS" if all((tc1, tc2, tc3, tc4, tc5)) else "FAIL")
