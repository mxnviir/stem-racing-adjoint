# Evolution + adjoint: tests (written before any of these solves, 2026-11-24 ~18:30 UTC; first launch 18:37)

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

## Round 1c (written before these solves): is the 0.5 mm gain shape, and does it survive the production scheme?
The base flow (and every 0.125 mm move) carries a slow drag oscillation (about +-0.9 mN, ~101-iteration cycle); all three
0.5 mm moves are steady (oscillation 0.01-0.03 mN). A switch of flow state could lower drag whatever the shape.
- `step_dafopp_05E`, `step_rnd1m_05E`: the opposite moves at 0.5 mm (explicit morph). **Mark S (shape, not state):**
  both opposite moves raise drag vs zero (change > 0). If either lowers drag, the 0.5 mm gains are not read as shape.
- `step_zero_P`, `step_daf_05EP`: base and DAFoam 0.5 mm under the production scheme (linearUpwind), 2000 iterations from
  the steady state. **Mark P:** D(daf_05EP) < D(zero_P) by >= 3 SE. Reported: the size ratio vs the steady model.

## Morph diagnostic 4: chained explicit morphs (run 45486612820, morph only)
Morph the mesh onto A (1 mm), then morph THAT mesh onto A + increment:
| A | increment | total peak | A | B |
|---|---|---|---|---|
| DAFoam 1.0 | rnd2 0.5 | 1.49 mm | acceptable (1 face skew 4.2) | **acceptable** (1 face skew 4.5) |
| DAFoam 1.0 | rnd2 1.0 | 1.98 mm | acceptable | **acceptable** (1 face skew 4.8) |
| DAFoam 1.0 | DAFoam 1.0 | 2.0 mm | acceptable | 1 inverted face |
| GUIDED 1.0 | rnd3 1.0 | 2.0 mm | acceptable (9 faces skew 5.2) | 7 inverted faces |
Chaining reaches 1.5-2 mm where one 2 mm morph never passed; it is not reliable at 2 mm. Larger totals: smaller
chained steps (untested) or a new mesh.

## Round 2 result (2026-11-24 22:26, run 45482339933): **H2 FAIL** (`hybrid/R2_VERDICT.txt`)
| run (0.125 mm, old morph; marked) | change (mN) | linear model |
|---|---|---|
| ES (span of 11 random probes only) | **-1.84** | -1.34 |
| GUIDED (randoms + DAFoam + ESI frozen/SST) | -1.40 | -1.74 |
| GUIDED-DAF | -1.45 | -1.58 |
| GUIDED-ESI | -1.77 | -1.50 |
| DAFoam alone (round 1) | -1.07 | |
- G1 not met: GUIDED is 0.43 mN *worse* than ES (3 SE 0.40). G2 not met: GUIDED vs DAFoam -0.34 (3 SE 0.38). At
  0.125 mm, adding the adjoint directions to evolution's own estimate did not help; every combined direction still
  beat the best single probe.
- Reported (explicit morph): GUIDED 0.5 mm **-5.24**, 1.0 mm -6.65; DAFoam 1.0 mm **-6.93** (best so far, 3.6 % of the
  half car; 0.5 -> 1.0 mm adds only -2.1: diminishing); ES 1.0 mm folded 2 cells (no result).
- Fresh DAFoam gradient at the 0.5 mm DAFoam design (run 45477836968): coarse drag 228.7 -> 218.2 mN; its predictions
  correlate 0.95 with the base gradient's, 0.74x the size. The 1.0 mm design's DAFoam job died in the adjoint (runner
  lost after 1.5 h; 1 of 4 runner DAFoam jobs so far).

## Round 3 = generation 2 (written before these solves)
Parent: DAFoam 1.0 mm (`daf@1.0`, -6.93). Children: the mesh is morphed onto the parent, then that mesh is morphed by
each child's 0.5 mm increment (chained, `hybrid/chain_solve.py`), warm start from the base flow, 1000 iterations:
`g2_zero` (the parent itself through the chained pipeline), `g2_daffresh` (DAFoam gradient at the 0.5 mm DAFoam design),
`g2_dafbase` (base DAFoam), `g2_esi`, `g2_guided`, `g2_es` (round-2 directions), `g2_rnd11`-`g2_rnd16`.
Predictions on record: `hybrid/pred_r3.json`.
- **Mark L (the loop keeps going):** the best child is below `g2_zero` by >= 3 SE.
- Reported: fresh vs base DAFoam guide; adjoint-guided children vs random/ES children; parent through the chained
  pipeline vs its from-base value (-6.93).

