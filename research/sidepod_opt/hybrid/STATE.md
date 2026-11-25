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
| Round 1b | 45467103535 | done: mark E met; 0.5 mm: DAFoam -4.84, ESI -3.57, rnd1 -2.70 |
| Round 1c (opposites at 0.5 mm; production pair) | resolved_bumps 45486415307 (20:59) | running; marks S, P in HYBRID_TEST.md |
| Chained morph checks | morph_check 45486612820 | done: 2 of 4 clean to 1.5-2 mm |
| DAFoam at daf 0.5/1.0 designs | coarse_dafoam 45477836968 | running |
Next: generation 2 (round 3) = best <= 0.5 mm design + 0.5 mm children (fresh DAFoam guide via dafnpz:, randoms 11-16, guided, es).
| Round 2 (H2) | 45482339933 | FAIL at 0.125 (ES -1.84 > GUIDED -1.40); DAFoam 1.0 mm -6.93 best |
| Generation 2 (round 3), first launch | 45501421243 | all failed in the morph (settings bug, fixed) |
| Generation 2 relaunch | resolved_bumps 45503888773 (22:45) | running |
| DAFoam at daf@1.0 retry | coarse_dafoam (22:31) | running |
| Round 2b (ES/GUIDED-DAF/GUIDED-ESI at 0.5 mm) | resolved_bumps 45501709693 (22:31) | running |
| Round 1c | 45486415307 | dafopp_05E done (+4.05, job log); rnd1m_05E and the production pair (2000 its) still running |
| Round 2b | 45501709693 | done: at 0.5 mm combined -5.24 best, evolution alone -2.62 |
| Round 1c | 45486415307 | done: Mark S met; Mark P not met (production noise 3 SE 12.5 mN) |
| Generation 2 relaunch | 45503888773 | Mark L met: ESI 0.5 accepted, total -8.21 mN; parent now daf@1.0|esi_frozen@0.5 |
| Generation 3 (loop.py next 3) | resolved_bumps 45519631311 (00:38) | running; then `python hybrid/loop.py next 4 <fresh npz>` |
| DAFoam at gen-3 parent | coarse_dafoam (00:38) | running |
| Fresh ESI at gen-3 parent (re-solve + frozen adjoint) | resolved_bumps 45519814660 (00:39) | running; output hybrid/esi_after/45519814660/ |
