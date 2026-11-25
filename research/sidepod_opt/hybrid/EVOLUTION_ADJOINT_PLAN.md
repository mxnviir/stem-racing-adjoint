# Evolution + adjoint for the most aerodynamic sidepod: the tested plan

Owner's request (2026-11-24 ~18:15 UTC): combine evolution with both adjoints (discrete DAFoam, normal ESI) to make the
most aerodynamic sidepod; aerodynamics only; research first; bring over the evolution branch's parts; test; 18 hours.
Every number below is a wall-resolved CFD result on GitHub Actions unless it says otherwise. Marks were written before
each round's solves (`HYBRID_TEST.md`); where a mark failed, it says so.

## 1. The method: guided evolution, judged by good-mesh CFD
The design is a smooth normal-displacement field on the pod's surface: no shape parameters, no predictor. Each round is
one batch of good-mesh CFD runs in parallel (free runners, ~20 at once, ~1.5-2 h):

| member of the batch | where it comes from | why |
|---|---|---|
| parent re-run | the current design | the reference for this round (the pipeline is deterministic: repeat 0.0003 mN) |
| ~6-10 random smooth moves | evolution's mutation | exploration, and an unbiased measured gradient estimate |
| one move along each adjoint | DAFoam (coarse, fresh each round), ESI | the cheap guess at "downhill"; measured, not trusted |
| moves along the combination of everything measured | least squares in the span of measured moves (`combine.py`) | evolution's recombination; uses every measurement |
| a fan of sizes (0.5 / 1.0 mm) along the best directions | | the step size is chosen by CFD |

The best member replaces the parent if it beats it by >= 3 SE (Lamarckian selection: the improved design is what the
next generation starts from). The adjoints never decide; each adjoint's move is measured in the same batch it is used.
Implementation: `hybrid/guided_es.py` (ask/tell, resumable, the interface of the evolution branch's CMA wrapper, ported
in `hybrid/evolution_methods.py`), `esi/make_step.py` (moves), `hybrid/combine.py`, `hybrid/chain_solve.py` (chained morph),
workflows `resolved_bumps.yml`, `coarse_dafoam.yml`, `morph_check.yml`.

## 2. What the tests showed (2026-11-24 18:37 onward)
[filled in below, section 6]

## 3. Why this design, and not the alternatives
- **Plain CMA-ES (the evolution branch):** 96 SimScale cars over a 72-number lattice never beat the team pod (best 4 %
  worse). Probable causes (not tested here): ~6 mm random steps where 0.125 mm already moves drag by +-1 mN; a fresh
  mesh per car (that mesh changed the team car's drag by 6 %); milling and rule masks applied after each sample. Its
  ask/tell interface is kept; its lattice is not (shape parameters).
- **Adjoint descent alone:** the coarse DAFoam direction is the best single direction at 0.5-1 mm, but on its own it
  sizes steps 2x wrong and goes flat after ~1 mm (0.5 -> 1.0 mm adds only 2.1 mN of 6.9).
- **ESI alone:** fails every gradient test; as a move it lowers drag (0.5 mm: -3.6 mN) but less than DAFoam's.
- **Guided ES (Maheswaranathan et al. 2019) as the frame:** keeps evolution's guarantee (it is a descent method in
  expectation whatever the adjoints' bias) and uses the adjoints where they help (`RESEARCH.md`).

## 4. Schedule and cost (proposed)
All on free GitHub runners (public repository); no paid machine is needed for any step below.

| phase | what | cost per unit | gate to the next phase |
|---|---|---|---|
| A. Local loop | `hybrid/loop.py next <k>` each generation: parent re-run + fresh DAFoam move + ESI move + 6 random moves + 4 combination moves, chained explicit morph, 0.5 mm moves | ~2 h, ~13 runners, one fresh DAFoam gradient (~1.5 h, in parallel with the previous generation) | stop when 2 generations in a row accept nothing, or the chained morph refuses (~1.5-2 mm total) |
| B. New mesh | rebuild the wall-resolved mesh and its steady state on the accepted design, then continue A | the first build took several chained 6 h jobs (Actions + Kaggle); expect ~1 day | needed after every ~1.5-2 mm of accumulated change |
| C. Several starts (evolution's global part) | run A from 3-4 different starting pods (team pod, groove, a 50 % blend, no pod) in parallel lanes | lanes share the ~20 runners | the space has a valley (a half-grown pod is worse than none): one start is not enough |
| D. Confirmation | best designs under the production model, fresh meshes, repeats (D8, D10) | production runs ~3 h each | only confirmed gains count |
| E. Legalisation | milling, 27 mm ceiling, wall thickness, mass back on; re-measure | as A | the final car |

## 5. Decisions for the owner
[filled in below]

## 6. Evidence, in order
All on the wall-resolved mesh (2.1 M cells), steady model, morphs of one tested mesh, change of half-car drag vs the
unmoved team pod (190.73 mN). Whole-signal SE ~0.12 mN at small moves, < 0.01 mN at 0.5-1 mm.

| test (marks fixed before) | result | what it decided |
|---|---|---|
| Step test (ESI proposes, 0.125 mm) | FAIL: ESI -0.64, a random move -1.04 | ESI alone is no better than luck at tiny steps |
| Retro check (post hoc) | coarse DAFoam predicts 8 measured good-mesh moves r 0.82 | worth a prospective test |
| **H1** coarse DAFoam proposes (0.125 mm, vs 10 randoms) | **PASS**: -1.07, opposite +0.90; tied with the best random (-1.04), 46 % more per RMS move; fidelity r 0.85, signs 10/11, sizes 2x too big | DAFoam is a usable *direction*, never a step size |
| DAFoam on a free GitHub runner | reproduces the stored gradient (cos 0.9985); ~1.5 h | fresh gradients each generation are affordable |
| Morph limits | old morph 0.125 mm; explicit morph (wall layer moved rigidly) **1 mm** per morph; chained morphs 1.5-2 mm (2 of 4) | larger changes without new meshes, up to ~2 mm |
| Mark E (explicit morph agrees) | met (-1.18 vs -1.04) | the new morph does not change the answer |
| Larger steps (reported) | 0.5 mm: DAFoam -4.84, ESI -3.57, random -2.70; 1.0 mm: DAFoam **-6.93**, GUIDED -6.65 | step sizes of 0.5-1 mm pay; the adjoints win at this size |
| **H2** combined vs evolution-only vs DAFoam (0.125 mm) | **FAIL**: evolution-only -1.84 beat combined -1.40; combined vs DAFoam not separable | at tiny steps the adjoints add nothing to evolution's own estimate |
| Mark S (shape, not flow state) | met: both opposite 0.5 mm moves raise drag (DAFoam +4.05, random +1.86) | the 0.5 mm gains are shape |
| All arms at 0.5 mm (reported, post-H2) | combined **-5.24**, evolution+DAFoam -5.03, DAFoam -4.84, evolution+ESI -3.77, ESI -3.57, random -2.70, evolution alone **-2.62** | at the working step size, evolution + adjoints beats either alone |
