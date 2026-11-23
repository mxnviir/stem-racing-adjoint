# Decision log (for the paper)

Every major method decision, why it was taken, the evidence behind it, and the single result that would
overturn it. `ROUTES.md` is the dated lab log with the raw numbers; this file is the short, citable version.
A decision is added here when it is taken and edited when evidence changes its status.

**Status words:** *settled* (evidence in hand), *provisional* (taken, evidence still coming), *open* (not yet
decided), *withdrawn*.

| # | Decision | Status |
|---|---|---|
| D1 | The objective is race time from the race model, not drag | settled |
| D2 | 48.0 g is a legal minimum only; the model chooses mass and ballast; > 50 g flags the model | settled |
| D3 | Shapes are free-form fields; only locations are parameters | settled (owner requirement) |
| D4 | Every candidate is scored by CFD; no predictor stands in for CFD | settled (owner requirement) |
| D5 | Method: multi-start free-form adjoint shaping, each step CFD-checked | provisional |
| D6 | The coarse mesh (~105 k cells) is not used for any design decision | settled |
| D7 | Repeat meshes shift the meshing frame; the geometry is never nudged | settled |
| D8 | Which mesh scores designs (medium vs fine or finer) | open |
| D9 | Which adjoint drives the shape steps (discrete vs normal) | open |
| D10 | The adjoint runs on a steady (first-order) flow model; gains are confirmed on the production model | provisional |
| D11 | Several different starting shapes, because the design space has a valley | settled |
| D12 | Pass marks are fixed in writing before each result | settled |
| D13 | The wheel is optimised separately for inertia and durability, with one closing check | provisional |
| D14 | The hubcap is a separate, later decision (axle-mounted, non-rotating) | provisional |
| D15 | Compute runs only on machines the team owns or rents | settled (see note) |
| D16 | Wheel supports: the team's architecture, from the repo's two engines through one adapter | provisional |

---

## D1. The objective is race time, not drag
- **Decision:** every design is scored by the race-time model (thrust curve, drag, lift, mass, centre of mass,
  wheel inertia, rolling and guide friction), and gradients are race-time gradients.
- **Why:** drag alone ignores mass and COM. Measured slopes: 0.185 ms per mN of drag, 7.5 ms per gram, COM free
  inside a flat zone and costly outside it (4–22 ms cliffs from wheel lift and guide friction).
- **Evidence:** `objective.RaceModel`; ROUTES.md 2026-11-20/21.
- **Overturned if:** track timing of built cars disagrees with the model's ranking. Friction terms are still
  placeholders (`mu_guide`), so this needs physical test data.

## D2. Minimum weight 48.0 g, no sizing to it
- **Decision:** 48.0 g is the legal minimum (T3.6). Nothing resizes a car to it. Below it, lead in the halo
  container tops up to 48.0 g; above it the race model charges every gram. The race model also chooses the
  ballast amount (legal minimum to container capacity). Any car above 50 g is flagged `mass_suspect`.
- **Why:** the best balance of aero against weight has to come from the model, not from a fixed target. A best
  car above 50 g would contradict how strongly weight counts (7.5 ms/g), so it signals a model error.
- **Evidence:** four cars re-scored, ROUTES.md 2026-11-22 11:00: in each the model chose the minimum lead.
- **Overturned if:** the scrutineering scale needs a margin above 48.0 g (then the floor becomes 48.0 + margin).
- **Assumption to replace:** non-body parts are taken as 22.52 g (the drawn car assumed 48.2 g); needs a parts
  weigh-in.

## D3. Free-form shapes; only locations are numbers
- **Decision:** each foam or printed part is a solid/air field on a 1 mm grid, built legally (3-axis milling,
  3 mm walls, rules). Numbers describe only locations: halo, rear wheel, wheelbase, wing and nose positions
  (NACA 0015, no tilt).
- **Why:** a handful of shape parameters cannot describe organic geometry (walls, ribs, tunnels); the design
  must not be limited by what a parameter set can express.
- **Overturned if:** n/a (requirement).

## D4. Every candidate is CFD'd
- **Decision:** no learned or reduced model replaces CFD when a candidate is scored.
- **Why:** nothing shows a predictor could rank this car's sub-percent differences; the porous-material model
  tried earlier misranked thin shapes (it scored a design 18 % better that real-wall CFD found 11 % worse).
- **Overturned if:** n/a (requirement).

## D5. Method: multi-start free-form adjoint shaping
- **Decision:** from several different starting shapes, grow and carve the surface along the race-time
  gradient from an adjoint; add ribs/walls where the adjoint's topological derivative suggests; try tunnels as
  CFD-checked candidates; accept a step only if CFD shows a lower race time. (ROUTES.md "SELECTED ROUTE".)
