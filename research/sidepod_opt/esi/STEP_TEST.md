# Step test: can the normal (ESI) adjoint steer a CFD-decided loop? (PROPOSED 2026-11-24, awaiting the owner)

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
