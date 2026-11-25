# Seed evolution: architecture, research and the tests that would prove or kill it

Written 2026-11-25. **Status: plan only. Nothing here is built or run.** Every pass mark below is fixed in
this file before any result exists (DECISIONS D12). Paths are relative to `research/sidepod_opt/`.

**Goal:** new sidepod geometry (not a polished copy of one pod) by evolving a population bred from many
different seed pods, every candidate legal and millable, every candidate scored by real CFD, the best few
polished by the existing hybrid loop.

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
| 5. Archive and select | `seedevo/archive.py`, `seedevo/evolve.py` | Section 5; batch ask/tell so it stops and resumes between batches | the ask/tell interface of `methods.py`; `campaign.py`'s state handling |
| 6. Score | existing | One fresh-mesh production run per design, repeats by meshing-frame shift only (D7) | `prodcheck.py`, `gate.kw` (`GATE_DOMAIN_DX_MM`), `objective.RaceModel` |
| 7. Polish | existing | Hybrid loop from the top 2-3 mutually different designs, each on its own wall-resolved mesh | `hybrid/loop.py`, `resolved_bumps.yml` |

Objective: race time from CFD drag and lift with the exact mass (D1); drag is reported beside it. Opening
windows removes foam and adds lead low in the car; the race model prices that without CFD.

## 4. Operators (all act on fields; every child then goes through stage 2)

| | Operator | What it does | Why |
|---|---|---|---|
| X1 | Splice | Front of A, rear of B, joined across a plane with a 6-10 mm smooth blend (also top/bottom, inboard/outboard) | Whole working halves are inherited intact |
| X2 | Transplant | A's difference from the team pod inside a 10-25 mm window, added to B | Moves one feature (a groove, a window, a bulge) between designs |
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

- **Map:** pod volume (6 bins) x openness (5 bins: closed, 1 opening, 2-3, 4+, slotted array) = 30 niches.
  Each niche keeps its best design. Seeds fill it first (the census, stage P2).
- **Parents:** a niche drawn uniformly from the occupied ones; crossover takes its second parent from a
  different niche.
- **Entry rule (adaptive sampling):** a child scored once enters an empty niche at once. Against an
  incumbent it must look better on its first run; then child and incumbent each get runs on shifted
  meshing frames until both have the same count (at most 3), and the child replaces the incumbent if its
  mean is lower by >= 2 SE, SE = sigma x sqrt(1/n + 1/n), sigma from T1. Entry at 2 SE is for searching
  only: **every claim in a report needs 3 SE** on the confirmation meshes (T5).
- **Batch:** 20 children per generation; 4 of the 20 are control children (T4).

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
- **T0 Ingest is faithful.** (a) Known answer: `cad/trial_car.step` through `ingest.py` reproduces the
  `original` seed: built mesh volume within 0.5 % of the CAD's 157.522 cm3 and surface distance p99
  <= 0.05 mm. (b) Every seed: where the rules did not act, built surface to seed surface p99 <= 0.3 mm.
  A seed with more than 5 % of its pod volume changed by the rules is labelled **altered** in every table.
- **T0b Operators are usable.** Every operator, >= 10 seed pairs, 20 draws each. Pass per operator:
  legal children >= 50 %; of the legal ones >= 70 % overlap their nearest parent with IoU between 0.50 and
  0.98 (neither a clone nor noise); median volume the mill puts back <= 10 % of the pod (the lattice CMA:
  about 25 %). An operator that fails is fixed or removed before any CFD is spent.
- **T3 The search machinery works on a known answer.** Score = mismatch to a hidden legal target built
  from features of three different seeds, plus noise at T1's sigma in the same ratio to the seeds' spread.
  Arms at 200 evaluations, 5 random seeds each: the full engine; mutation only; random parents (no
  selection). Pass: the engine's final best (noise-free score) beats both other arms in >= 4 of 5.
  This proves the machinery and the noise rule, **not the physics**.

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
- **T4 Selection is doing the work.** In every generation 4 of 20 children are bred by the same operators
  from seeds drawn uniformly from the census, never from evolved designs.
  - **S2:** over generations 6-9, the mean score of the 64 selected-lineage children is below the mean
    of the 16 control children by >= 3 SE.
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
