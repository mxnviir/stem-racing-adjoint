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

## TF The chosen configuration with the final operators (bench, instances 11-13, `results/tf_final.json`)
Means of the handed design (lower = better): evolution 3.318, random parents 3.794, mutation only 3.758, evolution +
end polish with trust check 3.005 (adjoint good) / 3.055 (adjoint misleading on open pods).
- **TFa FAIL as registered:** evolution beat random parents in 2, 5, 4 of 5 seeds and mutation-only in 4, 3, 5 of 5
  (instances 11, 12, 13): both >= 4 on only instance 13. On the means it is clearly ahead (0.44-0.48 better).
- **TFb PASS:** the end polish with the trust check beats evolution alone in 5, 3, 4 of 5 seeds.
- **TFc PASS:** with an adjoint misleading on open pods, no worse than evolution alone in 12 of 15 pairs.
Across the two held-out rounds of "evolution beats random parents and mutation-only" (T3a on 2-4 with amendment B:
PASS; TFa on 11-13 with the final operators: FAIL), the per-seed mark holds on 3 of 6 instances; on the mean it holds on
all 6 (T3a means 1.35/3.46/2.38 against 2.11/3.64/3.16 and 1.58/3.49/2.80).

## Reported, not marked (2026-11-26)
**Morph-scored small children (part of amendment B) on or off** (instances 2-4, seeds 1-5, final operators, means):
evolution 1.46 / 3.03 / 2.41 with, 1.60 / 3.16 / 2.29 without; evolve-then-polish 1.59 / 2.97 / 1.95 with, 1.27 / 2.73
/ 2.04 without. No consistent effect, so the first campaign driver scores every child on a fresh mesh.

**Campaign driver dry run** (`campaign.py`, `test_campaign.py`: batches of ~20 runs, results fed back between
batches, budget 300; instances 2-4, seeds 1-3): driver vs engine 1.60/1.82, 1.61/1.27, 2.04/1.45 (instance 2);
3.31/3.15, 3.33/3.34, 3.24/3.34 (3); 2.55/2.31, 2.40/2.62, 2.24/2.69 (4). Means 1.75/1.51, 3.29/3.28, 2.40/2.54: the
batch driver reaches the engine's level; 13-14 batches per 300 runs; no design lost; 0-3 duels open at the end.

