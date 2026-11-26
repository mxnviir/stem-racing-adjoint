# Seed evolution: architecture, research and the tests that would prove or kill it

Written 2026-11-25; **version 2 the same day: the adjoint is inside the loop (section 5b), the engine is
built (`seedevo/`), and the no-CFD tests and a coarse-CFD plumbing test are run on this machine** (results:
`SEED_EVOLUTION_RESULTS.md`). Every pass mark below is fixed in this file, and committed, before the result
it judges exists (DECISIONS D12); amendments made before a run are marked as such. Paths are relative to
`research/sidepod_opt/`.

**Goal:** new sidepod geometry (not a polished copy of one pod) by evolving a population bred from many
different seed pods, every candidate legal and millable, every candidate scored by real CFD, with the adjoint working
on the population's best members all the way through (not only as a polish at the end).

## 1. The answer to "CPPN or something?"

**No CPPN as the genome. The genome is the shape itself:** the solid/air field on the 1 mm grid that
`geometry.py` and `shape_loop.build_design` already use. Variation is done by geometric operators on
fields (section 4). A CPPN-style pattern generator is kept as **one mutation operator**, because it is good
at one thing we want: regular arrays of slots, ribs and windows.

| Option | For | Against, here | Decision |
|---|---|---|---|
| **Field as genome, geometric operators** | Any seed loads directly (STEP -> field). Any topology. No shape parameters (D3). Children look like their parents by construction | Operators have to be written and proven (tests T0b, T2) | **Chosen** |
| CPPN-NEAT as genome (`methods.py` `neat`) | Natural ribs and windows; resolution-free | A seed cannot be stored as a CPPN, only fed in as a distance input (Clune, Chen, Lipson 2013), so one network modifies one seed. The repo's own probe (`organic_feasibility/results3d/herit.json`): 27 of 40 mutations changed nothing at all and the rest changed the body by up to 48 %: poor locality. Never run at the real Reynolds number | Operator only (M4) |
| Lattice + CMA-ES (`methods.py` `cma`) | Built and run | 72 numbers bulging a smooth blob, control points 10-18 mm apart: no ribs or windows. One seed only. The SimScale run: generation 0 was 20 ms slower than its seed, the best of 96 cars was still 2.6 ms behind it, the mill put back a median 16.6 cm3 per car (pod 67 cm3) | Dropped |
| Learned latent space (VAE on the seeds; "data-driven topology design", Yamasaki, Yaji, Fujita) | Published for turbulent problems where adjoint topology optimisation fails; crossover in latent space | Needs a few hundred legal shapes to train; interpolates, does not extrapolate (Hagg et al. 2021: prefer an explicit encoding to a learned one when one exists); a build in itself | Optional operator X5 once the archive holds >= 200 legal designs; tested as an arm, not assumed |
| Hybrid loop alone (`hybrid/loop.py`) | The one method here with a second-model-confirmed gain | Fixed topology, 4.5 mm smoothing, volume-neutral, ~2 mm per mesh, one seed | The polisher at the end (stage 6) |

## 2. Research this rests on

| Idea | Source | What we take | What does not carry over |
|---|---|---|---|
| Keep the best design in every niche of a map, not one winner (MAP-Elites) | Mouret and Clune 2015 | The archive (section 5): no path has to improve step by step, so a worse-first route (a valley) does not block it | Usually run with 10^4-10^6 cheap evaluations; we have a few hundred |
| Quality diversity with real aerodynamics | Gaier, Asteroth, Mouret 2018 (SAIL; 2D airfoils and 3D aerodynamic cases) | Proof the map idea works on flow problems | SAIL needs a Gaussian-process predictor to pick candidates: excluded here (D4), so we pay with fewer niches |
| Noisy scores in a map | Justesen, Risi, Mouret 2019 (adaptive sampling); Flageat and Cully 2020, 2023 | Re-evaluate only a challenger and the incumbent it would replace (section 5) | Their noise is cheap to re-sample; ours costs a CFD run |
| Variation along the line between two elites | Vassiliades and Mouret 2018 (directional variation) | Operator X4 | Defined for vectors; here applied to signed-distance fields |
| A population of material layouts, crossover by a generative model, high-fidelity scoring, no gradients | Yamasaki, Yaji, Fujita 2021; Yaji et al. (multifidelity); Kii et al. 2024 (latent crossover); Fujita group 2025 (turbulent pipes) | The overall shape of the method: seeds in, select, recombine, re-score with the real solver. The closest published relative | Their seeds come from cheap topology optimisation and their crossover is a trained VAE; internal flows |
| Seeding a generative encoding with an existing object | Clune, Chen, Lipson 2013 | Why a CPPN cannot hold many seeds at once | - |
| Milling as a filter inside the design step | Langelaar 2019; Morris et al. 2020 | Every child passes the mill and wall rules before it exists (already in `build_design`) | Their filters are differentiable; ours is a hard rule |
| A representation must have locality: small change in, small change out | Rothlauf (locality); Jones and Forrest 1995 (fitness-distance correlation) | Tests T0b and T2: measured before any search is trusted | - |
| Global search then adjoint polish | Kontoleontos, Asouti, Giannakoglou 2012; Bons et al. 2019 | Stage 6 | - |

