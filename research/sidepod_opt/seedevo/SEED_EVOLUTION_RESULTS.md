# Seed evolution: test results

Marks are in `SEED_EVOLUTION_PLAN.md` section 7, each committed before the run it judges. Lower score = better.
The bench (`toy.py`) tests the search machinery, not aerodynamics.

## T0 Ingest (real car, `results/t0_ingest.json`)
| | measured | mark | verdict |
|---|---|---|---|
| trial-car STEP rebuilt: volume | within 0.5 % | 0.5 % | pass |
| surface, built vs CAD (p99) | 0.46 mm | 0.3 mm (owner: 0.5 mm accepted for now) | pass under the owner's 0.5 mm |
| round trip of the grooved pod: volume | within 0.5 % | 0.5 % | pass |
| round trip surface (p99) | 0.35 mm | as above | pass under 0.5 mm |

## T0b Operators (real car, real builder, 40 draws each, `results/t0b_operators.json`)
| operator | legal | children in the band (IoU 0.50-0.98) | near-copies (IoU > 0.98) | foam the mill put back | verdict |
|---|---|---|---|---|---|
| splice | 100 % | 88 % | 12 % | 0.1 % | pass |
| graft | 100 % | 80 % | 20 % | 0.4 % | pass |
| line | 100 % | 97 % | 3 % | 0.8 % | pass |
| pattern | 88 % | 83 % | 17 % | 2.5 % | pass |
| offset | 100 % | 82 % | 17 % | 0.8 % | pass |
| combine | 100 % | 38 % | 62 % | 0.2 % | FAIL (too timid) |
| bump | 100 % | 60 % | 40 % | 0.4 % | FAIL (too timid) |
| cut | 97 % | 69 % | 31 % | 1.4 % | FAIL (69 % vs 70 %; too timid) |
| fill | 100 % | 33 % | 68 % | 0.4 % | FAIL (too timid) |

No operator fails on legality or on the mill. The four failures make changes too small to be worth a CFD
run. New through-openings on the real car: `cut` 12 of 39 legal children, `pattern` 7 of 35 (the ten test
seeds have none).

## T3 Search machinery (bench)
**Instance 1, as registered (`results/t3_problem1.json`): T3a, T3b, T3c FAIL.** Diagnosis and amendment B:
plan section 7.

**Held-out instances 2-4 with amendment B** (`results/t3_heldout_p{2,3,4}.json`; a mark passes on an
instance at >= 4 of 5 seeds, overall at >= 2 of 3 instances):

| mark | instance 2 | instance 3 | instance 4 | overall |
|---|---|---|---|---|
| T3a evolution beats random parents and mutation-only | pass | fail (mutation-only 3/5) | pass | **PASS** |
| T3b adjoint in the loop beats evo, evolve-then-polish, polish-only (rho 0.85) | pass | fail | fail | **FAIL** |
| T3c a useless (rho 0) or misleading (rho -0.3) adjoint costs no more than its share | fail | pass | fail | **FAIL** |

Mean score of the handed design, rho 0.85 (best seed: 3.68 / 3.99 / 3.15):

| arm | inst. 2 | inst. 3 | inst. 4 |
|---|---|---|---|
| evolution only (`evo`) | 1.35 | 3.46 | 2.38 |
| evolve, then the adjoint at the end (`evo_polish`) | 1.21 | 2.55 | **2.07** |
| the adjoint in the loop (`memetic`) | **1.03** | **2.42** | 2.18 |
| the adjoint alone from the seeds (`polish`) | 1.57 | 2.55 | 2.64 |

Within T3b, `memetic` beats `evo` on all three instances (5/5, 5/5, 4/5); it fails against `evo_polish`
(5/5, 3/5, 3/5).

**What the registered rules conclude:**
- T3b fails, and fails because of `evo_polish`: **the adjoint goes at the end** (plan, amendment B).
- T3c fails: with a useless or misleading adjoint, in-loop refinement lost to evolution with 60 % of the
  budget on 2 of 3 instances. It never made a design worse (CFD rejects bad steps: with rho -0.3, 0 to 14 of
  about 220 steps were accepted), but it spent runs that evolution would have used better. An in-loop
  adjoint would need a stop rule, re-tested on instances 5-7.
