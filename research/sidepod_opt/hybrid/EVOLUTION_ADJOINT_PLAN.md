# Evolution + adjoint for the most aerodynamic sidepod: the tested plan (draft, results filled in as they land)

Scope (owner, 2026-11-24): aerodynamics of the sidepod only. Constraints kept: the sidepod region (x 0.07-0.20 m,
y > 12 mm, faded at its edges), symmetry, the ground. Dropped for this stage: milling, cargo, mass/ballast, the 27 mm
ceiling, wall thickness. They come back as a final legalisation step, measured by CFD like everything else.

## 1. The method in one paragraph
**Guided evolution, judged by good-mesh CFD.** The design is a smooth normal-displacement field on the pod's surface (no
shape parameters). Each round, one batch of good-mesh CFD runs in parallel on GitHub Actions (free, ~20 at once,
~2 h): the current design re-run; a population of random smooth mutations (evolution); one probe along each adjoint
direction (coarse DAFoam, wall-resolved ESI, last accepted step); and a fan of steps along the steepest descent
inside the span of every direction measured so far. The best candidate replaces the design if it beats it by >= 3 SE
(Lamarckian selection). The adjoints never decide anything: each one is weighted by the drag change its own probe
actually produced, measured in the same batch. Evolution supplies exploration and the safety net; the adjoints supply
direction where they are right.

## 2. Why this and not the alternatives (evidence)
- [to fill: R1, R1b, R2 results; DAFoam smoke test; morph]

## 3. Pipeline
- Good mesh: the wall-resolved mesh (2.1 M cells, y+ ~1), steady upwind model (D10), warm start, 1000 iterations.
- Moves: explicit morph of that mesh (`P2_MORPH_EXPLICIT`, wall layer moved rigidly), tested clean to 1 mm per move.
- DAFoam: coarse mesh of the current design + DAFoam on a GitHub runner (`coarse_dafoam.yml`), ~1 h, free.
- ESI: on the good mesh (as in the 2026-11-23 test).
- Optimiser: `hybrid/guided_es.py` (ask/tell, resumable), round builder, verdict scripts.

## 4. Schedule, costs, decisions for the owner
- [to fill]