**Nobody has published this whole system** (free-form, milled, 3D turbulent external drag, CFD-scored
evolution from many seeds). The parts are published; the combination is ours to prove. Section 7 is how.

## 3. Architecture

```
 seed STEPs ──► ingest ──► field (1 mm) ──► build (rules, mill, 3 mm walls, checks, mass, ballast)
                               ▲                         │ legal car folder (STLs)
        operators (crossover,  │                         ▼
        mutation) on fields    │            CFD, fresh mesh (drag, lift) ──► race time
                               │                         │
                         parents picked ◄── archive: best design per niche (volume x openness)
                                                         │ top 2-3 different designs
                                                         ▼
                                        hybrid loop polish (adjoints propose, CFD decides)
```

| Stage | Module (new unless marked) | Does | Reuses |
|---|---|---|---|
| 1. Ingest | `seedevo/ingest.py` | Whole-car STEP (frame, units and solid names of `cad/trial_car.step`) -> voxels -> signed-distance field; refuses a seed whose body differs outside the region | `cadio.read_step_solids`, `tessellate`, `voxelize`; `geometry.Car` |
| 2. Build | existing | Field -> legal milled body, exact mesh, mass, lead chosen by the race model; reports how much the rules changed (`rules_changed_mm3`) | `shape_loop.build_design`, `export_design`, `objective.best_ballast` |
| 3. Describe | `seedevo/describe.py` | Numbers of the built body, no CFD: pod volume, openness (through-openings seen from the side and from above), frontal area, overlap (IoU) with every seed | `campaign._descriptor` as the starting point |
| 4. Vary | `seedevo/operators.py` | Section 4 | `shape_loop.redistance`, `esi/make_step.py`'s smooth random fields |
| 5. Archive, select, refine | `seedevo/engine.py`, `seedevo/space.py` | Sections 5 and 5b | `shape_loop.step_field`, `grid_gradient` |
| 6. Score | existing | One fresh-mesh production run per design, repeats by meshing-frame shift only (D7) | `prodcheck.py`, `gate.kw` (`GATE_DOMAIN_DX_MM`), `objective.RaceModel` |
| 7. Refine in the loop | `seedevo/engine.py` (`refine_one`), `seedevo/real.py` | Section 5b: the adjoint's move on elites every generation | `esi/esi_on_state.py`, `dafoam/`, `shape_loop.solve` (morph path) |
| 8. Final polish | existing | Hybrid loop (adjoints + random moves + recombination) on the finalists, each on its own wall-resolved mesh | `hybrid/loop.py`, `resolved_bumps.yml` |

Objective: race time from CFD drag and lift with the exact mass (D1); drag is reported beside it. Opening
windows removes foam and adds lead low in the car; the race model prices that without CFD.

## 4. Operators (all act on fields; every child then goes through stage 2)