## Round 2b (written before these solves): the round-2 arms at 0.5 mm
`step_es_05E`, `step_guidedaf_05E`, `step_guidedesi_05E` (explicit morph), to set beside GUIDED 0.5 (-5.24) and
DAFoam 0.5 (-4.84). Reported, not marked (a post-result follow-up of H2). Predictions: `hybrid/pred_r2b.json`.
Round 1c, first result in (job log; the commit waits for the production runs): DAFoam's opposite at 0.5 mm **+4.05 mN**
(DAFoam itself -4.84): the 0.5 mm gain is shape, not a flow-state switch, along this direction.
- Round 3, first launch (run 45501421243): all 12 jobs failed in the morph, the parent's re-run included. Cause: the
  chained solve built the moves in the solve stage, where the workflow does not pass the smoothed-normal / clearance
  settings, so the 1 mm parent was built on raw normals (which fold at 1 mm). Fixed in `chain_solve.py`; relaunched
  unchanged otherwise (same candidates, same marks).
- Round 1c, second result (job log, D20 of the run record; the committed forces will give the 404-iteration mean):
  rnd1's opposite at 0.5 mm **+1.86 mN** (rnd1 itself -2.70). With DAFoam's opposite +4.05: **Mark S met** (both
  opposites raise drag): the 0.5 mm gains are shape, not a switch of flow state.

## Round 2b result (2026-11-25 00:07, run 45501709693; reported, not marked)
Every arm at 0.5 mm (explicit morph), change vs zero (mN): **GUIDED (evolution + DAFoam + ESI) -5.24**; GUIDED-DAF -5.03;
DAFoam alone -4.84; GUIDED-ESI -3.77; ESI alone -3.57; one random move -2.70; **ES (evolution only) -2.62**.
At 0.125 mm the order was the reverse (ES best, H2 FAIL). At the step size the loop actually uses, the combination of
evolution's measured directions with the adjoints removes twice what evolution alone does and 0.40 mN more than
DAFoam alone; ESI adds 0.2 mN on top of DAFoam. This is a post-result comparison (round 2b was written after H2's
verdict) and is reported as such; generation 2 and later test it prospectively.

## Generation 2 result (2026-11-25 00:37, run 45503888773): **Mark L met**
Parent (DAFoam 1.0 mm) through the chained pipeline: 183.803 (identical to its from-base run). Children, change vs the
parent (mN): **ESI 0.5 mm -1.28** (accepted; total vs the team pod **-8.21**, 4.3 % of the half car); combined -0.19;
DAFoam (gradient at the 0.5 mm design) +0.11; DAFoam (base gradient) -0.03; evolution-only +0.43; random moves -0.03 to
+1.73 (5 of 6 worse). 3 SE of every difference < 0.02 mN.
- DAFoam's direction is spent after 1 mm (its fresh gradient at the 1 mm design is 0.2x the base size along the old
  directions, r 0.83), and the next gain came from the other adjoint: the two adjoints pick up different features.
- Round 1c production pair (2000 iterations, linearUpwind): base 181.75 +/- 2.75, DAFoam 0.5 mm 177.65 +/- 3.14:
  difference -4.10, 3 SE 12.5: **Mark P not met** (the production flow's unsteadiness needs far longer averages; the
  sign and size agree with the steady model's -4.84, but that is not evidence at this precision).
- Mark S final (committed forces): DAFoam's opposite +4.05, rnd1's opposite +1.87: met.

## Generation 3 (written before these solves; `hybrid/loop.py next 3`, rules in its docstring)
Parent `daf@1.0|esi_frozen@0.5` (two chained levels). Children (0.5 mm unless noted): DAFoam (gradient at the 1 mm
design), ESI (base), combined and evolution-only directions from generation 2's measurements (0.5 and 0.25 mm),
random seeds 17-22. Mark L as before. A fresh DAFoam gradient at this parent runs alongside, for generation 4.

- **Amendment to the loop's acceptance rule (2026-11-25 00:45, before generation 3's results):** a child must also be
  >= 0.15 mN below the parent (at these designs 3 SE is ~0.007 mN, below the 0.14 mN two morphs of the same shape differ
  by, mark E). Generation 2's accepted child (-1.28) passes either way.
