# Evolution + adjoint: tests (written before any of these solves, 2026-11-24 ~19:30 UTC)

The owner asked (2026-11-24): a tested plan for combining evolution with both adjoints (discrete DAFoam and normal
ESI) to make the most aerodynamic sidepod; aerodynamics only for now (fewer constraints). This reverses the owner's
"no DAFoam at all" of this morning for this purpose (logged in DECISIONS D9). DAFoam runs only on GitHub Actions or on
coarse data already on the branch; fine-mesh DAFoam (rented machine) still needs the owner's OK on cost.

Everything below is on the wall-resolved mesh, the 2026-11-24 step-test setup: the tested mesh morphed onto each
candidate (strict, no fresh mesh), warm start, 1000 steady upwind iterations, one GitHub runner per candidate.

## Why these tests (evidence already on the branch)
- Step test (esi/STEP_TEST.md): ESI's direction is right in sign but no better than a blind smooth move.
- Retrospective, post hoc (not a mark): the coarse DAFoam gradient (validated on coarse only) predicts the 8 moves
  measured on the resolved mesh with r 0.82, slope 1.15, signs 7/8 (esi/sst/opp are one direction, so ~6
  independent, 5/6 signs). Its largest miss: rnd1 (predicted -0.28, measured -1.04): it ranks the ESI step above
  rnd1, the opposite of CFD. ESI: r 0.30-0.57, signs 3/5 on moves not built from itself.
- Free parallelism: the repository is public, so runners cost nothing and up to ~20 run at once. The binding budget
  is rounds (~2 h each), not solves. Exploration samples in the same round cost no extra time.

## Round 1 (H1): is the coarse DAFoam direction a better step than luck on the good mesh?
Candidates (`esi/make_step.py`, all peak 0.125 mm, same normalisation as the step test):

| name | field | role |
|---|---|---|
| `step_daf_q` | downhill along coarse DAFoam (exact transpose of `dafoam/judge.py`'s mapping, per area, smoothed 4.5 mm) | the proposer |
| `step_dafopp_q` | its negative | uphill control |
| `step_rnd3_q` .. `step_rnd10_q` | random smooth fields, seeds 3-10 | 8 more blind steps (10 with rnd1, rnd2) |
| `step_rnd1m_q` | -rnd1 | linearity: expect about +1.04 |
| `step_rnd1h_q` | rnd1 at 0.0625 mm | linearity: expect about -0.52 |
| `step_zero_r` | no move | run-to-run repeat of `step_zero` |

Predictions on record before launch: `hybrid/pred_r1.json` (coarse DAFoam, coarse ESI, resolved ESI; peak, RMS,
volume). The DAFoam step is predicted at -2.17 mN, the random steps at -0.18 .. +0.44.

Measured drag: mean of the last 404 iterations. **SE: each run's whole-signal `force_mean_stderr`** (the stricter of
the two estimators). A difference is "by >= 3 SE" when it exceeds 3*hypot(SE_a, SE_b).

Marks (fixed now):
- **M1:** D(daf) < D(zero) by >= 3 SE.
- **M2:** D(daf) < D(dafopp) by >= 3 SE.
- **M3:** D(daf) below every random step at 0.125 mm (rnd1-rnd10 that morphed; ranking only). By luck: ~1/11.
- **PASS = M1 and M2 and M3.**
- **F (fidelity, marked separately):** over the new moves at 0.125 mm (daf, dafopp, rnd3-10, rnd1m), Pearson r between
  measured and coarse-DAFoam predicted >= 0.7 and signs >= 80 %.
- Fold rule: a random seed that folds is dropped and reported (no replacement). If daf or dafopp folds, H1 is
  INVALID and is re-run at 0.0625 mm.
- Reported, not marked: per-RMS drops (the random fields move ~43 % more RMS at the same peak), linearity, the
  zero repeat, ESI's prospective fidelity.

What it decides: PASS and F -> coarse DAFoam is the main guide in the loop. FAIL -> it is one guide among the random
directions, weighted by its measured alignment (round 2 measures that either way).