- **Why:** with limited CFD runs, one adjoint solve gives the direction for every surface point at once;
  random changes to ~400,000 values would waste nearly every run.
- **Evidence so far:** the loop works as an optimiser of the model it is given (coarse: −7.4 % in its own
  model). It has not yet produced an established gain on a trusted mesh (see D6, D8).
- **Overturned if:** no adjoint passes its accuracy check on a mesh that passes D8; then steps are scored by
  direct CFD comparisons without a gradient.

## D6. The coarse mesh is out
- **Decision:** no design loop and no ranking on the ~105 k-cell mesh.
- **Evidence:** the adjoint design's gain was −10.4 mN on coarse and −0.8 ± 0.6 mN on medium (clean repeats).
  Cold-start and warm-start coarse runs agree (−10.3 / −10.4), so the cause is resolution: the coarse mesh puts
  19.8 mN of pressure drag on the team pod's body, medium 8.4, fine 2.6. (ROUTES.md 2026-11-21 10:10, 20:05.)
- **Overturned if:** n/a.

## D7. Repeat meshes shift the frame
- **Decision:** mesh noise is measured by re-meshing the identical surface with the meshing frame shifted by
  multiples of 0.37 mm.
- **Evidence:** the earlier method (nudging the design by 0.05 mm) moved surfaces by up to 0.2–1.5 mm through
  the 1 mm voxel builder; one "repeat" was a different design by 1 cm³ (ROUTES.md 2026-11-21 16:05).
  Clean medium noise: σ = 0.75 mN (7 degrees of freedom).
- **Overturned if:** n/a.

## D8. Scoring mesh (open)
- **Question:** is the medium mesh (~520 k cells) enough to rank sidepod designs?
- **Evidence so far:** medium agrees with coarse on large effects (pod vs none +25 mN; the valley). On medium
  with 3–4 clean repeats the groove is −3.6 ± 0.5 mN. On the fine mesh (3.36 M cells) single runs can't rank
  it: the identical team pod reads 176.04 and 179.86 mN on two meshes (two converged flow states, the ones
  Part 2 documents as ~1.3 ms apart), and the groove's single 178.52 lies between them. Fine repeats are running.
- **Consequence for the method:** the steady solver has more than one converged state per car, so small
  differences need either several clean repeats per design or Part 2's "method A" (each car from both states,
  averaged). Single cold runs are valid only for differences well above ~4 mN (medium) / ~8 mN (fine).
- **Decision rule (fixed 2026-11-21 13:00, mark M1):** medium is adequate only if the team pod's body drag is
  within 3 mN of the finer mesh and every design difference within max(2 mN, 3 SE).
- **Next evidence:** fine clean repeats (team, groove), fine design 8 / no pod / blend 50; the 5 M-cell
  wall-resolved runs.

## D9. Which adjoint (open)
- **Evidence:** discrete adjoint (DAFoam) predicts 66–109 % of measured ±1 mm bump effects (r = 0.98), but
  needs ~150 kB of memory per cell. The normal (OpenFOAM) adjoint on the same flow gets all signs but 2–25 % of
  the size. Ruled out as causes: turbulence treatment (frozen = full, within 1 %), Reynolds number (same flow),
  missing grid terms (adding them made it worse). Suspect: no boundary-layer cells (y+ up to 180).
- **Decision rule:** the normal adjoint is used only if, on a wall-resolved mesh, r ≥ 0.9, all signs agree and
  predicted/measured lies within 0.5–2 at every site (`esi/RESOLVED_TEST.md`).
- **Status 2026-11-23:** the test ran (2.13 M cells, layers on 62 % of wall faces, A1 PASS, both adjoints clean) but is
  inconclusive: every registered bump folded the wall layer when morphed, so no bump pair was measured. The
  next step (locate the folded cells, then a direct-field or stepped morph) needs a written amendment to the test first.
