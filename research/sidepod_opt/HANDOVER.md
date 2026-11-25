# Handover: the whole project in one file

Written 2026-11-22 13:15 UTC. Repository `mxnviir/stem-racing-paper` (formerly `esp32-line-follower`),
working branch `claude/dazzling-ritchie-3q792g`. Never push to `main` without the owner saying so.

**Read order for a new agent:** this file → `DECISIONS.md` (what was decided and why) → the top section of
`ROUTES.md` ("SELECTED ROUTE") → `ROUTES.md` status log from the end backwards for raw numbers.
`HANDOFF_LOCAL.md` (2026-11-21) is older; its pitfall table and Codespace notes are still valid, its
status is not.

All paths are relative to `research/sidepod_opt/` unless they start with `part` or `research/`.

---

## 1. The idea

A STEM Racing (F1 in Schools) car is a CO₂-powered dragster: about 48 g, 20 m of track, about one second.
The team wants software that **designs the car's shape on its own**, and a research paper about it.

- **What "on its own" means (owner):** give it the legal space and it decides what goes there: organic
  surfaces, thin 3 mm walls, ribs, tunnels, structure around tunnels. Not blobs, not a tuned copy of a human
  design, and not limited to seed shapes the team drew.
- **What it is scored on:** race time from a race model (thrust curve, drag, lift, mass, centre of mass, wheel
  inertia, friction). Not drag alone.
- **What it must respect:** the regulations, 3-axis milling of the foam body, printed ABS parts, and the
  truth of real turbulent CFD: every candidate gets a CFD run, nothing predicts performance in its place.
- **Scope:** started with one sidepod region of a fixed trial car; the goal is the whole car (pods, nose,
  wing supports, halo loft, wheel and wing positions).

**Status in one line:** the tooling works end to end; the open questions are which mesh can be trusted to
rank small shape differences, and which adjoint (gradient method) is accurate enough to drive the shaping.
No car has been built or track-tested: every time is a model number.

---

## 2. The car and the owner's fixed rules

