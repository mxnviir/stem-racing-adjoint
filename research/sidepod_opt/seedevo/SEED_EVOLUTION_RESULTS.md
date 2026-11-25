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