- **Plan B (2026-11-23 18:40, proposed; routes in step 2 wait for the owner's choice):**
  1. Diagnostic, no rule change (PC, morph-only checks, ~1.3 min each): locate the folded cells (`checkMesh -writeSets`)
     for pod_front_low, pod_rear, pod_rear_top_m with the fixed reference; morph pod_front_low and pod_rear_top_m at 0.5 and
     0.25 mm to see whether folds scale with height. Must first reproduce pod_front_low = 9 cells.
  2. One repair, picked from step 1 and written into RESOLVED_TEST.md before any run: smaller bump (0.5 mm, mean over whole
     ~101-iteration cycles) if folds vanish with height; direct-field morph if they sit on sharp edges at any height;
     site swap (chosen on morphability alone) if only pod_front_low's ground gap folds; stepped morph last (needs a ramp).
  3. **Stop rule:** one diagnostic round plus one repair round. If the registered pairs (or the swapped set) still do not all
     morph Mesh OK, the normal adjoint is closed as "not testable on a layered mesh" and Plan C applies.
  4. **Plan C:** discrete adjoint (DAFoam, coarse r = 0.98) on the fine mesh, the scoring mesh D8 now points to (medium
     failed M1). ~150 kB/cell × 3.4 M ≈ 510 GB: a rented machine, only with the owner's OK on instance and cost, after a
     sizing run. Its bump validation needs a working morph on fine (check first). A gradient-free route is not proposed: under
     "no parameters, no predictors" the only step proposer is bump-by-bump differencing, i.e. a gradient at 2 CFD runs per site.
  - Not fixed by any of this: fine-mesh scoring scatter (two flow states, team sd 3 mN) still needs method A or repeats.
  Otherwise the discrete adjoint, but only on a mesh that passes D8 (medium ≈ 128 GB; fine ≈ 500 GB,
  extrapolated), or steps scored by CFD without a gradient.
- **Interaction with D8:** the PC test is on the `resolved` mesh (wall layers); D8's evidence is on `fine` (no
  layers). If the normal adjoint passes, `resolved` becomes the loop mesh and must itself be scored for D8.

## D10. Steady model for the adjoint
- **Decision:** the adjoint is taken on a first-order-upwind flow model that settles to a fixed solution;
  every accepted step is confirmed with the production (second-order) model.
- **Why:** an adjoint is the derivative of a converged solution; the production model's wake never settles
  (residuals stall near 1e-3) and the adjoint solve stalls on it.
- **Cost:** the steady model reads ~26 % more drag on coarse, so its gains are not trusted without the check.
- **Overturned if:** the steady model fails to settle on the scoring mesh (mark A1: block means within 0.10 mN).

## D11. Several different starts
- **Decision:** runs start from at least three very different shapes (full legal block, team pod, no pod).
- **Evidence:** the path from no pod to the team pod first gets worse: no pod 204.2, 50 % 211.0, 75 % 196.5,
  full 178.7 mN (medium); same shape on coarse. A local method starting from "no pod" stalled after −2 mN.
- **Overturned if:** n/a; the number of starts is set by compute.

## D12. Pass marks first
- **Decision:** the pass/fail mark of each test is written in ROUTES.md before the result exists, and is not
  changed afterwards.
- **Why:** several early conclusions (from a previous agent and from this work) did not survive a fair
  re-test; fixed marks stop a result from choosing its own threshold.

## D13. The wheel: optimised separately for inertia and durability, one closing check
- **Decision:** the wheel is designed before the car, for the lowest moment of inertia that survives the load
  cases and can be printed, with a closed outer skin. When the car is final, one check decides whether the
  wheel must be redone with mass priced in.
- **The argument (why separate is exact, not a shortcut):**
  1. The car feels a wheel only through its mass m, its inertia I and its outer skin. In the race model the
     wheel enters as m_eff = m_car + 4·I/r² (r = 14.13 mm); with a closed skin its inside does not touch the air.
  2. So the wheel's cost to race time is  μ·m + c·(I/r²), where c = 7.50 ms per gram and μ is the price of a
     gram of mass at the car's optimum (computed: mass 7.51 ms/g, inertia 7.50 ms per gram of I/r²).
  3. Ballast cannot cancel inertia, so c never changes. μ depends on the car: 7.5 ms/g above 48.0 g; 0 when the
     car carries lead (a gram off the wheel becomes a gram of lead); in between when the car sits at 48.0 g with
     no lead.
  4. When μ = 0 the cost is c·(I/r²) alone: the lowest-inertia wheel is the joint optimum of wheel and car.
- **Data that proves it for the final car (to report in the paper):**

  | Claim | Measurement | Have it? |
  |---|---|---|
  | Inertia always costs | dT/d(I/r²) = 7.50 ms/g from the race model | yes |
  | Mass is free at the optimum (μ = 0) | lead carried by the final car > 0, and ΔT for moving 1 g from the wheels to the lead container | on a test car: groove car, 1.45 g lead, ΔT = 0.000 ms; to repeat on the final car |
  | Worst case if μ were not 0 | (mass of the lowest-inertia wheel − mass of the lightest feasible wheel) × 4 × 7.5 ms/g: an upper bound on the loss | needs the wheel's structural optimisation |
  | The inside does not affect the aero | closed outer skin by construction | design rule |
  | The inertia value is real | spin-down test of a printed wheel | no: 1.39e-7 kg·m² per wheel is computed from the wheel CAD (`part4-simulation/wheel.py` gives 1.41e-7), not measured |
  | Loads do not depend on the car | car mass fixed at the 48.0 g minimum, so wheel loads are the same for every car | by D2 |

