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
| 6 random smooth moves | evolution's mutation | exploration, and measured directions for the next recombination |
| one move along each adjoint | DAFoam (coarse, fresh at the parent, ~1.5 h on a free runner) and ESI (fresh at the parent, ~2 h) | the cheap guess at "downhill"; measured, not trusted |
| moves along the recombination of last round's measured moves | least squares in their span: all of them, and the random ones only (`combine.py`) | evolution's recombination; uses every measurement |
| two sizes for the recombinations (AMP, AMP/2) | AMP = 0.5 mm, 0.25 mm once the chained mesh gets tight | the step size is chosen by CFD |

The best child replaces the parent if it is below the parent's re-run by >= 3 SE **and** by >= 0.15 mN (Lamarckian
selection: the improved design is what the next generation starts from). The adjoints never decide. One command builds
each generation from the last one's results with these rules: `python hybrid/loop.py next <k> <fresh DAFoam npz>`
(`LOOP_AMP`, `LOOP_ESI=esinpz:<fresh ESI npz>`).
Implementation: `hybrid/loop.py` (the generation driver), `hybrid/guided_es.py` (the same rules as an ask/tell class, the
interface of the evolution branch's CMA wrapper, ported in `hybrid/evolution_methods.py`), `esi/make_step.py` (moves),
`hybrid/combine.py`, `hybrid/chain_solve.py` (chained explicit morph), Part 2's `openfoam_case.py` (explicit morph,
opt-in), workflows `resolved_bumps.yml`, `coarse_dafoam.yml`, `morph_check.yml`.

## 2. What the tests showed (2026-11-24 18:37 to 2026-11-25; details in section 6)
1. **The discrete adjoint (DAFoam), run on the cheap coarse mesh, is a good *direction* on the good mesh** (H1 PASS,
   fidelity r 0.85, 10/11 signs) but **not a step size** (2x too large). It costs ~1.5 h on a free GitHub runner, so it
   can be recomputed at every new design, and that matters: the base gradient was spent after 1 mm, and the gradient
   recomputed at the moved design gave generation 4's step (-1.02).
2. **The normal adjoint (ESI) failed every gradient test, but as a direction it works**: it gave generation 2's step
   (-1.28 on top of DAFoam's 1 mm). The two adjoints point in nearly unrelated directions (cosine 0.0-0.2) and found
   different improvements. Fresh ESI at a moved design works (~2 h), but ESI's direction hardly changes with the design
   (cosine 0.8-1.0) while DAFoam's does (0.05 after 1.5 mm): refresh DAFoam every generation, ESI rarely.
3. **Evolution's part is small in the tested loop.** Random moves alone are weak (most were worse than the parent in
   every generation). Recombining the measured moves (least squares in their span) helps in two ways: it carried the
   adjoint's direction forward (generation 5's accepted step is 0.80-aligned with the DAFoam move it was built from), and
   evolution-only recombinations gave the steps of generations 3 and 6 (-0.27, -0.19), both after the mesh had refused
   the adjoints' moves. At 0.5 mm (reported, not marked) the combination beat either part alone (-5.24 vs DAFoam -4.84,
   evolution alone -2.62); at 0.125 mm the marked test (H2) failed. **What was tested is an adjoint-proposed loop with
   evolution's recombination as the fallback; evolution's global role (several starts, phase C) is untested.**
4. **The loop works**: every generation kept a step under a rule fixed beforehand: -6.93 (DAFoam 1 mm), -1.28 (ESI),
   -0.27 (evolution-only), -1.02 (fresh DAFoam), -0.25 (combination, mostly DAFoam), -0.19 (evolution-only): **-9.94 mN,
   5.2 % of the half-car drag** (steady model), six generations, 87 completed good-mesh solves since 18:37 (all tests
   included). Adjoint-led steps: 9.48 of 9.94; evolution-only: 0.46.
5. **It survives the production scheme**: the -8.21 design keeps -6.32 mN (3.5 %) under linearUpwind (Mark P2 met).
6. **The limit is the mesh**: the explicit morph (new, opt-in) moves the wall layer rigidly and allows ~1 mm per morph,
   chained to ~2 mm (5 levels); after that even 0.25 mm adjoint moves fold. Beyond that the mesh must be rebuilt
   (untested here). DAFoam on a runner failed 2 of 7 times (a lost runner; one unconverged adjoint).

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
| B. New mesh (untested) | rebuild the wall-resolved mesh and its steady state on the accepted design (snappy + layers, 1000 production iterations, ~1200 upwind iterations), then continue A from it | the first build: mesh + production link 129 min on Actions, steady continuation ~2 h (it ran on Kaggle; Actions can do it as a second link): **~5 h, free** | needed every ~2 mm of accumulated change (5 chained morph levels); the new mesh's base value is re-measured, so its own noise does not enter acceptance |
| C. Several starts (evolution's global part; untested) | run A from 3-4 different starting pods (team pod, groove, a 50 % blend, no pod) in parallel lanes | lanes share the ~20 runners | the space has a valley (a half-grown pod is worse than none): one start is not enough |
| D. Confirmation | best designs under the production model, fresh meshes, repeats (D8, D10) | production runs ~3 h each | only confirmed gains count |
| E. Legalisation | milling, 27 mm ceiling, wall thickness, mass back on; re-measure | as A | the final car |

## 5. Decisions for the owner
1. **DAFoam back in (coarse, free runners) and ESI back in, both as proposers only.** Both failed as gradients and stay
   failed; as directions whose every move is CFD'd they carried most of the gain. Fine-mesh DAFoam (rented, ~$15-40 per
   gradient) is not needed by this plan.