- **Mark P, post-hoc diagnostic (not a re-scoring):** both production histories are stationary from the start (ten
  200-iteration block means: base 181.2-182.5, DAFoam 0.5 mm 177.1-178.9) and decorrelate within ~5 iterations (std ~4
  mN). From the block means: base 181.81 +/- 0.12, DAFoam 0.5 mm 177.67 +/- 0.16, difference **-4.13 +/- 0.20** (steady
  model: -4.84). Mark P stays "not met" as written (its SE was fixed as the whole-signal one).

## Mark P2 (written before this solve): does the current best design hold up under the production scheme?
`step_best2_P`: the generation-3 parent (`daf@1.0|esi_frozen@0.5`, steady -8.21 mN), chained morph, production scheme
(linearUpwind), 2000 iterations from the base steady state, against `step_zero_P` (same pipeline). SE: from the ten
200-iteration block means (sd / sqrt 10). **Mark P2:** D(best2_P) < D(zero_P) by >= 3 SE. Reported: the ratio to the
steady model's -8.21.

## Generation 3 result (2026-11-25 02:26, run 45519631311): Mark L met
Parent (DAFoam 1.0 | ESI 0.5, chained) 182.521 (-8.209 vs the team pod). Children vs the parent (mN): **evolution-only
direction from generation 2's measurements, 0.25 mm: -0.273 (accepted; total -8.48)**; the combined direction 0.25 mm
-0.269; evolution-only 0.5 mm -0.139; random moves +0.05 .. +1.33 (all six worse). **Failed in the morph** (chained total
~2 mm): fresh DAFoam 0.5, ESI 0.5, combined 0.5. In this generation the gain came from evolution's recombination of
measured moves, not from an adjoint's own move.
- DAFoam gradient at this parent (run 45519631165): coarse drag 211.4 mN; its predictions no longer correlate with the
  base gradient's (r -0.24): the old directions are used up.
- **Amendment for generation 4 (before its launch):** moves of 0.25 mm (combinations 0.25 and 0.125), because every
  0.5 mm move along a strong direction folded the chained mesh in generation 3. Everything else as `loop.py`.
- **Fresh ESI at a moved design works** (run 45519814660): the generation-3 parent re-solved through the chained
  pipeline (D20 182.52, matching its generation-3 run), then ESI frozen (1000 its) on that converged morphed state:
  32 117 surface points; the job took ~2 h in all. Usable as a guide via `esinpz:` (generation 5 onward).

## Mark P2 result (2026-11-25 03:45, run 45520314673): **met**
Production scheme (linearUpwind), 2000 iterations, SE from ten 200-iteration block means: team pod 181.808 +/- 0.121,
best design (DAFoam 1.0 | ESI 0.5, chained) **175.487 +/- 0.060: -6.32 mN (3 SE 0.40), 3.5 % of the production half-car
drag**, 0.77 of the steady model's -8.21. The gain survives the production scheme (same mesh family; fresh-mesh and
repeat confirmation per D8 are still to do). `hybrid/P2_VERDICT.txt`.

## Generation 4 result (2026-11-25 04:31, run 45533175628): Mark L met
Parent 182.248 (-8.48). Children vs the parent (0.25 mm): **fresh DAFoam (gradient at the generation-3 parent) -1.016
(accepted; total -9.50 mN, 5.0 %)**; recombinations -0.16 .. -0.24; best random -0.20 (5 of 6 worse); base ESI folded.
The base DAFoam direction was spent after 1 mm; the gradient recomputed at the moved design found a new one.

## Generation 5 (written before these solves; loop.py rules, 0.25 mm as generation 4)
Parent: 4 chained levels (`loop_state.json`). Guides: DAFoam at the generation-4 parent (run 45533213960), ESI fresh at
the generation-3 parent (`esinpz:hybrid/esi_after/45519814660`). Mark L as before.