- **The closing check:** if the final car carries lead, the wheel stands. If it carries none, the wheel is
  re-optimised for μ·m + c·I/r² with μ measured on that car (the race-time change for 1 g of body foam).
- **Overturned if:** the final car carries no lead and the bound above is larger than the mesh noise in race
  time; or the wheel's inside is exposed to the flow (open spokes).
- **Alternatives considered:** (a) lowest effective mass ∫(1 + ρ²/r²)dm first (assumes μ = 7.5; wrong when
  the car carries lead); (b) wheel structure inside the car optimisation (same answer under claim 1, far more
  cost); (c) computing the whole mass–inertia front and letting the car pick (exact for any μ; kept as the
  fallback if the closing check fails).

## D14. Hubcap later
- **Decision:** a non-rotating cap fixed to the axle is evaluated after the wheel and body, as mass (at price
  μ) against its measured drag change.
- **Why:** fixed to the axle it adds no inertia, so it does not interact with D13; wheels carry ~90 % of
  half-car drag in CFD (157 of 176 mN, fine mesh) on the stripped trial car (body + four closed-disc wheels,
  no wings, nose or supports; a full car is quoted at 64–75 % in `research/APPROACH.md`), so the drag side may
  be large.
- **Needs:** a rule check that a fixed cap is legal; CFD with and without, on the scoring mesh.

## D16. Wheel supports
- **Decision:** every car carries wheel supports of the team's architecture: per axle one printed ABS part,
  wheel to wheel, from the body (flush, glued, or pocketed into the foam) through a neck to a flat disc on the
  wheel's inner side, with the stub axle and bearing. The disc and stub are Part 4's (sized by its load case);
  **everything between the body and the disc is generated** by `support_gen.py` from a free-form solid/air
  field, not drawn and not parametric. The team's CAD supports (`supports.py --kind cad`) remain the
  reference.
- **Why:** the support is part of the real car's shape and mass; the CFD car had none (open air under the
  body at both axles). Coarse CFD: supports add 10-30 mN (180.7 without; 191-211 with), the size of the
  sidepod effects, so they cannot be left out of the shape search.
- **How a support is made legal:** legal volume (inside the wheels' cylinder T7.12.1, 1.5 mm off the track
  T3.7, clear of the T7.13 claw band, inboard of the disc); 1.05 mm minimum wall (opening); only face-connected
  pieces carrying load from the disc to the body/centre plane; one part wheel to wheel; >= 10 mm2 glue contact;
  beam-theory load check (stress, sag at the bearing, disc per foot) on the voxels and again on the as-built
  mesh; gates on the final mesh (one piece, watertight, claw points free). The load-carve removes the
  least-loaded material until the next step fails, never cutting the wheel-to-wheel tie path, and stops when
  thinner disc feet would cost more disc than they save. First result: 5.33 g for both axles (team: 5.88 g).
- **Evidence:** ROUTES.md 2026-11-22 21:00 (CFD of five support sets, mesh capture >= 99.6 % of exposed
  surface, renders inspected).
- **Open:** (a) the glue joint is taken as rigid foam: optimistic; a foam/glue strength from the team would
  turn it into a check; (b) surfaces are lumpy at 0.4 mm voxels; (c) mass: this pipeline's 22.52 g of
  "other parts" vs the SimScale branch's itemised 19.23 g; (d) supports are meshed at level (5 5) on every mesh (fine-mesh build checked: Mesh OK, 99.7 % capture).
- **Overturned if:** the with/without-supports CFD difference is inside mesh noise on a mesh that resolves
  the disc (then supports can stay out of the shape search and be added only for final timing).

## D15. Compute
- **Decision:** CFD runs on machines the team owns or rents (PC, cloud), not on GitHub-hosted runners.
- **Why:** GitHub's terms limit hosted runners to building and testing the repository's software; an earlier
  project lost four accounts this way.
- **Note (2026-11-22):** the wall-resolved adjoint test is nevertheless running as a chained workflow on
  GitHub-hosted runners (`.github/workflows/resolved_adjoint.yml`, set up by the owner's own agent). That was
  the owner's call; the risk above applies to it.