| Item | Rule |
|---|---|
| Objective | Race time (`objective.RaceModel`, Part 2's model) |
| Weight | 48.0 g legal minimum; nothing sizes a car to it; the model picks mass and ballast; a best car above 50 g means the model is wrong |
| Ballast | Lead in the T1.22 container under the halo (capacity ~15.8 g) |
| Pods | Milled foam (0.163 g/cm³), 3-axis, 6.35 mm ball end, 3 mm minimum walls, no through-hole rule |
| Printed parts | Nose cone, wing supports, wheel supports: ABS, 0.2 mm nozzle (printer's minimum wall still unknown) |
| Wings | NACA 0015, no tilt; only their fore/aft and up/down positions vary |
| Layout numbers | Halo fore/aft, rear wheel fore/aft, wheelbase, front wing / rear wing / nose positions |
| Shapes | Free-form fields, never shape parameters |
| Scoring | Real CFD for every candidate; no neural network or other predictor |
| Compute | Limited; only machines the team owns or rents; never GitHub-hosted runners |
| Adjoint | Normal (continuous) adjoint preferred because the discrete one needs too much memory, if it proves accurate |

---

## 3. Architecture: what each part is and the idea behind it

```
 field on a 1 mm grid ──► build (rules, mill, walls, checks, mass, ballast) ──► car folder (STLs)
        ▲                                                                          │
        │ step along the race-time gradient                                         ▼
 adjoint (drag gradient on every surface point) ◄── steady flow ◄── mesh + RANS CFD (OpenFOAM)
                                                                                    │ drag, lift
                                                                                    ▼
                                             race model (thrust, drag, mass, COM, inertia) ──► race time
```

### The five parts (the original pipeline; mostly used as libraries now)

| Folder | What it is | Concept |
|---|---|---|
| `part1-simulation` | The milled body as one field on a 1 mm grid with every rule as a hard mask; the machining rule; mass and COM | A body is only valid if the mill can make it and the rules hold, so both are applied to the field itself, not checked afterwards |
| `part2-simulation` | OpenFOAM half-car CFD (`openfoam_case.py`, `cfd_wrapper.py`), the race-time model (`race_objective.py`, JAX, differentiable), the ESI adjoint case (`openfoam_adjoint.py`), noise studies | One trusted "stopwatch": geometry in, drag/lift out, then race time and its slopes |
| `part3-simulation` | The "compass": turns an aero sensitivity map into a race-time map (`compass.py`); known-answer checks for adjoints | A gradient must pass a test with a known answer before anything follows it |
| `part4-simulation` | Everything that is not the body: wheels (`wheel.py`: the team's wheel STLs, one 3×6×2.5 mm bearing of 0.30 g per wheel, mass and inertia computed from the mesh: 1.41e-7 kg·m² per wheel), wings, nose, supports, joints, print files | Exact parametric parts with rule gates and manufacturing files |
| `part5-simulation` | One car end to end (`run_car.py`), the referee (`legality.py`, 113 rule rows), the older search (`solver.py`, `pattern.py`) | A scrutineer in code, independent of the code that builds the car |

Each part's `README.md` has a module-by-module table of its files (what every `.py` does); they are current.
Two mismatches with the owner's rules to fix when the whole-car work starts: Part 4 assumes printed parts in
SLS PA12 / PLA (owner: ABS, 0.2 mm nozzle), and these files are still set to the old 48.2 g sizing: `part5-simulation/run_car.py`, `pattern.py`, `solver.py`,
`part1-simulation/ballast.py`. Change when the whole-car work starts (DECISIONS.md D2).

### `research/` (where the current work lives)

| Folder | What it is |
|---|---|
| `research/APPROACH.md`, `research/LITERATURE.md` | The 2026-11-19 review: what the five parts do, where the old search went wrong, and the literature (no published work solves the whole problem) |
| `research/organic_feasibility`, `research/sidepod_region`, `research/optimiser_bench` | Earlier test benches (2D and 3D lattice-Boltzmann at low Reynolds number; optimiser benchmarks). Superseded: the low-Reynolds tunnel ranked sidepods wrongly |
| `research/sidepod_opt` | **The current work**: free-form sidepod design on the trial car with real CFD |

### The CFD model (Part 2)

- Half car with a symmetry plane, 20 m/s, air; k-ω SST RANS; rolling road; rotating wheels; steady solver
  (`simpleFoam`), drag = mean of the last 20 % of iterations ("D20"). Whole-car drag = 2 × half car.
- **What is in the CFD car today:** the milled body (`car`) and four wheels as closed spinning discs (`wheelF`,
  `wheelR`). No wings, nose cone or supports: at both axles there is open air under the body where the printed
  support pod sits on the real car (`supports.py` adds the team's CAD supports and `support_gen.py` generates
  new ones, both as an opt-in `supports` patch refined with `GATE_PLUS_SURFACES=supports`; coarse CFD: supports
  add 10-30 mN, see D16; a car with supports is a new baseline). So "wheels carry ~90 % of drag" describes this stripped trial car;
  `research/APPROACH.md` quotes 64–75 % for a full car.
- Meshes (`resolution=`): `coarse` ~105 k cells, `medium` ~520 k, `fine` ~3.36 M, `resolved` ~4–5 M with a
  wall-layer stack (y+ ≤ 2). **Coarse, medium and fine have no boundary-layer cells** (the search settings
  switch layers off; wall functions on bare cells).
- "Production model" = second-order velocity scheme (`linearUpwind`): the wake never fully settles.
  "Steady model" = first-order upwind velocity (`CFD_DIV_U="bounded Gauss upwind"`): settles to a fixed
  solution (needed by an adjoint) but reads ~26 % more drag on coarse.

### The race model

`objective.RaceModel` wraps Part 2's `race_objective.py` with this car's axles, thrust line and guides.
Slopes on the team car: **0.18 ms per mN of drag, 7.5 ms per gram, 7.5 ms per gram of wheel I/r²**, lift
negligible, centre of mass free inside a flat zone with 4–22 ms cliffs outside it (wheel lift, guide friction).
Friction terms (`mu_guide` 0.25, rolling 0.010) are placeholders until the team measures them. The wheel inertia
(1.39e-7 kg·m² per wheel) comes from the wheel CAD, not from a spin test of a printed wheel.

---

## 4. How one design becomes a race time (the working path)

1. **Field** `f` (mm, positive = foam, 1 mm grid of the STEP): `shape_loop.seeds()`, or a step of the loop.
2. **Build** `shape_loop.build_design(car, f)`: rules (forced air/foam, locked spine), 3-axis mill, 3 mm
   walls, checks (one piece, nothing changed outside the region, cargo inside, ground clearance), exact mesh,
   mass. `geometry.Car.mass()` adds lead only up to 48.0 g; `objective.best_ballast()` lets the race model pick
   more.
3. **Export** `export_design` → `<folder>/car/` with `car_half.stl`, `wheelF.stl`, `wheelR.stl`,
   `assembly.json`, `mass_report.json`, `body_full.stl`.
4. **CFD** `prodcheck.py <car folder> <tag> <np> cold` (production model, fresh mesh, cold start) →
   `gate_results_<res>/prodcheck_<tag>.json` plus force histories. `PRODCHECK_RES` picks the mesh.
5. **Race time** `rm(D20, L20, mass)` → seconds and slopes.
6. **Adjoint** (when a gradient is wanted): steady flow → `dafoam/` (discrete) or `esi/esi_on_state.py`
   (normal) → dD/dX per surface point → `shape_loop.grid_gradient` → `step_field` → back to 1.

---

## 5. Every route tried, in order, and what it taught

| # | Route | Result | Lesson |
|---|---|---|---|
| 1 | Original pipeline: carve the body along an ESI adjoint "compass" (Parts 1/3/5) | The adjoint failed Part 3's sign tests | A gradient needs a known-answer check |
| 2 | Low-Reynolds lattice-Boltzmann benches (`research/sidepod_region`, `organic_feasibility`) | Ranked pods wrongly (Re ~2×10³ vs 2.7×10⁵) | Only full-Reynolds RANS counts |
| 3 | **Route D:** `sidepod_opt` campaign: CMA-ES / BO / SAIL / NEAT / SPSA over lattice, CPPN or level-set shapes (`campaign.py`, `methods.py`, `design.py`), OpenFOAM / Actions / SimScale evaluators | Built and tested; not run at scale | Kept as tooling; lattice/CPPN parameters are not the owner's "free-form" |
| 4 | **Route B:** porous-material topology optimisation from an empty region (`topo/`) | Stalled at the seed skin; CMA on the porous model scored a design 18 % better that real-wall CFD found 11 % worse | A porous solid has no boundary layer: it misjudges thin shapes |
| 5 | ESI adjoint vs ±1 mm bumps (`gate_results/RESULT.md`) | r = −0.5 | Confounded: adjoint on a 375 k mesh, bumps on 520 k, unsteady flow |
| 6 | **Route A** (free surface + real-wall adjoint): DAFoam discrete adjoint on the production flow | Out of memory on medium; on coarse the solve stalled | An adjoint needs a settled flow; memory ~150 kB per cell |
| 7 | DAFoam on the **steady model**, coarse mesh | **Passed**: predicted/measured 1.09, 0.66, 0.97 at three sites, r = 0.98 | The discrete adjoint is exact for the model it is given |
| 8 | Shape loop v1 → v2 (`shape_loop.py`), run `cloud_original` from the team pod | −7.4 % in its own (steady, coarse) model (accepted steps 1, 3, 4, 6, 7, 8) | The loop works as an optimiser |
| 9 | Run `cloud_lean` from no pod | Stalled after −2 mN | A local method can't grow a pod from nothing |
| 10 | Concept probes on coarse: blends, groove, windows, block | Pod vs none 25 mN; half-grown pod worse than none (a valley); groove −5.5; windows worse | Big structure of the design space |
| 11 | Medium-mesh re-check | The adjoint design's −10.4 mN became ≈ −1 mN | **The coarse mesh invented ~10 mN of body pressure drag and the adjoint optimised that** |
| 12 | "Repeat meshes" by nudging the design 0.05 mm | Surfaces moved 0.2–1.5 mm through the voxel builder | Repeats must keep the geometry: shift the meshing frame (`GATE_DOMAIN_DX_MM`) |
| 13 | Clean medium verdict | Groove −3.6 ± 0.5 (real), adjoint design −0.8 ± 0.6 (not established), σ = 0.75 mN, valley and windows confirmed | Medium agrees with coarse on big effects |
| 14 | ESI adjoint re-tested fairly on the coarse steady flow | Signs 3/3, r 0.98, but 2–25 % of the size; frozen = full turbulence; grid terms made it worse; undamped wall term crashed it | Not turbulence, not Reynolds number; suspect the wall mesh (no layers) |
| 15 | Wall-resolved test on the coarse mesh | Impossible: layers formed on 0 of 5,666 faces | The wall-resolved question needs the ~5 M mesh (running on the owner's PC) |
| 15b | Wall-resolved test on the 2.1 M `resolved` mesh (Actions + Kaggle, 2026-11-23) | Inconclusive: adjoints clean, A1 passes, but every registered ±1 mm bump folds the 15 µm wall layer when morphed | Bump checks on a layered mesh need a morph that keeps the wall field smooth at the 0.1 mm scale |
| 15c | Same test, smaller bumps (±0.5 / ±0.5 / ±0.25 mm, Actions, 2026-11-24) | FAIL: all morphs clean and pairs clear, but 2 of 3 signs wrong and predicted/measured ≤ 0.43 (frozen and SST) | The normal adjoint is not used; next is the discrete adjoint on fine (paid) or bump-by-bump differencing, owner's choice |
| 15d | ESI as a step proposer, CFD decides (wall-resolved, common 0.125 mm, Actions, 2026-11-24) | FAIL: downhill −0.64 mN, uphill +0.52 (right sign), but a random smooth step gave −1.04 | The adjoint is dropped from the loop; next is a gradient-free CFD-scored search (owner to approve) |
| 15e | Evolution + both adjoints, CFD decides (`hybrid/`, wall-resolved, explicit chained morph, 2026-11-24/25) | DAFoam proposes well (H1 PASS); six generations reach **-9.94 mN (5.2 %)** steady (adjoint-led 9.48, evolution-only 0.46); the generation-3 design keeps -6.32 mN under the production scheme (Mark P2) | Loop: `hybrid/loop.py`; next a new mesh on the final design (the chained morph is spent at ~2 mm) |
| 16 | Fine mesh (3.36 M) | The identical team pod reads 176.0 and 179.9 on two meshes (two converged flow states, known in Part 2 as ~1.3 ms apart); groove 178.5 lies between | Single fine runs can't rank designs closer than ~8 mN; small differences need several clean repeats or both-state scoring (Part 2 "method A") |
| — | **Route C** (sharp surface on a fixed grid, immersed boundary) | Never built: no ready turbulent framework | — |
| — | **Route E/G** ideas rejected by the owner: a parts kit with shape "recipes" and quality-diversity search; a neural-network drag predictor | Not built | Parameters can't describe organic shapes; every candidate must be CFD'd |
| — | **Route F** idea: a CFD-scored search over the layout numbers (BO/TuRBO) around the shaping loop | Not rejected, not agreed: the layout method is still open (section 6, point 5) | — |

Literature anchors (full list at the end of `ROUTES.md`): body-fitted level-set optimisation (Feppon,
Allaire, Dapogny), topology-to-shape (Koch), multimodality (Bons; Chernukhin & Zingg), memetic EA + adjoint
(Giannakoglou's group), topological derivatives (Amstutz; Sá & Novotny), adjoint wall functions (Zymaris).
Free-form turbulent external-aero topology design is not published as one working system.

---

## 6. The selected route

**Multi-start free-form adjoint shaping, every step checked by CFD** (`ROUTES.md` top section;
DECISIONS.md D5).

1. Shapes are fields; every field is built legally.
2. One adjoint solve gives the race-time gradient on the whole surface; the surface grows or carves along it;
   a step is kept only if CFD shows a lower race time.
3. The adjoint's topological derivative suggests where a new rib, wall or island would help; tunnels are
   tried as a few CFD-checked candidates.
4. Several very different starts (full legal block, team pod, no pod), because the space has a valley.
5. Layout numbers: CFD-scored changes alternating with shape steps (method still to agree with the owner).
6. Winners re-run on clean repeat meshes and finer meshes before milling.

**Three gates before the loop may run:**

| Gate | Question | State |
|---|---|---|
| 1. Scoring mesh | Does the mesh rank designs like finer meshes do? | **Open.** Coarse: no. Medium: yes for big effects; groove −3.6 ± 0.5 with 3–4 clean repeats. Fine: single runs too noisy to say (same car 176.0 vs 179.9). Fine repeats running in the cloud session |
| 2. Adjoint | Is the normal adjoint accurate on a wall-resolved mesh? | **Open.** Test running on the owner's PC (section 8). Fallback: DAFoam on the largest mesh that fits memory, or steps without a gradient |
| 3. Steady flow | Does the first-order model settle on that mesh? | Part of the PC test (mark A1) |

**The two open gates depend on each other:**
- The PC test runs on the `resolved` mesh (wall layers). Gate 1's evidence is on `fine` (no layers). If the
  normal adjoint passes there, `resolved` becomes the loop's mesh, and it must then be scored like the others
  (team, groove, no pod, repeats) before the loop runs on it.
- If the fine repeats confirm that medium mis-ranks pod details, the fallback "DAFoam on medium" would repeat
  the coarse-mesh mistake (optimising mesh error). DAFoam on the fine mesh needs roughly 500 GB (3.36 M cells ×
  ~150 kB, extrapolated). Then the realistic options are the normal adjoint (if it passes) or gradient-free
  steps scored on the fine mesh.

The wheel is a separate, smaller problem (DECISIONS.md D13): lowest inertia that survives the loads and prints,
closed outer skin; one closing check on the final car's lead. Hubcap later (D14).

---

## 7. Where things stand right now

**Running in the cloud session** (4 cores, 15 GB; see section 11 for how to keep it alive):
`gate/fine_here2.sh` → fine mesh, production model, 2,000 iterations, ~4.5 h per run, in this order:
`groove~1` (due ~19:10 UTC 22 Nov), then `team~2`, `groove~2`, `nopod`, `adjoint8`, `blend50` (`gate/fine_here3.sh`). Results land in
`gate_results_fine/prodcheck_<tag>.json`; `python fine_campaign/summarize.py fine` prints the table and marks.

**The wall-resolved adjoint test** runs as a GitHub Actions workflow on this branch
(`.github/workflows/resolved_adjoint.yml`, set up by the owner's agent; `ubuntu-24.04` hosted runners, chained
links, "all runs 1,000 iterations" protocol; state in `.github/resolved_adjoint_state.json`). On 22 Nov ~16:00
UTC it was still on the production base (link 4). Its verdict arrives as a ROUTES entry plus
`gate_results_resolved*/` on this branch; watch the Actions tab for progress.

**Another session works on branch `ccr-a4f3e46d-23atrh`:** the repo reorganised into `car/`, `cfd/`, `search/`,
SimScale-scored sidepod evolution (CMA) and a whole-car layout search. Its results: ROUTES.md 2026-11-22 19:00.
It still tops cars up to 48.2 g and places the team's CAD supports.

**Open questions, in priority order**
1. Fine repeats: with 3 fine meshes each, is the groove better or worse than the team pod (gate 1)? The solver
   has two converged states per car (~3.8 mN apart on fine), so single runs don't answer it. If 3 repeats don't
   either, score each design from both states (Part 2's method A: `stopwatch.py`, `campaign.py make-refs`).
2. The PC verdict on the normal adjoint (gate 2).
3. With both answered: run the loop from the three starts on the chosen mesh with the chosen adjoint.
4. Topological-derivative step and tunnel candidates: designed, not yet coded.
5. Whole-car integration (Part 5 body vs the trial-car STEP), layout search method.
6. Physical data: parts weigh-in, wheel spin-down, friction, a track run.

---

## 8. How to check the PC's adjoint test (the latest decision on the normal adjoint)

The test, its marks and its setup are in `esi/RESOLVED_TEST.md`. It currently runs as the `resolved_adjoint`
GitHub Actions workflow (section 7): there, read the run's job logs and wait for its ROUTES entry. The commands
below are for a run on a PC with `esi/run_resolved_test.sh`, where results live **on the PC** unless it was
started with `PUSH=1`.

**On the PC (repo root):**

```bash
tail -n 30 research/sidepod_opt/gate/resolved_test.log
```

```bash
cat research/sidepod_opt/gate_results_resolved_up/esi/VERDICT.txt
```

```bash
ls research/sidepod_opt/gate_results_resolved research/sidepod_opt/gate_results_resolved_up
```

**From any other machine (only if the PC pushed):**

```bash
git pull origin claude/dazzling-ritchie-3q792g && cat research/sidepod_opt/gate_results_resolved_up/esi/VERDICT.txt
```

To get results off the PC, commit them by hand there (re-running with `PUSH=1` only pushes when the test runs to
the end, and the log is git-ignored):

```bash
git add research/sidepod_opt/gate_results_resolved research/sidepod_opt/gate_results_resolved_up && git add -f research/sidepod_opt/gate/resolved_test.log && git commit -m "Normal adjoint test on the wall-resolved mesh: results so far" && git pull --no-rebase origin claude/dazzling-ritchie-3q792g && git push origin claude/dazzling-ritchie-3q792g
```

If the PC started from the first zip (before 15:32 UTC 21 Nov) its log has no layer-coverage line; read it from
the mesher's log instead:

```bash
grep "Extruding" research/sidepod_opt/gate/refA_resolved/logs/snappyHexMesh.log | tail -1
```

**How far it got** (each line appears in the log when the step is reached):

| Log line / file | Meaning |
|---|---|
| `layer coverage: Extruding X out of Y faces (P%)` | Wall layers after meshing. **Mark L:** P ≥ 50 or the test stops (not wall-resolved) |
| `mesh: N cells, y+ a..b; production D …; steady D …, block span … -> A1 PASS/FAIL` | Base flows done. **Mark A1:** span ≤ 0.10 mN, or the test stops (flow doesn't settle) |
| `gate_results_resolved_up/bump_<site>[_m].json` (6 files) | Measured ±1 mm bumps; `"morph_fallback": true` voids that pair |
| `gate_results_resolved_up/esi/pair_judge_frozen.json`, `…_sst.json` | Adjoint vs bumps per site |
| `VERDICT.txt` | One line per adjoint version: signs, r, predicted/measured, PASS/FAIL |
| `RESOLVED_TEST_DONE` | Finished |

**Reading the verdict** (marks fixed 2026-11-21, do not change them): PASS needs r ≥ 0.9, every sign right,
and predicted/measured between 0.5 and 2 at all three sites.

| Outcome | What it decides | Next step |
|---|---|---|
| PASS (frozen or sst) | The normal adjoint is usable on wall-resolved meshes (DECISIONS.md D9) | Score the `resolved` mesh for gate 1 (`RES=resolved … campaign.sh stage0`, then `forward`); wire `esi/esi_on_state.py` into `shape_loop.adjoint()`; check the steady→production transfer on that mesh; run the loop |
| Signs right, sizes off | Wall resolution alone doesn't fix it | Discrete adjoint only on a mesh that passes gate 1 (medium ≈ 128 GB, fine ≈ 500 GB), else gradient-free steps |
| A1 FAIL | The steady model doesn't settle at 5 M cells | No adjoint there; consider a coarser wake region or an unsteady adjoint; report block means |
| Mark L FAIL | The mesh isn't wall-resolved | Fix the layer settings (Part 2 `resolved_layer_controls`) before any conclusion |
| ESI crash in `adjointkOmegaSST` | Known (seen twice) | The frozen result stands on its own |

Also record from the PC: cells, y+, peak memory and wall time per step (`resources_*.json`), and append a
dated entry to `ROUTES.md` and update D9 in `DECISIONS.md`.

---

## 9. File map

### `research/sidepod_opt/` documents
| File | What |
|---|---|
| `HANDOVER.md` | This file |
| `DECISIONS.md` | Decision log for the paper: 15 decisions, evidence, what would overturn each |
| `ROUTES.md` | Lab log: selected route at the top, then every dated result with numbers and pass marks, sources at the end |
| `HANDOFF_LOCAL.md` | Older hand-off (21 Nov): Codespaces, pitfalls table |
| `README.md` | The campaign tooling (methods, evaluators, design → timed car) |
| `PARTS_PLAN.md` | Plan for wings, nose cone and wheel supports (not built) |
| `SIMSCALE.md`, `EVOLUTION_SIMSCALE.md` | Running the evolution methods on SimScale |

### Core code
| File | What |
|---|---|
| `geometry.py` | `CarSpec` (all dimensions, 48.0 g floor, lead container), `Car`: STEP → 1 mm grid, rules, mill, checks, exact mesh, `mass()`, `export_car_folder` |
| `cadio.py` | STEP reading, tessellation, mesh repair, Booleans |
| `objective.py` | `RaceModel` (race time and slopes), `best_ballast` (the model picks the lead), `mass_cell_gradient` |
| `shape_loop.py` | The shaping loop v2: `seeds`, `build_design`, `solve`, `adjoint`, `grid_gradient`, `step_field`, `init/run/show` |
| `run_loop_here.sh` | Restart-proof wrapper: one loop iteration at a time, commit and push each |
| `supports.py` | Wheel supports for a car folder: `add <folder> --kind cad|beam` (team CAD solids or Part 4's parametric engine) → `supports.stl` wall patch, mass, COM, gates; `compare` checks them against `cad/example_car.step` |
| `support_gen.py` | The wheel-support GENERATOR (D16): per axle a solid/air field on a 0.4 mm grid → rules (legal volume, 1.05 mm wall, load path disc→body, one part wheel to wheel, glue contact) → load check (voxels and as built; disc sized per foot) → marching cubes, union with Part 4's disc and stub → `supports.stl` (CFD-trimmed), `supports_gen.json`, render. `python support_gen.py demo <car folder> --only carved_tie` (run under `ulimit -v 7000000`). Fields: `f_carved` (load-carve, protected tie path), `f_envelope`, `f_random`, `f_broken` (must be refused) |
| `render_cfd_patch.py` | What the CFD mesh made of the supports: the kept case's `supports` patch over the input part; capture of exposed surface, stray faces |
| `prodcheck.py` | One production-model CFD run of a car folder on any mesh (`PRODCHECK_RES/ITERS/TIMEOUT/KEEP/RESULTS/WALL_RESOLVED`) |
| `prodchain.py` | Production check of a loop run along one morphed-mesh lineage |
| `gate.py` | Bump geometry (`bumps`, `variant`), base state, bump solves, ESI adjoint judge; `kw()` holds the mesh settings (`GATE_RES`, `GATE_DOMAIN_DX_MM`, `GATE_WALL_RESOLVED`) |
| `design.py`, `methods.py`, `campaign.py`, `evaluators.py`, `eval_one.py`, `report.py`, `render.py` | The earlier search framework (lattice / CPPN / level-set shapes; CMA, BO, SAIL, NEAT, SPSA; OpenFOAM, Actions, SimScale evaluators) |
| `simscale_tool.py`, `config.*.json` | SimScale by hand |
| `test_methods.py`, `test_simscale.py`, `_parity.py` | Tests of the search framework |
| `codespace_*.sh`, `gate_*.sh` | Older launchers for Codespaces and gate lanes |

### Adjoint code
| File | What |
|---|---|
| `dafoam/make_case.py` | DAFoam case from a converged OpenFOAM state (same mesh, BCs, schemes) |
| `dafoam/runScript.py`, `run_docker.sh` | DAFoam primal + Krylov adjoint in Docker (`dafoam/opt-packages:v5.1.1`); `DAF_PRIMAL_ONLY=1` for a forward-only check |
| `dafoam/pair_judge.py`, `judge.py` | Adjoint prediction vs measured ± bump pairs |
| `esi/esi_on_state.py` | OpenFOAM's own adjoint on an existing mesh and flow → `esi_sens.npz` in DAFoam's format (`ESI_MESHMOVE`, `ESI_ATC_FULL` options) |
| `esi/run_resolved_test.sh`, `esi/RESOLVED_TEST.md` | The ~5 M-cell wall-resolved normal-adjoint test and its instructions |
| `topo/` | Porous topology optimisation attempts (`mill_topo.py`, `mill_cma.py`, …): superseded |

### Fine-mesh campaign
| File | What |
|---|---|
| `fine_campaign/campaign.sh` | Resumable launcher: `cars`, `stage0`, `forward`, `steady`, `bumps`, `adjoint`, `judge`, `bccheck`, `summary`; repeat meshes as `<design>~k` |
| `fine_campaign/make_cars.py` | Rebuilds every test car from code (`--check` compares with local runs) |
| `fine_campaign/steady_base.py` | Steady-model continuation of a production state + mark A1 |
| `fine_campaign/summarize.py` | Tables and marks M1–C5 across coarse / medium / fine |
| `fine_campaign/README.md` | Order, machine sizes, pass marks |

### Results (in git)
| Folder | What |
|---|---|
| `gate_results/` | The first (confounded) ESI gate on medium |
| `gate_results_coarse/` | Coarse production checks, concept probes, cold-start control |
| `gate_results_coarse_up/` | Coarse steady state: base, 6 bumps, DAFoam gradient (`dafoam/`), ESI gradients (`esi/`), verdicts |
| `gate_results_medium/` | Medium production runs; `<design>~k` = clean repeats; `_p05/_m05` and `win3edge` = nudged copies (not repeats) |
| `gate_results_fine/` | Fine production runs (in progress) |
| `gate_results_bccheck_nolayers/` | DAFoam accepts the wall-resolved BC types (mesh had no layers: not a full check) |
| `gate_results_resolved*/` | The PC's 5 M test, when pushed |
| `runs/cloud_original/`, `runs/cloud_lean/` | Loop runs (logs, per-step `cfd.json`, `current.npz`, best car); `it_008/field.npz` = "design 8" |

Git-ignored: `runs/` and `gate/` (use `git add -f` for files that must be kept), `cache/`, smoke-test output.
`gate/` holds the queue scripts and logs of this machine (`fine_here2.sh`, `medium_table.py`, …).

---

## 10. Reference numbers (half-car drag, production model, mN)

| Design | Coarse (105 k) | Medium (520 k, clean) | Fine (3.36 M) |
|---|---|---|---|
| Team pod | 180.9 | 178.74 (4 meshes, sd 0.91) | 176.04, 179.86 (2 meshes) |
| Groove (`channel`) | 175.4 | 175.15 (3, sd 0.37) | 178.52 |
| Adjoint design 8 | 170.5 | 177.95 (3, sd 0.75) | running |
| 3 windows / 5 windows | 182.8 / 187.0 | 180.93 / 180.75 | — |
| No pod | 206.2 | 204.23 | running |
| Blend 50 % / 75 % | 212.3 / 201.1 | 210.98 / 196.52 | 50 % queued |
| Block | 251.8 | — | — |
| Team pod body pressure drag | 19.8 | 10.4 (mean of 4: 8.4–11.7) | 2.6, 5.3 |
| Team pod wheels | 147.7 | 154.8 (mean of 4: 152.9–157.8) | 157.5, 159.1 |

Mesh noise (clean repeats): medium σ = 0.75 mN; fine: one pair 3.8 mN apart (two flow states). Cost on 4 cores: coarse 5–6 min,
medium ~35 min, fine ~4.5 h (6.2 GB), DAFoam adjoint on coarse 27 min and ~15 GB.
Adjoint accuracy on the coarse steady flow (predicted/measured at pod_rear, pod_front_low, pod_rear_top):
DAFoam 1.09 / 0.66 / 0.97; ESI 0.09 / 0.02 / 0.24.

---

## 11. Operating the cloud machine (and any other)

- **Tools:** OpenFOAM v2412 (`source /usr/lib/openfoam/openfoam2412/etc/bashrc`, outside `set -u`), Python at
  `/opt/py/bin/python` (no pip/pytest), Docker for DAFoam (`dockerd` must be started by hand).
- **After a container restart** (they happen; every running job dies): `swapon /swapfile`, delete
  `part2-simulation/cfd_case_template/runs/run_*`, restart the queue script (all are resumable: finished
  results are skipped).
- **Keep-alive:** the session is reclaimed when idle. Keep one tracked background loop (≤ 2 h, re-arm) while a
  queue runs, and a 30-minute log watcher.
- **Git:** `git pull --no-rebase` before every push; push only to the working branch; commit results as they
  land (a stop hook insists); no PRs unless asked; never paste tokens.
- **Method rules:** pass marks in `ROUTES.md` before the result; never change a mark, iteration count or
  tolerance to get a pass; compare only like with like (same mesh level, same model, same `NP` in a set);
  repeat meshes by frame shift only; report failures with their cause.
- **Docs to keep current:** `ROUTES.md` (every result, dated), `DECISIONS.md` (when a decision or its evidence
  changes), this file (when the state in section 7 changes).

---

## 12. Words used

| Term | Meaning |
|---|---|
| D20 | Drag at 20 m/s, mean of the last 20 % of solver iterations; "half car" unless stated |
| Production / steady model | Second-order / first-order velocity scheme (section 3) |
| Adjoint | A second solve that gives the drag gradient for every surface point at once. *Discrete* (DAFoam) differentiates the solver's own arithmetic; *normal/continuous* (OpenFOAM's ESI) solves derived adjoint equations |
| Bump pair | The same spot pushed out and in by 1 mm; half the drag difference is the measured answer an adjoint must match |
| Clean repeat (`~k`) | The identical car re-meshed with the meshing frame shifted by k × 0.37 mm |
| Design 8 / adjoint pod | Step 8 of run `cloud_original` (coarse steady-model adjoint loop from the team pod) |
| Groove / channel | The team pod with an 8 mm lengthwise outboard groove |
| Valley | A half-grown pod is slower than no pod, so small steps from "no pod" can't reach a pod |
| μ | The price of a gram of mass at the car's optimum: 0 if the car carries lead, up to 7.5 ms otherwise |
| Marks M1–C5, A1, A2, L | The fixed pass marks (`fine_campaign/README.md`, `esi/RESOLVED_TEST.md`) |