2. **Is the least-squares combination a "predictor"?** It turns measured drag changes into a proposed direction (no
   model decides anything; the proposal is CFD'd). It is the "combined" arm; if the owner rules it out, the loop runs on
   the adjoint moves and the random moves alone (at 0.5 mm the combination gave -5.24 vs DAFoam's -4.84).
3. **Volume-neutral moves** (mean removed before scaling) are a constraint the aero-only stage could drop; dropping it
   would let the pod shrink or grow freely, which the drag will reward until the mass rules come back.
4. **What is confirmed and what is not:** the loop runs on the steady upwind model (D10). Under the production scheme
   the best design keeps 0.77 of its gain (Mark P2 met: -6.32 mN, 3.5 %); Mark P (an earlier pair, whole-signal SE)
   was not met. Still open: fresh meshes and repeats (D8), and the full race-time effect.
5. **Mesh rebuilds (phase B) and several starts (phase C) are untested here.** The chained morph ran out at ~1.5 mm
   (generation 3: the strongest +0.5 mm moves folded), so B is the next engineering task.

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
| Mark S (opposite moves raise drag) | met: DAFoam +4.05, random +1.86 at 0.5 mm; but the opposite moves stayed oscillating (0.03 vs 1-3 mN) while the downhill ones went steady | drag is antisymmetric in the move; it does not prove the flow state was unchanged (P2's 0.77 ratio is the better evidence) |
| All arms at 0.5 mm (reported, post-H2) | combined **-5.24**, evolution+DAFoam -5.03, DAFoam -4.84, evolution+ESI -3.77, ESI -3.57, random -2.70, evolution alone **-2.62** | at the working step size, evolution + adjoints beats either alone |
| Mark P (production scheme confirms) | not met: base 181.7 +/- 2.8, DAFoam 0.5 mm 177.6 +/- 3.1 (2000 iterations; same sign, unresolved) | production confirmation needs a better protocol (section 4 D) |
| **Generation 2** (parent DAFoam 1 mm, chained morph; Mark L) | **met**: ESI 0.5 mm -1.28 on top (accepted); DAFoam moves ~0 (spent); combined -0.19; 5 of 6 random moves worse | total **-8.21 mN (4.3 %)**; the second adjoint found what the first had used up |
| **Generation 3** (parent + ESI 0.5; Mark L, 0.15 mN floor) | **met**: evolution's recombination of generation 2's measured moves at 0.25 mm -0.27 (accepted); combined 0.25 mm -0.27; all 6 random moves worse; the 3 strongest 0.5 mm moves folded the chained mesh | total **-8.48 mN**; evolution's part shows once the adjoints' own directions are spent; the morph range is the limit now |
| **Generation 4** (0.25 mm moves) | **met**: fresh DAFoam (recomputed at the moved design) -1.02 (accepted); recombinations -0.16..-0.24; 5 of 6 random worse | total **-9.50 mN (5.0 %)**; refreshing the discrete adjoint each generation pays |
| **Generation 5** (0.25 mm moves) | **met (just)**: combined 0.125 mm -0.25 (accepted); fresh DAFoam and ESI moves folded at 0.25 mm; DAFoam at the new parent did not converge | total **-9.75 mN (5.1 %)**; the chained morph (~2 mm) is now the limit |
| **Generation 6** (0.125 mm moves) | **met**: evolution-only recombination -0.19 (accepted); every adjoint move folded, even at 0.125 mm | **final -9.94 mN (5.2 %)**; the mesh is spent: stop for a new mesh |
| **Mark P2** (best design under the production scheme, block-mean SE) | **met**: 175.49 vs 181.81, **-6.32 mN (3.5 %)**, 0.77 of the steady gain | the gain is not a steady-model artefact (same mesh family; fresh meshes still to do) |

## 7. What to do next, in order
1. **Production confirmation of the final design** (Mark P4, running at the time of writing) and, per D8, on fresh
   meshes with repeats.
2. **Phase B: a new wall-resolved mesh on the final design** (~5 h, free), then continue the loop from it with the same
   rules (`loop.py`, 0.5 mm moves again). The adjoints' moves were the big steps; they need the mesh room back.
3. **DAFoam robustness on runners**: 2 of 7 runner jobs failed (a lost runner; an adjoint that stopped at 2000 GMRES
   iterations). Use the newest converged gradient when one fails (as generation 6 did), and try a looser GMRES
   tolerance or more iterations before relying on it.
4. **Phase C (several starts)** once B works: 2-3 lanes from different pods share the ~20 runners.
5. **Legalisation** (milling, ceiling, wall thickness, mass) as the last loop stage, each candidate CFD'd.
