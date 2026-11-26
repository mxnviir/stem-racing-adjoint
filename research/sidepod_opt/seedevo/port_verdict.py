"""TS and TC2 verdicts: python seedevo/port_verdict.py <files...>"""
import json, sys
import numpy as np
rows = []
for p in sys.argv[1:]:
    d = json.load(open(p)); rows += [dict(r, problem=d["problem"]) for r in d["rows"]]
for test, a, b in (("TS", "evo_screen", "evo"), ("TC2", "gf_cma", "gf")):
    A = {(r["problem"], r["seed"]): r["true_best"] for r in rows if r["test"] == test and r["arm"] == a}
    B = {(r["problem"], r["seed"]): r["true_best"] for r in rows if r["test"] == test and r["arm"] == b}
    k = sorted(set(A) & set(B)); wins = sum(A[x] < B[x] for x in k)
    per = {pr: (round(np.mean([A[x] for x in k if x[0] == pr]), 3), round(np.mean([B[x] for x in k if x[0] == pr]), 3)) for pr in sorted({x[0] for x in k})}
    print(f"{test}: {a} better than {b} in {wins}/{len(k)} pairs -> {'PASS' if wins >= 11 else 'FAIL'} (mark: >= 11 of 15); means per instance ({a}, {b}): {per}")
