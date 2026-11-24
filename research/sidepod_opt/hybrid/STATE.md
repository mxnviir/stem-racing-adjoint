# Hybrid work: state (for picking up after a context reset)
Started 2026-11-24 ~18:15 UTC; owner's budget 18 h -> deliver by ~12:15 UTC 2026-11-25.

| what | run | status |
|---|---|---|
| Round 1 (H1), 13 resolved solves | resolved_bumps 45461604257 | PASS (hybrid/R1_VERDICT.txt) |
| Larger-step morph checks (7) | morph_check 45461955558 (18:40) | running; results in esi/morph_check/results_45461955558.md |
| DAFoam on Actions smoke test | coarse_dafoam 45462436057 (18:42) | PASSED 20:08 (r 0.999999, cos 0.9985, adjoint 59 min) |
| Explicit-morph checks (7) | morph_check 45465008793 | done: 0.5 mm OK, 1 mm acceptable (1 skew face) for rnd2/daf, 2 mm folds |
| Round 1b, 6 solves (explicit morph, larger steps) | resolved_bumps 45467103535 (19:08) | running; daf_10E will fail strict (1 skew face; rule fixed in 7d855e6 after launch) -> redo in round 2 |
| DAFoam gradients at daf 0.5 / 1.0 mm designs | coarse_dafoam (20:12) | running |
| Round 2 (H2), 8 solves | resolved_bumps 45482339933 (20:35) | running; verdict: `python hybrid/r2_verdict.py` |