## TS and TC2 The evolution branch's mechanisms, ported (bench, instances 14-16, `results/port_p{14,15,16}.json`)
- **TS PASS:** model-screened batches (GP + expected improvement + kriging believer, from the branch's layout search)
  beat plain evolution in **11 of 15** pairs (mark >= 11); means 4.209 vs 4.872, 2.184 vs 2.416, 5.902 vs 6.786 (best
  seeds of the instances are higher). Screening goes into the campaign configuration (the model only picks which
  children get CFD; every pick is CFD'd).
- **TC2 FAIL:** CMA-ES over a 6x2x3 lattice as the gradient-free polish beat random smooth moves in 7 of 15 (means
  4.824 vs 4.875, 2.433 vs 2.433, 6.820 vs 6.845): no gain at this budget. Kept in the code, off.

**Campaign driver with model screening (dry run, reported):** instances 2-4, seeds 1-3, budget 300: screened driver
2.06 / 1.05 / 1.85, 3.15 / 2.55 / 3.16, 1.49 / 2.14 / 2.02; means **1.65 / 2.95 / 1.88** against the unscreened driver's
1.76 / 3.29 / 2.40 and the engine's 1.51 / 3.28 / 2.54. The price: fewer niches held at the end (4-6 against 7-11):
the model concentrates the search on what it predicts well.

**TR, coarse DAFoam on the channel seed (gate run 45864447055):** failed. GMRES (restart 200, ILU fill 0 / level 1)
stalled: residual 4.2e-3 at 200, 8.9e-4 at 1000, 8.45e-4 at 2000 (tolerance 1e-6); flat for the last 1000. The
slotted seed's run was still falling when it hit the cap (2.8e-2 to 3.6e-5); this one is not, so the TR retry with more
iterations would not rescue it. Under the plan the channel seed's adjoint counts as refused (the design is refined
gradient-free). A different preconditioner would be a new decision, not taken.

**TR, coarse DAFoam on the original and window seeds (gate run 45864447055):** both runners were lost (18:58 and 18:59
UTC, after about 100 minutes in the adjoint step; no log, no artifact). Not a solver verdict. Re-run under the TR retry
rule (5000 GMRES iterations). For reference, the hybrid campaign's earlier DAFoam runs with these settings converged in
4 of 6 (hybrid/dafoam_actions/).
The first re-run (45881629527) never reached the solver: the OpenFOAM package mirror served truncated files ("File has
unexpected size ... Mirror sync in progress?") on all five install attempts, and the workflow went on without OpenFOAM.
All seedevo workflows now retry the install eight times and stop if OpenFOAM is missing. Re-launched.
The second re-run (45883073321) failed the same way on all eight attempts: every bad file came from one SourceForge
mirror (82.71.205.33), and the repo script sometimes came back as a web page. The workflows now install OpenFOAM with
.github/scripts/install_openfoam.sh: the seven v2412 (2412.260127-1) packages fetched from named mirrors in turn, each
kept only if its SHA-256 matches the openfoam.com repo index (checked), cached between jobs; the apt repo is the last
resort. Re-launched (attempt 3).

**TW campaign workflow plumbing (run 45870892378):**
- **W1 PASS.** Both cases rebuilt their design from the stored field, meshed fresh (2.12 M cells, y+ max 55.9 / 55.7),
  converged, returned a production drag; collect committed `campaign_test/results/gen_0/`.
- **W2 PASS after a fix.** As launched, `next` found nothing to breed from: the test campaign ranked on `steady` and the
  batch ran in mode `prod`. With the campaign's score set to `prod` (what TW specified), ingest + next wrote a legal
  batch 1: 20 new children (16 explore, 4 control), 7 operators, all distinct, 1 m 47 s on 2 workers. (This campaign
  predates seed hashing, so a child equal to a seed would not be caught here; new campaigns hash their seeds.)
- Reported, same design, frame 0, mean of the full 1000 iterations: team pod 180.72 campaign vs 179.07 gate; windowed
  pod 179.18 vs 179.24. With the start-up transient left out (iterations 200-1000, gate runs): 174.18 / 173.97 mN, block
  SE 0.10 / 0.19. See the campaign scoring amendment in the plan.

**TR retry, slotted seed (run 45875486505):** runner lost at 20:50 UTC after 2 h 22 min in the adjoint step (no log, no
artifact). That is the fourth lost runner during a coarse DAFoam adjoint today (original, window, slots twice counting
the first cap); the channel run is the only one that reached its end. Likeliest cause: memory (about 980 k adjoint states,
4 ranks, swap) on a standard runner, not shown without a log.

**TR retry, original and window seeds (run 45885388243):** original **converged** (1364 GMRES iterations, residual
2.6e-7 at 1000; 64 min of solver); its along/against probes launched on the gate's frame-0 steady state. Window: runner
lost again (21:35 UTC, about 108 min into the step). Coarse DAFoam on the four seeds today: 1 converged of 6 attempts
(channel stalled; four lost runners).

**Gate run 45864447055:** all 13 state jobs (production 1000 + steady 1200, fresh wall-resolved mesh) succeeded. All 20
probes failed or could not succeed: each probe job copied its design's DAFoam file even for moves that do not use it
(zero, two random), so a design without an adjoint lost every probe. Run cancelled to free runners. The zero and random
probes of all four seeds re-run through the retry workflow (DAFoam file only for moves that use it); the original seed's
along/against probes are running in 45899521794.

## T1 Instrument (gate run 45864447055; verdict from the 13 t1 artifacts, `t1_verdict.json`)
Fresh wall-resolved mesh per design and meshing frame (2.12 M cells), production 1000 iterations, then steady model 1200.
- **I1 PASS.** Wall layers on 59.6-62.0 % of wall faces, every design and frame (mark: >= 50 %).
- **I2, production: pooled mesh-to-mesh sigma 0.57 mN (9 dof) -> "single runs score".** Per design (mean, sd, n):
  team pod 179.54 / 0.37 / 4; channel 183.45 / 0.16 / 3; slotted 189.30 / 1.04 / 3; windowed 178.83 / 0.40 / 3.
- **I2, steady model: pooled sigma 1.42 mN (9 dof) -> "duel".** team 186.01 / 1.23; channel 186.43 / 1.52; slotted
  199.20 / 1.02; windowed 184.11 / 1.86.
- Reported, not marked: production on iterations 200-1000 (start-up left out), pooled sigma 0.63 mN; team 174.75,
  channel 178.67, slotted 184.25, windowed 173.50. Both models rank the four seeds alike (windowed < team < channel <
  slotted); the windowed pod is 0.7 mN under the team pod on production (about 1.2 sigma; not a claim).
- Consequence under the plan (the I2 rule): the campaign scores with **production**, single runs, and the steady
  continuation is not needed for scoring (it costs 1200 more iterations and is the noisier of the two).

**TR, original seed, along/against probes (run 45899521794), provisional until the zero probe is in:** 0.5 mm moves on
the converged coarse DAFoam gradient, explicit morph of the frame-0 steady state, steady model 1000 its, last 404:
along (dn) 184.43 mN, against (up) 190.47 mN; the unmoved frame-0 steady drag 187.07. DAFoam first-order prediction
(tr_predict): dn -7.50, up +7.50 mN. Measured from 187.07: dn -2.64, up +3.40; dn - up = -6.03 against -15.00 predicted
(ratio 0.40). Right sign both ways, about 40 % of the predicted size.

## TR Trust check on the real car (probes: runs 45899521794 and 45902612380 on the gate's frame-0 steady states; `verdict_t1_tr.json`)
0.5 mm moves, explicit morph, steady model 1000 its, last 404 (same-mesh SE 0.0001-0.06 mN, so the 0.15 mN floor sets the
margin). Drag change from each seed's own zero-move probe, mN:

| seed | zero (mN) | along DAFoam (dn) | against (up) | random 101 | random 102 | DAFoam |
|---|---|---|---|---|---|---|
| team pod | 187.07 | **-2.64** | +3.39 | +0.03 | -0.30 | converged (retry) |
| channel | 187.13 | - | - | -1.20 | -1.72 | stalled at 8.4e-4 |
| slotted | 199.00 | - | - | -0.46 | -0.83 | runner lost twice |
| windowed | 185.07 | - | - | -0.11 | -0.29 | runner lost twice |

- **TR1 PASS.** Team pod trusted: dn - zero = -2.64, dn - up = -6.03 (margin 0.15).
- **TR2 FAIL**, but not on evidence against the gradient: none of the three new seeds got a DAFoam gradient to test
  (one stalled, two lost their runners twice). Coarse DAFoam on these seeds: 1 converged of 6 attempts.
- **TR3 PASS** (1 of 1): dn below both random moves (-2.64 against +0.03 / -0.30).
- Reported: DAFoam predicted dn -7.50 / up +7.50 mN; measured -2.64 / +3.39 (ratio 0.35 / 0.45). Right sign, about 40 %
  of the size: the gradient points the right way and overstates the gain, as in the hybrid loop.
- Reported: both random moves lowered drag on all three new seeds (0.1-1.7 mN), and the channel seed's by more than its
  zero-to-dn would need to beat. On the same mesh the explicit morph itself may carry a small downward bias; to be
  checked before any campaign result leans on a sub-2 mN morph gain (campaign scores use fresh meshes, so it does
  not touch them).
- **What it decides (as registered):** TR2 fails -> the end polish on shapes unlike the team pod is gradient-free, and
  the adjoint is used only where its own per-design check passes.

**Owner, 2026-11-27:** campaign POC approved; DAFoam lost runners: option B (one retry with fewer MPI ranks and a
smaller GMRES restart); channel seed's adjoint left refused; the probe/polish step stays at 0.5 mm for now (to be tuned
later), no runs spent on the morph-bias check yet. Launched: DAFoam on slotted and windowed seeds, 2 ranks, GMRES
restart 100, 5000 iterations, memory logged every minute.

**POC batch 1 (run 45937827424):** design 5 failed its rebuild on the runner (thin foam 34 mm3); the same happens here:
the field was stored as float16 and surface voxels moved on reload. 19 of 20 cases go ahead. From batch 2 on, fields
are stored as float32 and every child is rebuilt from storage before it is accepted (a child that changes or fails
is dropped).
Checked on a copy of the POC campaign: `next` wrote a full batch of 20 in 524 s (3 workers; the storage rebuild is
serial), and the four children spot-checked rebuild legal from storage. (A first version also demanded an identical
shape on rebuild; the build is not bit-idempotent, so it rejected nearly every child and was replaced before any batch
used it.)

**DAFoam option B (2 ranks, GMRES restart 100; run 45937335294):** windowed seed: runner lost again at 06:30 UTC,
about 2 h 24 min into the step (no log, no artifact, so no memory log either). Third loss for this seed. Slotted seed
still running.

## POC campaign, batch 1 (run 45937827424)
- 19 of 20 cases converged (design 5: storage bug, fixed). The collect job failed before committing: it installed
  system libraries without `apt-get update`, and Ubuntu had replaced one package (404). Results taken from the run's
  artifacts, ingested and batch 2 written here; collect now updates apt with retries. **P1 as registered fails**
  (batch 1 needed a manual hand-over); batch 2's hand-over is the re-test.
- Best seed: windowed pod 173.50 mN (mean of 3 frames). Children, production 200-1000, frame 0, lowest first:
  d7 offset(window) **170.11** (-3.39), d10 bump(window) 171.17 (-2.33), d11 combine(window, team) 172.96, d13
  splice(window, team) 174.63, d19 pattern(window) 174.73; worst: two `fill` children 221 / 228 (fill closes openings).
- Archive after batch 1: 6 niches (P2's mark is >= 3). Duels opened by the driver: d10 vs window, d13 vs team.
- d7 is 3.39 mN under the best seed, past the 1.6 mN bar; it took an empty niche, so the driver set no re-run. Per P3
  a claim needs a second meshing frame: d7 on frame 1 added to batch 2 by hand.
Slotted seed, option B: the runner survived (memory 13.4 GB used of about 16, swap 0.1 GB at the end) but GMRES with
restart 100 stalled: 1.53e-2 at 200 iterations, 1.024e-2 from 1000 to 5000 (reason -3). Restart 200 had reached 3.6e-5
before. So fewer ranks keep the runner alive and the shorter restart stops convergence. As decided (option B, then
C), the slotted and windowed seeds are polished gradient-free; the adjoint stays on shapes near the team pod.

**POC d7, how it differs (renders in `campaign_poc/renders/`):** the `offset` operator grew the whole window pod's
surface out by 0.72 mm (26 % of the body's faces moved > 0.3 mm, none moved in), which closed the side window
(through-openings 1 -> 0) and raised the pod volume from 65.7 to 79.2 cm3. Why that lowers drag is not known; the
frame-1 re-run in batch 2 decides whether the 3.4 mN is real.

**POC batch 1 counted in race time, not drag alone (found 2026-11-27):** the campaign scores drag only, and the
ballast absorbs added foam only while lead is left. The seeds carry 0-0.2 g of lead, so a child that adds foam ends
over the 48.0 g the others are ballasted to. d7 (offset +0.72 mm, +13.5 cm3) weighs 49.52 g with no lead: at the
project's rates (0.18 ms per whole-car mN, 7.5 ms per g) its -3.39 mN half-car drag is -1.2 ms and its +1.52 g is
+11.4 ms: **about 10 ms slower** than the window seed. In race time the best child of batch 1 is d10 (bump, -2.33 mN,
+0.05 g: about -0.5 ms), then d11 (-0.2 ms); every other child is slower than the window seed. The campaign's score
has to be race time (or the mass rule a hard limit) before a real campaign; not changed yet (owner's decision).

## POC campaign verdict (batches 1-2; runs 45937827424, 45955823913; drag scoring, as the owner asked)
- **P1 FAIL as registered**, for batch 1 only: its hand-over needed a manual step (apt 404 in collect). Batch 2 ran,
  committed, ingested and stopped at `max_gen` 2 with no manual step (STOP written by the collect job). Convergence
  42 of 43 child runs (98 %; the one failure was the float16 storage bug, fixed).
- **P2 PASS:** 7 niches held at the end (mark >= 3).
- **P3 (reported):** best seed: windowed pod 173.50 mN (3 meshing frames). Two children beat it on two frames each:
  **d7** (offset +0.72 mm of the windowed pod, window closed) 170.11 / 171.44, mean **170.77 (-2.72 mN)**; **d10** (bump
  on the windowed pod) 171.17 / 171.65, mean **171.41 (-2.09 mN)**. SE of a 2-run vs 3-run mean difference is
  0.57 x sqrt(1/2 + 1/3) = 0.52 mN, so 5.2 and 4.0 SE, past the 1.6 mN bar. d13 (splice) 174.19, not better.
  Single-run children under the best seed: d36 171.51, d27 171.66, d34 171.93, d24 172.02, d38 172.34 (all from d7),
  d11 172.96.
- Reported: explore children under the best seed: batch 1 3 of 16, batch 2 (model-screened) 6 of 16; control
  children: 0 of 8. Every child under the best seed descends from the windowed pod.
- Caveats: one wall-resolved mesh size (2.1 M cells): the next check is the fine mesh. d7 is 1.5 g over the 48 g
  ballast target (race time is not the score for now, owner's choice). Four seeds only; the channel seed lost its
  archive place to the team pod in batch 1 and got children only as a control parent.

## Approval test: census (run 46019374824)
All 14 organic seeds converged and every one has more drag than the team pod (174.75 mN, 4 frames): worley1 185.51,
cppn2 194.36, cppn1 194.50, snake1 195.62, worley2 197.81, gyroid2 200.80, teardrop1 205.47, lumpy1 209.63,
snake2 210.22, lumpy2 211.59, teardrop2 215.80, blobs2 215.96, gyroid1 216.31, blobs1 218.78 (one frame each). None
kept a through-opening after the rules. Batch 1 (24 cases) was written and started by the collect job unattended;
`every_seed_once` gave each of the 15 seeds an explore child (team pod 2).
