# Architecture

Three searches share one car builder, one CFD route and one race model.

```
                 genes (numbers in [0, 1])
                          |
   search/layout  ->  layout_genes.decode  ->  layout, body loft, nose, wings, cargo, lattice
   search/shape   ->  (stage-1 layout + a lattice of control points)
                          |
                 search/layout/layout_car.build
                          |   runs car/build/run_car.py (a subprocess per car)
                          v
   car/body   param_body.build: rule masks + loft (+ lattice) -> milled with the 3.175 mm ball, 3 mm walls
   car/parts  assembly.build: wheels, halo, nose cone, wings, tether guides (no supports yet)
   car/build  legality.check: every rule with its margin -> summary.json
                          |
   layout_car.judge   waivers (below), mass + lead to 48.2 g, COM
   layout_car.export_cfd   ONE closed solid of the whole car (cfd/layout_wrap.py)
                          |
   cfd/   simscale_layout.LayoutEvaluator: reduce to N triangles -> air volume with exact wheels (STEP)
          -> SimScale import -> mesh -> k-omega SST, 1000 iterations -> drag and lift
                          |
   search/sidepod/objective.RaceModel (car/race): race time with THIS car's wheelbase, thrust point,
   mass and COM  ->  the search is told the race time
```

The sidepod search is older and narrower: the team's own STEP outside the sidepod region, a voxel field
inside it (search/sidepod/geometry.py), the same SimScale evaluator (cfd/simscale_step_eval.py) with the
pod as triangles and the rest exact CAD.

## Frames and units

- Car frame (car/, search/layout, search/shape, cfd/): x from the nose tip towards the tail, y left,
  z up from the track; mm in the builder, metres in the CFD files. Ref A = front axle - 16 mm,
  Ref B = rear axle + 16 mm.
- Team STEP frame (search/sidepod/geometry.py): x forward (nose at +x), mm. `Car.to_car_frame` mirrors it.
- Forces: whole car (the CFD is a half car; x2), at 20 m/s, `D20_N` and `L20_N`.

## The pieces

### car/body (was Part 1)
`param_body.build(W, x_front, d_halo, body_params, rear_len_mm=, cargo_placement=, lattice=)`:
the grid for this layout (`unified_phi.build_unified_geometry`), the loft (eight superellipse stations
from Ref A to the rear face, sidepods, optional bumps), the rule masks forced on top (T4.2 cargo,
halo pocket and ballast container, the 52 mm cartridge bore with its 3 mm wall, wheel keep-clear zones,
T8.5.1 nose cap), then `machining` (top-and-bottom 3.175 mm ball, 3 mm minimum wall), loose pieces
joined or dropped. `rear_len_mm` moves the rear face (and the bore) for the layout search; `lattice`
is stage 2's free-form change. Mass from the cells (0.163 g/cm3 foam).

### car/parts (was Part 4)
`assembly.build(...)`: the team's wheels (their measured files), the official halo in its pocket, the
nose cone lofted onto the body's front section, NACA 0015 front and rear wings at the minimum legal size,
tether guides on stalks, the wheel supports (switched off by `supports=False`), and Part 4's own gates.
`joints.make_all` cuts pockets for the printed parts and writes the manufacturing files (skipped in
searches with `--no-joints`; rebuild finalists without it).

### car/build (was Part 5)
`run_car.py`: one car end to end (body, parts, mass roll-up, referee, report). `legality.py`: the
scrutineer, independent of the builder (it imports nothing from car/body; `rules_constants.py` is
typed from the regulations; `docs/RULES.md` maps every rule to its check).

### car/race (was Part 2)
`race_objective.py`: the race simulation (measured thrust sheet, mass, wheel inertia, rolling and guide
friction, drag and lift), `pitch_balance.py`: axle loads with the thrust line above or below the COM,
`physics_contract.py`: calibrated constants. `search/sidepod/objective.RaceModel` wraps it for one car's
layout.

### cfd
- `layout_wrap.py`: the merged car rebuilt from its own occupancy on a 0.3 mm grid and reduced with a
  topology-keeping edge collapse. The union of parts carries needle triangles and 0.03 mm ledges that
  SimScale's importer rejects; nothing thinner than a cell survives the rebuild, so no slit or void is left.
- `simscale_step_eval.py`: the SimScale state machine (keys, project, import, mesh, run, forces), one
  case per car, restartable from its JSON state; retires a key on 402/403 or a quota message and moves
  its unfinished cases to the next key; flags diverged runs.
- `simscale_template.py`: the simulation spec (half car, 20 m/s inlet, moving road 0.15 mm under the
  wheels, rotating wheels, k-omega SST, manual mesh 30 mm far field / 0.8 mm smallest, 1.5 mm refinement box;
  small-feature suppression 0.05 mm for the sidepod route, 0.8 mm for the whole car, see RUNBOOK "Meshing").
- `simscale_step_domain.py`: the half wind tunnel with the car cut out, faces named for the boundary
  conditions, written as STEP.
- `cadio.py`: mesh <-> OpenCASCADE / manifold3d helpers.

### search
See [SEARCH.md](SEARCH.md).

## What is waived, and why

A search car is not refused for:

| rule | why |
| --- | --- |
| T7.12 wheel supports | the supports are designed later (user, 2026-11-22); their 5.9 g is counted at the axles |
| T3.6 48.0 g | met by lead in the T1.22 container (up to its 15.8 g capacity, else refused) |
| T5.1 chamber diameter | the bore is the block's own drilled 18.1 mm; the 1 mm build grid draws it 0.6 mm small. Finalists are measured on the fine grid |

T9.4.2 (40 mm behind Ref B) is measured on the rear wing and its support only (team's reading,
2026-11-22); the body is limited by the 223 mm block.

## Files a car folder holds

`summary.json` (every check, mass), `layout_car.json` (genes, decoded numbers, verdict, mass with lead,
CFD solid report), `body_half.stl`, `parts/*.stl` + `assembly.json`, `body_full.stl` (the merged solid,
metres; reduced to 60k faces once timed), `wheelF.stl`/`wheelR.stl`/`wheels.json`, `run_car.log`.
