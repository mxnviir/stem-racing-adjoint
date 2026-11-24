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
[filled in below]

## 5. Decisions for the owner
[filled in below]

## 6. Evidence, in order
[filled in below]