## Round 2 (H2, design fixed now; directions computed from round-1 data by a committed script before launch)
Every measured move (step test and round 1) is a directional measurement: drag change dF_i along field d_i. Under
the linear regime (checked by rnd1m, rnd1h), the steepest descent inside the span of measured directions is
c* = -M^-1 dF (M: area-weighted Gram matrix of the d_i, ridge 1e-3 of its trace), w = sum c_i d_i, then the same
taper / mean / p95 / clip / 0.125 mm as every step. Arms:
- **ES** (evolution only): span of the random directions.
- **GUIDED** (evolution + both adjoints): span of the random directions + daf + ESI frozen + ESI SST.
- **GUIDED-DAF** (evolution + discrete only), **GUIDED-ESI** (evolution + normal only): ablations.
- **DAF** (adjoint only): the round-1 `step_daf_q`.
Marks: **G1** D(GUIDED) < D(ES) by >= 3 SE; **G2** D(GUIDED) < D(DAF) by >= 3 SE; **PASS = G1 and G2**: combining
beats either alone per step. In the loop every round spends one batch on both exploration (pairs) and the step,
so per step = per round. Reported: ablations; GUIDED at larger peaks if the morph test below allows them.

## Larger steps (morph), diagnostic only
Folds at >= 0.25 mm sit on the pod's sharp edges. Hypothesis: there the morph's nearest-point surface change and the
raw vertex normals jump. Test: morph-only checks of the same fields at 0.25 / 0.5 / 1 mm with the car-patch points
moved directly by the smooth field (env flag, default unchanged), then one re-solve of `step_rnd1_q` under the new
morph to check that it reproduces -1.04 mN.

## Morph diagnostics (2026-11-24 18:40-19:07, morph-only, no solves)
- Run 45461955558: direct-field morph (car points moved by the design's smooth field instead of the STL-to-STL
  nearest-point change), smoothed normals, sharp-edge mask: **all fold at >= 0.5 mm**. Bad cells sit in the wall layer
  2-12 mm from sharp edges, so the edges were not the cause; the Laplacian mesh motion is.