- Not marked: the adjoint at the end improved on evolution alone on every instance (1.35 -> 1.21,
  3.46 -> 2.55, 2.38 -> 2.07), and with a useless adjoint it cost almost nothing (1.34, 3.47, 2.42 against
  evo's 1.35, 3.46, 2.38).

## T3e Trust check (held-out instances 5-7, `results/t3e_heldout.json`): **FAIL as registered**
| scenario (adjoint quality) | plain polish | with trust check | trusted | check no worse than plain |
|---|---|---|---|---|
| S1 good everywhere | 2.744 | 2.803 | 32 % | 8/15 |
| S2 good closed, useless open | 2.786 | 2.900 | 26 % | 6/15 |
| S3 good closed, misleading open | 2.772 | 2.970 | 22 % | 6/15 |
| S4 useless everywhere | 3.555 | **3.441** | 8 % | 12/15 |
| S5 misleading everywhere | 3.502 | **3.464** | 1 % | 11/15 |
Evolution alone 3.403; gradient-free polish only 3.381.

TC1 (cheap when good) PASS; TC2 (S3 fails 6/15) FAIL; TC3 (S2 fails 6/15) FAIL; TC4 (never worse than no
polish) PASS; TC5 (trusted only 32 % in S1, needs 50 %) FAIL.

Diagnosis (instance 5, S1, seeds 1-3, after the verdict): of 27 checks, 8 trusted and **all 19 distrusts were a
downhill probe the morph refused** (a fold or a topology change), never a measured wrong direction: the same
"missing measurement counted as distrust" bug that was fixed for the uphill probe, still present for the
downhill one. And the instances did not exercise S2/S3: 0, 0 and 1 of 12 seeds had a through-opening and no
target had one, so "bad on pods with openings" rarely applied.

What it did show: with a useless or misleading adjoint everywhere (S4, S5), the plain polish is worse than not
polishing at all (3.56 / 3.50 against 3.40: the polish's 30 % of the budget is wasted), and the check recovers
part of it (3.44 / 3.46). With a good adjoint, the plain polish is worth 0.66 (3.40 -> 2.74).

## TP Plumbing on real coarse CFD (GitHub Actions run 45792787835, 2.3 h, `results/plumbing_45792787835/`): **PASS**
P1 every stage ran (fresh mesh, solve, ESI adjoint, sensitivity on the grid, step, build, morph solve, decision),
no errors. P2 team pod 449.24 mN whole car (reference 449.24) and no pod +22.1 mN half car (mark >= 15). P3
both refined elites decided from morphed steps. P4 opening-changing crossover (graft) and mutation (pattern)
children meshed and converged.

Reported, not marked (coarse mesh: no design conclusion, D6), half car, steady model, mN:
- census: groove 220.96, team 224.62, window 223.09, slots 226.67, no pod 246.69;
- explore: line (groove x slots) 219.77 (took the groove's niche), graft 222.39, pattern 224.53 / 226.58;
- refine (ESI adjoint, morph-scored; the morph's own offset measured at -0.006 / -0.002 mN): groove -1.54 at
  0.5 mm (the 1 mm step folded the mesh), window pod -2.49 at 1 mm and -1.40 at 0.5 mm, both accepted;
  first-order predictions -1.10, -2.77, -1.39. On this coarse mesh ESI's sizes were close to measured, unlike
  the wall-resolved bump test; one coarse case, not evidence that the adjoint is accurate on a good mesh.

## T3e' Trust check after the fix (held-out instances 8-10, half the seeds windowed, windowed targets; `results/t3e2_heldout.json`): **FAIL as registered, by one pair**
| scenario | plain polish | with trust check | trusted (decided checks) | undecided | check no worse than plain |
|---|---|---|---|---|---|
| S1 good everywhere | 2.965 | 2.980 | 99 % | 63/152 | 9/15 |
| S2 good closed, useless open | 3.165 | **3.107** | 53 % | 70/167 | 10/15 |
| S3 good closed, misleading open | 3.205 | **3.178** | 46 % | 75/169 | **9/15** |
| S4 useless everywhere | 3.585 | **3.486** | 19 % | 69/176 | 13/15 |
| S5 misleading everywhere | 3.604 | **3.484** | 1 % | 69/179 | 13/15 |
Evolution alone 3.540; gradient-free polish only 3.463.

TC1 (cheap when good) PASS; **TC2 FAIL** (S5 13/15 passes, S3 9/15 against the mark of 10); TC3 PASS (S2 10/15,
S4 13/15); TC4 PASS; TC5 PASS (99 % / 19 % / 1 %). The fix worked where it was aimed: a good adjoint is now trusted
on 99 % of decided checks (was 32 %), a useless one on 19 %, a misleading one on 1 %. With a bad adjoint the check
beats the unchecked polish on average in every scenario, and in 13 of 15 pairs when it is bad everywhere. The one
miss: misleading only on open pods (S3), where it is ahead on average but not in 10 of 15 pairs.
About 40 % of checks were undecided (the bench's morph refused even the half-size probe), so in practice a large
share of designs gets the gradient-free polish whatever the adjoint's quality.

## T0b' and T0b'' Operator re-tests (real car, same 10 test seeds, new draws): **all nine operators now pass**
| operator | attempt | legal | in band | near-copies | mill refill | verdict |
|---|---|---|---|---|---|---|
| bump | T0b' (wider random ranges) | 100 % | 93 % | 8 % | 0.6 % | PASS |
| cut | T0b' (wider random ranges) | 95 % | 84 % | 16 % | 1.1 % | PASS |
| combine | T0b' | 100 % | 53 % | 48 % | 0.2 % | FAIL |
| fill | T0b' | 100 % | 53 % | 48 % | 0.5 % | FAIL |
| combine | T0b'' (+ near-copy redraw) | 100 % | 83 % | 18 % | 0.3 % | PASS |
| fill | T0b'' (+ near-copy redraw) | 100 % | 95 % | 5 % | 0.8 % | PASS |
With splice, graft, line, pattern and offset (passed T0b), every operator passes. `results/t0b2_operators.json`,
`results/t0b3_operators.json`. `cut` made new through-openings in 13 of 38 legal children.