| | Operator | What it does | Why |
|---|---|---|---|
| X1 | Splice | Front of A, rear of B, joined across a plane with a 6-10 mm smooth blend (also top/bottom, inboard/outboard) | Whole working halves are inherited intact |
| X2 | Graft | A, with B's geometry inside one 8-20 mm window placed where the two differ | Moves one feature (a groove, a window, a bulge) between designs |
| X3 | Combine | Inside a window: both designs' cuts (minimum) or both designs' material (maximum) | Stacks features |
| X4 | Line step | B's field moved a fraction (<= 0.3) towards A, plus a small smooth random field | Mild morph between two elites (Vassiliades and Mouret) |
| M1 | Bump or dent | Smooth local move, 1-4 mm high, 5-15 mm wide | Local shape change larger than the hybrid loop's |
| M2 | Cut | A groove, slot or through-window swept by a ball >= 6.35 mm along a short path reachable from a mill set-up | New topology the mill can make |
| M3 | Fill | A rib (>= 3 mm) across an opening, or an existing cut closed | The reverse of M2 |
| M4 | Pattern | A periodic field (random direction, period >= 9.5 mm = 3 mm rib + 6.35 mm ball) cuts an array of slots inside a window | Ribs and windows as a family: the CPPN's useful part |
| M5 | Grow or shrink | The surface offset by 0.5-2 mm, whole pod or a window | Volume change (the hybrid loop's moves are volume-neutral) |
| X5 | Latent crossover (later, optional) | A small VAE trained on the archive's legal shapes proposes blends | Only if T4 shows X1-X4 have run dry |

Operator choice: each starts with an equal share; from generation 3 the share follows each operator's
measured rate of children that entered the archive, with a floor of 5 %.

**For the owner to rule on:** M2-M4 are a vocabulary of cuts placed at random. The design is still a field,
not parameters, but they are hand-written operators. Without them new openings can only come from seeds.

## 5. Selection: a map, with noisy scores handled

- **Map:** pod volume (6 bins) x through-openings seen from the side and from above (4 bins: 0, 1, 2-3,
  4+) = 24 niches (`space.py`; amended from 30 before any run: a "slotted array" bin had no measurable
  definition). Each niche keeps its best design. Seeds fill it first (the census, stage P2).
- **Parents:** a niche drawn uniformly from the occupied ones; crossover takes its second parent from a
  different niche.
- **Entry rule (adaptive sampling):** a child scored once enters an empty niche at once. Against an
  incumbent it must look better on its first run; then child and incumbent each get runs on shifted
  meshing frames until both have the same count (at most 3), and the child replaces the incumbent if its
  mean is lower by >= 2 SE, SE = sigma x sqrt(1/n + 1/n), sigma from T1. Entry at 2 SE is for searching
  only: **every claim in a report needs 3 SE** on the confirmation meshes (T5).
- **Batch:** about 20 runs per generation (section 5b says how they are split).

## 5b. The adjoint inside the loop (`engine.py`)

Each generation spends its runs on three kinds of children:

| Kind | Made by | Scored on | Enters the map |
|---|---|---|---|
| **Explore** (9) | Crossover or mutation of map members (section 4): any topology | A **fresh** mesh: noise sigma_fresh | By the duel above |
| **Refine** (3 elites x 2 step sizes) | The adjoint's own move on an elite: sensitivity -> `shape_loop.step_field` (smoothing, 95th-percentile scaling, mass price) -> the builder | The elite's own mesh **morphed** onto the child: noise ~100x smaller | Replaces its parent if CFD says it is better by >= 3 SE of the morph and >= the floor; else that elite's step halves |
| **Control** (2) | The same operators on census seeds only (test T4) | Fresh mesh | Never |

- **The adjoint proposes, CFD decides** (the hybrid loop's rule, unchanged). A sensitivity is solved once
  per elite and reused until that elite changes. Any adjoint that writes `Xs, dD_dXs` works: DAFoam on a
  coarse mesh of that elite, or OpenFOAM's own (ESI) on its scoring mesh.
- **Lamarckian:** the refined field replaces the elite, so later crossover inherits the refinement.
- **Which elites:** the best two by estimate plus one drawn from the other niches, so the map improves,
  not only its champion.
- **Scores through a refinement chain:** child estimate = parent estimate + morph-measured change, carrying
  the parent's count of fresh runs. After 2 mm of accumulated morph (the measured range of one mesh) the
  elite is re-run on a fresh mesh of its own and the two estimates are pooled.
- **Second use of the adjoint (`guided`):** once an elite has a sensitivity map, its mutations are placed
  by it: cuts where the surface wants to move in, material where it wants out. Tested as arm `memetic_g`.
- **What the adjoint still cannot do:** change topology. New openings come only from seeds, crossover and
  the cut / fill / pattern operators.

## 6. Budget (in CFD runs; cost per run is set by T1's mesh)

| Stage | Runs | Gate to the next |
|---|---|---|
| P0 Build; tests T0, T0b, T3 | 0 | all three pass |
| P1 Instrument, T1 | ~24 | I1 and I2 |
| P2 Seed census, test E | N seeds + ~15 repeats | E |
| P3 Heritability, T2 (also generation 1) | 24 | H and D |
| P4 Evolution, generations 2-9, T4 | 160 | - |
| P5 Confirmation, T5, T6 | ~25 | S1 |
| P6 Hybrid polish of 2-3 finalists | as `hybrid/` (about 13 per generation and lane) | Marks of `HYBRID_TEST.md` |

About 250 runs plus one per seed before polish. On the wall-resolved mesh a run was 129 min on 4 cores
(mesh and 1000 production iterations): roughly 2,200 core-hours plus 9 per seed.

## 7. Tests and pass marks (fixed now)

### No CFD
- **T0 Ingest is faithful.** (a) Known answer: `cad/trial_car.step` through `ingest.py` and the builder:
  built mesh volume within 0.5 % of the CAD body's and surface distance p99 <= 0.3 mm both ways in the
  region. (Amended before any run from 0.05 mm: a body rebuilt from a 1 mm grid rounds sharp edges, and
  **every design, seeds included, is re-surfaced the same way** so that seeds and children are compared like
  with like; the re-surfacing offset of the team pod is measured in T1.) (b) Round trip: a built seed with
  a feature (the grooved pod) written as STL, read back and built again: p99 <= 0.3 mm, volume within 0.5 %.
  (c) Every real seed: where the rules did not act, built surface to seed surface p99 <= 0.3 mm. A seed
  with more than 5 % of its pod volume changed by the rules is labelled **altered** in every table.
- **T0b Operators are usable.** Every operator, 40 draws with parents drawn from 10 test seeds on the real
  car and the real builder (amended before any run from 20 draws x 10 pairs: a build takes 13 s). Pass per operator:
  legal children >= 50 %; of the legal ones >= 70 % overlap their nearest parent with IoU between 0.50 and
  0.98 (neither a clone nor noise); median volume the mill puts back <= 10 % of the pod (the lattice CMA:
  about 25 %). An operator that fails is fixed or removed before any CFD is spent.
- **T3 The search machinery works on a known answer** (`toy.py`, `run_t3.py`). Score = weighted mismatch
  to a hidden legal target built from parts of three seeds, one cut no seed has, and a smooth sculpt of
  the whole surface. Fresh score = truth + noise at 0.25 x the seeds' spread (reliability 0.94, what test
  E demands); morph score = exact difference with 1/50 of that noise, only for small moves that keep the
  topology and within 2 mm of a fresh mesh; adjoint = the true surface sensitivity mixed with a fixed bias
  field to correlation rho, twice the true size; costs: fresh 1, morph 1, adjoint 0.7. 12 seeds, budget
  300 after the census, problem instance 1, random seeds 1-5 (amended before any marked run from 200
  evaluations; instance 0 was used only to debug). The score of an arm is the **noise-free** objective of
  the design it would hand over (its map's best by its own noisy estimate). This proves the machinery, the
  noise rule and the budget split, **not the physics**.
  - **T3a Evolution works:** `evo` beats `randpar` (no selection) and `mutonly` (no crossover), each in
    >= 4 of 5 seeds.
  - **T3b The adjoint in the loop pays, when the adjoint is decent (rho 0.85):** `memetic` beats `evo`,
    beats `evo_polish` (evolve for 70 % of the budget, then the adjoint on the best three) and beats
    `polish` (the adjoint alone from the best seeds), each in >= 4 of 5 seeds. If it beats `evo` but not
    `evo_polish`, the adjoint goes at the end (version 1 of this plan) and this section says so.
  - **T3c A bad adjoint is safe (rho 0 and rho -0.3):** `memetic` is no worse than `evo60` (evolution with
    60 % of the budget) in >= 4 of 5 seeds at each rho: a useless or misleading adjoint may cost its share
    of the runs, never more.
  - **T3d (reported, not marked):** `memetic_g` against `memetic`; rho 0.5; problem instances 2 and 3.

### Amendment B (2026-11-25, after T3 failed as registered on instance 1; written before any held-out run)
Diagnosis on instance 1 (`results/t3_problem1.json`): (1) parents were drawn uniformly over niches, so most
children came from poor niches (the random-parents arm drew only from the 12 seeds and did better); (2) a
small real improvement could not win a duel: two noisy fresh runs cannot show a 0.2-sigma gain at 2 SE.
Changes (`engine.py`, `run_t3.py --amend B --reserve 12`):
- parents by a tournament of 3 from the map; control children still uniform;
- an explore child that is a small, topology-keeping move of its parent (within the 2 mm morph range) is
  scored on the parent's morphed mesh, like a refinement; big or topology-changing children keep fresh meshes;
- duel: both sides at >= 2 runs, the lower mean wins (0 SE); up to 3 runs each while the child looks better;
- 12 runs kept back to re-run the best five by estimate before hand-over (all arms).
Checked on instance 1 only (development, not a test): memetic 2.72, evo_polish 2.80, polish 2.98, evo
3.33, randpar 3.56 (mean noise-free score of the handed design; best seed 4.15).
**Held-out test, marks unchanged from T3a-T3c, on problem instances 2, 3 and 4** (never run before this
commit), random seeds 1-5, budget 300, rho 0.85 / 0 / -0.3. A mark passes on an instance at >= 4 of 5
seeds; **it passes overall if it passes on >= 2 of the 3 instances.** Instance 1 stays reported as failed.
- If T3b passes and T3c passes: the adjoint goes in the loop (subject to the owner's decision).
- If T3b fails only against `evo_polish`: the adjoint goes at the end (version 1), as the plan already says.
- If T3c fails: an inaccurate adjoint costs more than its share; the in-loop adjoint needs a stop rule
  (stop refining an elite after k rejected steps) before it can be used, re-tested on instances 5-7.

### Owner's decisions, 2026-11-25
- **T0 surface mark:** 0.5 mm of edge rounding is accepted for now (measured p99 0.46 mm built-to-CAD,
  0.35 mm round trip). Volumes pass (within 0.5 %).
- **CFD runs on GitHub Actions** (as the hybrid loop did). Wheel supports stay out for now.
- **T0b result (marks as registered):** splice, graft, line, pattern, offset pass; combine, bump, cut and
  fill fail on the clone rate (31-68 % of legal children overlap a parent by more than 98 %), not on
  legality (88-100 %) or mill refill (<= 2.5 %, the lattice CMA ~25 %). They are kept out of any CFD
  run until fixed and re-tested.

### T3e The trust check (owner approved 2026-11-26; written before any held-out run)
Why: on the real car the adjoint's quality will differ by design (it was validated only on the team pod; a
coarse mesh cannot resolve 3 mm ribs and slots). Placing the adjoint at the end limits what a bad adjoint
costs, not how wrong it is.
Method (`engine.py`, `refine_one`, `Config(trust_check=True)`): before a design's first adjoint step, a probe of
half a step along the adjoint and one against it, both on the design's own morphed mesh. Trusted only if the
downhill probe lowers the objective by the margin and beats the uphill probe by the margin (uphill retried at
half size if the morph refuses it; if it still cannot be measured, downhill alone decides, recorded as
one-sided). Untrusted designs, and designs with 2 rejected adjoint steps in a row, are refined gradient-free
(2 random smooth moves per refinement, same morph scoring). The downhill probe counts as a refinement
candidate. Development on instance 0 only (found and fixed: a refused uphill probe was counted as distrust).
Bench (`run_t3e.py`): the adjoint's correlation with the truth set per design: S1 0.85 everywhere; S2 0.85 on
closed pods, 0 on pods with a through-opening; S3 0.85 closed, -0.5 open; S4 0 everywhere; S5 -0.3
everywhere. Arms: `evo` (no polish), `plain` (evolve 70 %, then the adjoint polish without check), `tc` (with
the check), `gf` (gradient-free polish, no adjoint). Instances 5, 6, 7 (never run), seeds 1-5: 15 pairs per
comparison; ties count as "no worse".
- **TC1 cheap when the adjoint is good (S1):** mean(tc) - mean(plain) <= 0.25 x (mean(evo) - mean(plain)): the
  check keeps >= 75 % of the polish's gain.
- **TC2 protects against a misleading adjoint (S3, S5):** tc <= plain in >= 10 of 15, in each scenario.
- **TC3 protects against a useless adjoint (S2, S4):** tc <= plain in >= 8 of 15, in each scenario.
- **TC4 never worse than not polishing:** tc <= evo in >= 10 of 15, in every scenario.
- **TC5 the check discriminates:** trusted share of all checks >= 50 % in S1, <= 20 % in S4 and in S5.
- **PASS = TC1-TC5.** Reported: `gf` against `tc`; trusted share in S2 and S3.
- If it passes: the end polish of the finalists uses the trust check, and the real-CFD check on 3-4 real
  designs (team pod, groove, a slotted and a windowed pod) is next, on Actions, with marks written first.

### T0b' re-test of the four timid operators (owner 2026-11-26: random parameters acceptable; written before the run)
combine, bump, cut and fill failed T0b on the near-copy rate. Their random ranges are widened (combine: whole-pod
50 % (was 30 %), window radius 15-35 mm (10-25); bump: 2-6 mm high (1-4), 8-20 mm wide (5-15); cut: radius 3.7-7 mm
(3.3-5), stretch 1.5-4 (1-3), groove half-length 10-35 mm (7.5-25); fill: blobs 4-9 mm (3-6), ribs 3-6 mm thick
(3-4.5) and 10-20 mm long (8-15), closing window 15-30 mm (10-20)). Re-test on the same 10 real-car test seeds, 40 new
draws each (random seeds 200+), marks unchanged (legal >= 50 %, in band >= 70 %, mill refill median <= 10 %).

### T0b'' (written before the run)
T0b' result (`results/t0b2_operators.json`): bump PASS (in band 93 %), cut PASS (84 %), combine FAIL (53 %), fill FAIL
(53 %). Cause (diagnosed on draws outside the test): fill's "close" variant has nothing to close on pods without
cuts, and combine returns a parent when one pod's shape sits inside the other's. Fix for these two only: redraw (up
to 6 times) when the requested shape overlaps a parent at IoU > 0.98 before the builder. Re-test: same seeds,
40 new draws (random seeds 300+), marks unchanged. Operators that fail stay out of the campaign.

### TF The chosen configuration on the bench, with the final operators (written before the run)
Configuration: evolution (amendment B, all nine operators as passed in T0b/T0b'/T0b''), then the end polish with
the trust check (T3e' fix). New instances 11, 12, 13 (never run; half the seeds windowed, windowed targets), seeds
1-5, budget 300, 12 reserved. `run_final.py`.
- **TFa:** evolution beats random parents and mutation-only, each in >= 4 of 5 seeds, on >= 2 of 3 instances.
- **TFb:** with a good adjoint (S1), the configuration beats evolution alone in >= 4 of 5 seeds on >= 2 of 3 instances.
- **TFc:** with an adjoint that misleads on open pods (S3), it is no worse than evolution alone in >= 10 of 15 pairs.
This is a regression check of the machinery (the operators changed after T3), not a physics result.

### TW Campaign workflow plumbing (written before the run)
`.github/workflows/seedevo_campaign.yml` + `campaign.py` + `campaign_case.py`, a test campaign `campaign_test` of two
seeds (team pod, windowed pod), census batch only, production scheme (mode prod), auto off.
- **W1:** both cases rebuild their design from the stored field on a runner, mesh, solve, and return a production drag;
  the collect job commits `campaign_test/results/gen_0/`.
- **W2:** `campaign.py ingest` then `next` on those results writes a legal batch 1 (here, not on a runner).
- Reported: each drag beside the gate run's frame-0 production drag of the same design (the campaign rebuilds the
  design from its field: pod volume 65.70 vs 65.76 cm3 for the windowed pod, builder drift, not storage).

### TR amendment (2026-11-26 18:30, after DAFoam failed on `slots`, before any probe result)
The slotted pod's coarse DAFoam adjoint stopped at its 2000-iteration GMRES cap (residual 2.8e-2 -> 3.6e-5, still
falling; tolerance 1e-6; DAFoam writes no gradient unless it converges), as one hybrid-loop job did before. Rule: a
design whose DAFoam adjoint fails gets **one retry with 5000 GMRES iterations** (`seedevo_gate_retry.yml`), and its
dn/up probes run against the retry's gradient on the same frame-0 steady state. If the retry also fails, that design's
check is undetermined (counted as not trusted, as registered). Marks unchanged. The failure itself is reported:
the adjoint was harder to converge on the slotted pod than on the team pod.

### TS and TC2: the evolution branch's mechanisms, ported (owner 2026-11-26: "look at how its evolution mechanism
worked and implement that stuff here"; written before the run)
From branch `evolution` (search/layout/simscale_layout.py, search/sidepod and search/shape): (1) **model-screened
batches** (`screen.py`, `Config(screen=True)`): a Gaussian process on every scored design (features: block occupancy on
8 principal components + pod volume), a pool of 4 unbuilt candidates per explore slot, picked by expected improvement
with the kriging believer; the model only chooses which candidates get CFD (D4); (2) **CMA-ES over a coarse lattice**
(`Config(gf_method="cma")`, lattice 6x2x3, 4 moves per refinement) as the gradient-free polish, scored on the
design's morphed mesh like every refinement; (3) the reference/setup bookkeeping and parallel builds (campaign driver,
engineering, no mark). Development on instance 0 only.
New instances 14, 15, 16 (half the seeds windowed, windowed targets), seeds 1-5, budget 300, 12 reserved. Mark form
changed for these two tests only, before the run: a paired count over all 15 runs (the per-instance form failed with
large mean margins in TFa), **>= 11 of 15 = one-sided sign test p 0.06**.
- **TS:** evolution with model screening beats evolution (amendment B) in >= 11 of 15 pairs.
- **TC2:** evolve, then the CMA-ES polish beats evolve, then the random gradient-free polish (both without adjoint) in
  >= 11 of 15 pairs.
A mechanism that fails is kept in the code, off.

### T3e' re-test of the trust check (owner approved the fix and re-test 2026-11-26; written before the run)
T3e failed as registered (instances 5-7, kept as failed). Fixes, developed on instance 0 only: (1) a downhill
probe the morph refuses is retried at half size; if still unmeasurable the design stays **undecided** (re-checked
next generation; after 2 undecided checks it goes gradient-free) and is never counted as distrust; (2) instances
are built with half the seeds windowed (`make_seeds(open_share=0.5)`) and a target with a through-opening, so
"bad adjoint on pods with openings" (S2, S3) is actually exercised.
Held-out instances 8, 9, 10 (never run), seeds 1-5; arms, scenarios and marks TC1-TC4 exactly as T3e.
**TC5 amended:** the trusted share is taken over **decided** checks (an undecided check is a refused measurement,
not a verdict); the undecided share is reported beside it. Same thresholds (>= 50 % in S1, <= 20 % in S4 and S5).
PASS = TC1-TC5. Verdict: `seedevo/t3e_verdict.py`.

### Real-CFD gates T1 and TR (owner, 2026-11-26: "run all the tests we need, 12 hours"; written before the run)
One workflow, `.github/workflows/seedevo_gate.yml`, on this repository's runners. Designs (committed as
`designs/*.tgz`, built by the real builder, the same four as the plumbing run): team pod (`original`), groove
(`channel`), a slotted pod (`slots`, 1 through-opening) and a windowed pod (`window`, 1 through-opening).
**T1 amendment (before the run):** the design set is team pod x 4 meshing frames (0, 0.37, 0.74, 1.11 mm),
groove, slots and window x 3 each; the hybrid final design and no pod are dropped (the final design was built on a
different base surface; no pod's +15 mN check has held on every mesh). Each run: fresh wall-resolved mesh,
production scheme 1000 iterations (drag = 200-iteration block means of the last 1000, as Marks P2-P4), then the
steady model 1200 more (drag = mean of the last 404, as the hybrid loop). Marks I1 (layers on >= 50 % of wall
faces, every design) and I2 (pooled mesh-to-mesh sigma, per model: <= 1.0 mN single runs score; 1.0-2.5 the duel
of section 5; > 2.5 that model cannot score) as written above; reported: each design vs the team pod.
**TR, the trust check on real CFD:** for each of the four designs, a coarse DAFoam gradient of that design (fresh
coarse mesh, steady model, as `coarse_dafoam.yml`), then five moves of peak 0.5 mm on the design's own frame-0
steady mesh (explicit morph, smoothed normals, 1.5 mm ground clearance, 1000 steady iterations, as the hybrid
loop): zero, along DAFoam (`dn`), against it (`up`), random smooth moves seeds 101 and 102. Drag: mean of the last
404 iterations; SE from four 101-iteration blocks; margin m = max(3 x hypot(SE_a, SE_b), 0.15 mN).
- trusted(design) = D(dn) <= D(zero) - m AND D(dn) <= D(up) - m. A move the morph refuses makes the check
  "undetermined" for that design, counted as not trusted (conservative).
- **TR1:** trusted on the team pod (H1's result reproduced through the new pipeline). If TR1 fails, the
  pipeline is suspect and TR2 is not interpreted.
- **TR2 (the question):** trusted on >= 2 of the 3 new designs (groove, slots, window).
- **TR3:** on the trusted designs, D(dn) below both random moves on at least half of them.
- Reported: every drag change, DAFoam's first-order prediction against the measured change.
- **What it decides:** TR1 and TR2 pass -> coarse DAFoam is the end polish's proposer behind the trust check.
  TR2 fails -> the end polish on shapes unlike the team pod is gradient-free, and the adjoint is used only where
  its own check passes.

### Coarse CFD on this machine: plumbing only (DECISIONS D6: no design conclusion from the coarse mesh)
- **TP The whole chain runs on real CFD with a real adjoint** (`real.py`, `run_plumbing.py`). The trial
  car, coarse mesh (~105 k cells), steady model, 4 cores. Census of 5 seeds on fresh meshes (team pod,
  groove, no pod, and two test seeds with cuts); one generation: 4 explore children on fresh meshes and
  2 elites refined (OpenFOAM's own adjoint, frozen turbulence, on each elite's own flow; two step sizes
  each, scored on the elite's mesh morphed onto the child).
  - **P1:** every stage runs on real files with no hand edit between stages: field -> build -> export ->
    mesh -> solve -> adjoint -> sensitivity on the grid -> step -> build -> morph solve -> decision.
  - **P2:** the pipeline reproduces known coarse steady-model numbers: the team pod within 1 % of 449.24 mN
    whole car (`runs/cloud_original` iteration 0), and no pod worse than the team pod by >= 15 mN half car.
  - **P3:** each refined elite returns a decision (accepted, or rejected with its step halved) from at
    least one step scored on a morphed mesh (no fresh-mesh fallback).
  - **P4:** at least one crossover child and one mutation child whose through-opening count differs from
    both parents mesh (checkMesh passes) and converge.
  - Reported, not marked (coarse mesh): every drag number, whether the adjoint's steps lowered drag, the
    first-order prediction beside the measured change.

### CFD
- **T1 Instrument.** Team pod on 4 fresh meshes (frames 0, 0.37, 0.74, 1.11 mm); groove, 3-window pod and
  the hybrid final design on 3 each; no pod on 1; on the wall-resolved mesh, production scheme, 1000
  iterations, each followed by the steady continuation.
  - **I1:** wall layers on >= 50 % of wall faces for every design, windows included (mark L).
  - **I2:** pooled mesh-to-mesh sigma. <= 1.0 mN: single runs score. 1.0-2.5: as section 5. > 2.5: the
    production scheme cannot score a search on this mesh; the steady model replaces it only if its own
    sigma is <= 1.0 and it gives the same sign as production for every pair production separates by 3 SE;
    otherwise stop and fix the instrument first.
  - **I3 (reported):** no pod worse than the team pod by >= 15 mN (held on every mesh so far); the hybrid
    design's gain on fresh meshes (this is also the open confirmation of `hybrid/`).
- **E Seeds differ by more than noise.** After the census: reliability R = 1 - sigma^2 / variance of the
  seed scores >= 0.9. **If E fails, there is nothing for evolution to select on: stop, and polish the top
  seeds with the hybrid loop.**
- **T2 Children inherit.** 12 crossover and 12 mutation children of census parents from the better half.
  - **H:** slope of child score on mid-parent (crossover) or parent (mutation) score >= 0.3, with its 95 %
    interval above 0.
  - **D:** median (child - mid-parent) <= +5 mN half car (the lattice CMA's first generation: about +40).
  - Fail either: the operators are destroying what made the parents good. Fix operators, re-run T0b and
    T2 once; a second fail ends the method.
- **T4 Selection is doing the work.** In every generation 2 of the 11 fresh-mesh children are bred by the
  same operators from seeds drawn uniformly from the census, never from evolved designs.
  - **S2:** over generations 6-9, the mean score of the selected-lineage explore children is below the
    mean of the control children by >= 3 SE.
- **T4b The adjoint is doing work inside the loop** (the real-CFD counterpart of T3b).
  - **A1:** over the run, refine children accepted / refine children scored >= 25 %, and the summed
    morph-measured gain of accepted refinements is >= 3 SE of a fresh-mesh score.
  - **A2:** on the confirmation meshes (T5), the best refined design beats its own unrefined ancestor (the
    last explore child or seed in its lineage) by >= 3 SE. Fail: the refinements were morph or model
    artefacts, and the adjoint is taken out of the loop.
- **T5 The result is real on fresh meshes.** Best evolved design, best seed and team pod, 4 frame-shifted
  meshes each.
  - **S1:** best evolved < best seed by >= 3 SE. Fail: the claim is "a ranked map of alternatives", not
    "better than the seeds".
  - **C (reported):** the same pair on the fine mesh (no wall layers), one run each plus one repeat: same
    sign or not. Not the same sign = "depends on the mesh family", stated in every summary.
- **T6 It is new geometry.** The winner's IoU with its nearest seed < 0.9 in the pod region, or its count
  of through-openings differs from that seed's. Otherwise it is reported as "a seed, selected and
  refined", not as invented.
- **T7 Track (the only test of the instrument itself).** Mill the team pod, the best seed and the best
  evolved design; >= 10 timed runs each. Pass: the track order matches the model's for every pair the
  model separates by >= 2 ms. Until T7, every time in this project is a model number.

## 8. What could make this fail, known now

- **The instrument.** No mesh here is validated against a track; the medium mesh misranked the groove
  against fine; the same car read 3.8 mN apart on two fine meshes. T1 and E are first for this reason.
- **Thin features.** 3 mm ribs need cells well under 1 mm in the pod region and wall layers that form on
  them (I1).
- **The stripped car.** The CFD car has no wheel supports, wings or nose; supports alone read 10-30 mN on
  the coarse mesh. A pod evolved for the stripped car may not be the best pod for the real one. Decision
  below.
- **Budget.** A few hundred runs fill 30 niches thinly. The map will be coarse.
- **Headroom.** The team pod already takes the 25-39 mN a pod is worth over none. What a different
  topology can add is unknown; the method may honestly return "the seeds were already near the best".

## 9. Decisions for the owner before P0

1. Are the cut, fill and pattern operators (M2-M4) acceptable under "no shape parameters"?
2. Add the team's CAD wheel supports (`supports.py --kind cad`) to every car from the census on?
3. Rule set for seeds and children: cargo on or off, ceiling (27.175 mm in the SimScale run), mill set-ups
   (top and bottom only, or all four sides).
4. Where the CFD runs (DECISIONS D15: hosted GitHub runners carry an account risk).
5. How many seeds, and whether some are deliberately extreme (slotted, split, very slim).

## Sources

- Mouret, Clune: [Illuminating search spaces by mapping elites (2015)](https://arxiv.org/abs/1504.04909)
- Gaier, Asteroth, Mouret: [Data-efficient design exploration through surrogate-assisted illumination (2018)](https://arxiv.org/abs/1806.05865)
- Justesen, Risi, Mouret: MAP-Elites for noisy domains by adaptive sampling (GECCO 2019); Flageat, Cully: [Fast and stable MAP-Elites in noisy domains using deep grids (2020)](https://arxiv.org/abs/2006.14253), [Uncertain quality-diversity (2023)](https://export.arxiv.org/pdf/2302.00463)
- Vassiliades, Mouret: [Discovering the elite hypervolume by leveraging interspecies correlation (2018)](https://arxiv.org/pdf/1804.03906)
- Yamasaki, Yaji, Fujita: [Data-driven topology design using a deep generative model (2021)](https://arxiv.org/abs/2006.04559); Kato, Kii, Yaji, Fujita: [data-driven multifidelity topology design with latent crossover](https://arxiv.org/html/2407.06746v2); Fujita group: [data-driven morphological exploration and shape optimization for turbulent pipe systems (2025)](https://ir.library.osaka-u.ac.jp/repo/ouka/all/102927/JMechDes_147_9_091704.pdf)
- Hagg, Berns, Asteroth, Colton, Bäck: [Expressivity of parameterized and data-driven representations in quality diversity search (2021)](https://arxiv.org/abs/2105.04247)
- Clune, Chen, Lipson: [Upload any object and evolve it: injecting complex geometric patterns into CPPNs (2013)](https://datadryad.org/dataset/doi:10.5061/dryad.4qk42); Clune, Lipson: Evolving 3D objects with a generative encoding inspired by developmental biology (2011)
- Langelaar: [Topology optimization for multi-axis machining (2019)](https://repository.tudelft.nl/record/uuid:83241b69-5818-4b4a-a690-2bedfc8d9b40); Morris et al.: [3-axis milling in level-set topology optimisation](https://arxiv.org/pdf/2002.10246)
- Rothlauf: Representations for genetic and evolutionary algorithms (locality); Jones, Forrest: Fitness distance correlation (1995)
- Kontoleontos, Asouti, Giannakoglou (2012); Bons, He, Mader, Martins (2019): as in `ROUTES.md`
- Gradients inside a quality-diversity search: Nilsson, Cully: [Policy gradient assisted MAP-Elites (2021)](https://hal.archives-ouvertes.fr/hal-03135723v2/file/PGA_MAP_Elites_GECCO.pdf) (half the offspring from a gradient operator, half from the genetic one; a later ablation found the gradient operator matters most early and that both are needed: [Flageat, Chalumeau, Cully 2022](https://arxiv.org/abs/2210.13156)); Fontaine, Nikolaidis: [Differentiable quality diversity (2021)](https://arxiv.org/pdf/2106.03894)
- Writing the locally improved design back into the population (Lamarckian) or not (Baldwinian): Whitley, Gordon, Mathias: [Lamarckian evolution, the Baldwin effect and function optimization (1994)](https://www.doi.org/10.1007/3-540-58484-6_245). Lamarckian converges faster and is more easily trapped; the map's many niches are the guard against that here

### Campaign scoring amendment (2026-11-26 21:20, after TW, before any campaign)
A campaign case runs 1000 production iterations from a cold start, so "the last 1000" holds the start-up transient:
in the gate's frame-0 runs the first 200-iteration block reads 198.7 / 200.4 mN and the next four 173.9-174.5. From now
on a campaign production score is the mean of iterations 200-1000 (four 200-blocks; block SE 0.10 / 0.19 mN on those two
runs, against 5.2 / 5.6 with the transient in). T1 stays scored as registered (five blocks of the last 1000); the
200-1000 figure is added beside it as reported, not marked. Also: the campaign workflow now takes its run mode from the
campaign's score key (the TW batch ran in mode prod on a campaign that ranked on steady, so nothing was scored), and
ingest stops if a converged result lacks the score the campaign ranks on.
