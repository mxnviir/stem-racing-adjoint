# Step test: can the normal (ESI) adjoint steer a CFD-decided loop? (approved by the owner 2026-11-24, before any step was built)

Written before any step is built or solved. Nothing here changes D9: the normal adjoint failed its accuracy
test (2026-11-24) and stays failed as a gradient. This tests a different use of it, and a different method.

## Why
- The owner rules out the discrete adjoint (DAFoam) entirely and wants the normal adjoint, with larger changes.
- The loop never needed an accurate gradient: every step is built, CFD'd and accepted only if race time
  improves (`shape_loop.py` v2). It needs a direction that lowers drag more often and more strongly than a
  blind guess. The step size is then chosen by CFD, not by the adjoint, so steps can be large.
- Coarse-mesh evidence (ROUTES 2026-11-24 entry), with DAFoam's validated gradient as the reference: pod
  region, mean removed (volume-neutral), loop-style step (p95-normalised, clipped):

  | smoothing | ESI vs reference, centred cos | 95th pct of 200 random smooth fields | ESI step gain (of the best step) | random p95 gain |
  |---|---|---|---|---|
  | 4.5 mm | 0.34 | 0.14 | 0.20 | 0.10 |
  | 10 mm | 0.42 | 0.39 | 0.13 | 0.08 |

  So on coarse, ESI's 4.5 mm-smoothed direction carries real but modest information: about twice a lucky
  random field, a fifth of a good gradient. Heavier smoothing does not help (random fields catch up).
- Not known: whether this holds on a good mesh. The smoothed wall-resolved ESI map correlates only
  0.25 with the coarse reference, and the measured bump effects themselves change between meshes. Hence
  this test, on the wall-resolved mesh, with controls.

## Test (wall-resolved mesh, team pod, everything reused from the 2026-11-24 bump runs)
- **Direction:** the existing wall-resolved ESI frozen sensitivity (`gate_results_resolved_up/esi/esi_sens_frozen.npz`),
  outward normal, on the sidepod region (x 0.07–0.20 m, y > 0.012 m), Gaussian smoothing σ = 4.5 mm (area-weighted),
  mean removed (volume-neutral), divided by its 95th percentile of |value|, clipped to ±1, times the amplitude A.
  Applied to `gate/original_rm/car_half.stl` along vertex normals, fading to zero outside the region.
- **Candidates (7):**

  | name | field | A |
  |---|---|---|
  | `step_zero` | no move (same pipeline; the base) | 0 |
  | `step_esi_a05` | −ESI frozen (downhill) | 0.5 mm |
  | `step_esi_a10` | −ESI frozen | 1.0 mm |
  | `step_sst_a05` | −ESI SST | 0.5 mm |
  | `step_opp_a05` | +ESI frozen (uphill control) | 0.5 mm |
  | `step_rnd1_a05`, `step_rnd2_a05` | random smooth fields, numpy seeds 1 and 2, same smoothing and normalisation | 0.5 mm |

- **Order:** morph-only check of all candidates first (free, GitHub Actions). Rule, fixed now: a candidate that
  folds is re-made at half its A (once); if it still folds, it is dropped and reported. Then the solves: same
  settings as the 2026-11-24 bumps (steady model, warm copy, 1000 iterations, GitHub Actions in parallel).
- **Measured drag:** mean of the last 404 iterations; SE from four 101-iteration block means (as the amendment).

## Pass marks (fixed before any result)
- **M1, downhill:** D(`step_esi_a05`) < D(`step_zero`) by ≥ 3 SE.
- **M2, beats the uphill control:** D(`step_esi_a05`) < D(`step_opp_a05`) by ≥ 3 SE.
- **M3, beats luck:** D(`step_esi_a05`) < min(D(`step_rnd1_a05`), D(`step_rnd2_a05`)) by ≥ 3 SE.
- **PASS = M1 and M2 and M3.** Reported, not marked: `step_esi_a10` vs `step_esi_a05` (does a bigger step
  help?), SST vs frozen.
- **If PASS:** the loop runs "adjoint-proposed, CFD-decided": each iteration a fan of step sizes along the
  smoothed ESI direction, all CFD'd in parallel, the best accepted if it beats the current design by
  ≥ 3 SE; an opposite-direction control in the first iterations; scored and confirmed per D8.
- **If FAIL:** the normal adjoint gives no usable direction on a good mesh. The fallback is a search that
  needs no gradient: every proposal is CFD'd and the method uses no adjoint.