- Run 45465008793: **explicit morph** (`P2_MORPH_EXPLICIT=1`, no Laplacian solve: every point within 0.5 mm of the car
  moves exactly with it, the move fades to zero at 5 mm, and linearly to zero towards any other boundary), with the
  direct field and 1.5 mm smoothed normals: rnd2 at 0.5 mm **Mesh OK** (the old morph folded it at 0.25 mm); at 1.0 mm
  rnd2 and daf leave 1 face at skewness 4.0-4.2 (inside the existing acceptance rule: <= 10 faces, skew <= 8), ESI
  25 faces at 5.9 (outside it); at 2.0 mm rnd2 folds (~1000 cells; the pod's underside reaches the ground there).

## Round 1b (written before these solves): does the explicit morph agree, and do larger steps pay?
| name | move | morph |
|---|---|---|
| `step_rnd1_qE` | rnd1, 0.125 mm, raw normals (the same STL as `step_rnd1_q`) | explicit, STL surface change |
| `step_rnd1_qD` | rnd1, 0.125 mm, 1.5 mm smoothed normals | explicit, direct field |
| `step_rnd1_05E` | rnd1, 0.5 mm | explicit, direct field |
| `step_daf_05E`, `step_daf_10E` | DAFoam downhill, 0.5 / 1.0 mm | explicit, direct field |
| `step_esi_05E` | ESI downhill, 0.5 mm | explicit, direct field |
Predictions on record: `hybrid/pred_r1b.json` (linear; raw normals): daf -8.7 / -17.4 mN (coarse DAFoam), rnd1 0.5 mm -1.1,
ESI 0.5 mm -2.7 (coarse DAFoam) / -1.6 (resolved ESI). Linear scaling of the measured 0.125 mm results gives rnd1 -4.2.
- **Mark E (the new morph reads the same):** |D(rnd1_qE) - D(rnd1_q)| <= 3 SE.
- Reported: drag vs step size along each direction (is the response linear to 1 mm; where does it bend?).

## DAFoam on a GitHub runner (smoke test, run 45462436057, 2026-11-24 18:42-20:08)
Fresh coarse mesh + steady upwind state from the exact CAD (5000 its, 18 min, D 228.76 mN vs stored 228.72), then DAFoam
Krylov (PC fill 0, level 1) in Docker on the 16 GB runner with 16 GB swap: primal 63 s, adjoint 59 min. Against the stored
coarse gradient: point cosine 0.9985; predictions for the 18 round-1 moves r 0.999999, slope 0.998. **Passed: a fresh
coarse DAFoam gradient for any design costs ~1.5 h on a free runner.**

## Round 1 result (2026-11-24 20:32, run 45461604257): **H1 PASS, F met** (`hybrid/R1_VERDICT.txt`)
- DAFoam step -1.066 mN, its opposite +0.903 (M1, M2 met by > 3 SE); below all 10 random steps (M3 met, but only
  0.023 mN below the best, rnd1 -1.043; the random steps spread -1.04 .. +0.41, mean -0.06).
- Fidelity (11 new moves): coarse DAFoam r 0.85, signs 10/11, **size about 2x too large** (slope 0.48); resolved ESI
  r 0.67, signs 7/11, size 4x too small; coarse ESI r 0.81, signs 7/11, 7x too small.
- Per RMS move: DAFoam -25.9 mN/mm, best random -17.7.
- Repeat: zero_r +0.0003 (the pipeline is deterministic). Linearity: rnd1 -1.04, -rnd1 +0.47, rnd1/2 -0.36 (a curved
  response along rnd1: about -0.29 of curvature at this size); DAFoam nearly linear (-1.07 / +0.90).

## Round 2 as launched (directions from `hybrid/r2_build.py`, 16 measured moves; before any round-2 solve)
Linear-model values at 0.125 mm (`hybrid/r2/combine.json`): ES -1.34, GUIDED -1.74, GUIDED-DAF -1.58, GUIDED-ESI -1.50
(DAFoam alone measured -1.07). Marked runs as written above (0.125 mm, old morph). Reported: GUIDED at 0.5 and 1.0 mm,
ES at 1.0 mm, DAFoam at 1.0 mm again (all explicit morph, smoothed normals, 1.5 mm ground clearance; DAFoam 1.0 mm
re-run because the strict rule refused its one skewed face in round 1b). Verdict script: `hybrid/r2_verdict.py`.

## Round 1b result (2026-11-24 20:54, run 45467103535)
| run | change vs zero (mN) | linear from its 0.125 mm result | coarse DAFoam predicted |
|---|---|---|---|
| `step_rnd1_qE` (explicit morph, same STL as rnd1_q) | -1.18 | (rnd1_q -1.04) | -0.28 |
| `step_rnd1_qD` (explicit, direct field, smoothed normals) | -1.30 | | -0.28 |
| `step_daf_05E` (DAFoam, 0.5 mm) | **-4.84** | -4.26 | -8.68 |
| `step_esi_05E` (ESI, 0.5 mm) | -3.57 | -2.58 | -2.67 |
| `step_rnd1_05E` (rnd1, 0.5 mm) | -2.70 | -4.17 | -1.11 |
| `step_daf_10E` | refused by the strict rule (1 skewed face), re-run in round 2 | | |
- **Mark E met:** the explicit morph reads the same as the old morph at 0.125 mm (-1.18 vs -1.04, 3 SE 0.51).
- Steps of 0.5 mm pay 2.5-5 mN (1.4-2.5 % of the half car); DAFoam's direction stays the best, and scales slightly
  better than linear; the random direction scales worse than linear (its curvature, seen in round 1).
- The 0.5 mm explicit runs have a whole-signal SE of 0.001-0.003 mN (a steadier flow than the base's 0.13).
- Diagnostic 3 (morph only, run 45482441995): with 1.5 mm ground clearance, 1.5 and 2 mm moves still fold a few cells
  (2-24) for every direction: **one morph from a mesh reaches about 1 mm**. Larger total changes need chained morphs
  (each generation morphs its parent's mesh) or a new mesh.