## Built (2026-11-24, before any morph or solve; `esi/make_step.py`)
| candidate | moved > 0.1 mm (of region) | RMS move (moved region) | volume change |
|---|---|---|---|
| `step_esi_a05` | 38 % | 0.158 mm | +110 mm³ |
| `step_esi_a10` | 74 % | 0.316 mm | +250 mm³ |
| `step_sst_a05` | 50 % | 0.161 mm | +152 mm³ |
| `step_opp_a05` | 38 % | 0.158 mm | −78 mm³ |
| `step_rnd1_a05` / `step_rnd2_a05` | 69 % / 67 % | 0.215 / 0.210 mm | +24 / +8 mm³ |

- The volume is only first-order neutral: the mean is removed before the clip (as fixed above) and the ESI field is
  heavy-tailed, so clipping is lopsided. All changes are < 0.4 % of the 67 cm³ pod.
- At the same peak move, the random controls move ~35 % more surface (RMS) than the ESI steps, because the ESI field
  is spikier. Noted, not corrected: the normalisation was fixed before building.

## Morph checks (2026-11-24, no solves yet)
| candidate | at the registered A | at half A (fold rule) | at a common 0.125 mm (diagnostic) |
|---|---|---|---|
| `step_zero` | Mesh OK | | |
| `step_esi` | 0.5: 4 bad cells | 0.25: **Mesh OK** | Mesh OK |
| `step_esi_a10` | 1.0: 76 bad cells | 0.5: 4 bad cells -> dropped | |
| `step_sst` | 0.5: 4 bad cells | 0.25: **Mesh OK** | Mesh OK |
| `step_opp` | 0.5: 13 bad cells | 0.25: 2 bad cells -> dropped | Mesh OK |
| `step_rnd1` | 0.5: 6 bad cells | 0.25: **Mesh OK** | Mesh OK |
| `step_rnd2` | 0.5: 20 bad cells | 0.25: 6 faces -> dropped | Mesh OK |

Runs 45386092002, 45387356849, 45389614783. The folds sit in the 15 um wall layer, along the pod's sharp edges (top edge
z ~ 27 mm, front edge x ~ 88 mm, near the ground). Under the fold rule, the uphill control and one random control
are dropped, so M2 and M3 cannot be evaluated and the verdict as written would be INVALID. Amendment **approved by the owner 2026-11-24, before any solve**: every moving candidate at a common 0.125 mm
(`step_esi_q`, `step_sst_q`, `step_opp_q`, `step_rnd1_q`, `step_rnd2_q`) plus `step_zero`; marks unchanged; the 1.0 mm
comparison is dropped. `esi/step_verdict.py` reads the `_q` runs.

## Result (2026-11-24, Actions run 45391021727): **FAIL** (M1 met, M2 met, M3 not met)
All six runs converged on the morphed mesh (no fallback). Half-car drag, mN, mean of the last 404 iterations, SE from four
101-iteration blocks (`gate_results_resolved_up/esi/STEP_VERDICT.txt`):

| run (all moving at 0.125 mm) | drag | change vs zero |
|---|---|---|
| `step_zero` | 190.730 ± 0.000 | — |
| `step_esi_q` (−ESI frozen) | 190.086 ± 0.002 | **−0.644** |
| `step_sst_q` (−ESI SST, reported) | 190.117 ± 0.002 | −0.613 |
| `step_opp_q` (+ESI frozen, uphill) | 191.254 ± 0.002 | +0.524 |
| `step_rnd1_q` (random, seed 1) | 189.687 ± 0.002 | **−1.043** |
| `step_rnd2_q` (random, seed 2) | 191.138 ± 0.000 | +0.408 |

- M1 met (−0.644 mN, 3 SE 0.005). M2 met (−1.168 mN vs uphill, 3 SE 0.007). M3 **not met**: random seed 1 is
  0.398 mN lower than the ESI step (3 SE 0.008). Verdict FAIL, as the marks were written.
- What it shows (not marked): the ESI direction does carry the right sign at this broad scale. Downhill lowers drag,
  uphill raises it by a similar amount (−0.64 / +0.52), and the frozen and SST maps agree (0.03 mN apart). But it is
  not better than a blind smooth move: the two random fields gave −1.04 and +0.41, so the ESI step sits inside the
  random spread. The random fields move ~35 % more surface (RMS, noted before the runs); per unit RMS move seed 1 is
  still ahead (−19 vs −16 mN/mm). Two random draws cannot rank ESI among random fields; they only show it is not
  clearly better, which is what M3 tested.
- Block SE (≤ 0.002 mN) is iteration noise on a shared morphed mesh. The runs' own whole-signal SE is ~0.11–0.15 mN;
  every difference above except SST vs ESI clears 3 × that too.
- Per the plan above: the normal adjoint gives no direction better than luck on a good mesh. The fallback is a
  search that needs no gradient, every proposal CFD'd, no adjoint.
