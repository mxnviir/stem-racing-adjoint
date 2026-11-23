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
   car/parts  assembly.build: wheels, halo, nose cone, wings, tether guides, wheel supports (support_engine)
   car/build  legality.check: every rule with its margin -> summary.json
                          |
   layout_car.judge   waivers (below), mass + lead to 48.2 g, COM
   layout_car.export_cfd   ONE closed solid of the whole car with its supports (cfd/layout_wrap.py)
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

`freeform.py` (the searches' stage 2): the body and nose as three evolved surfaces, a top and a bottom over
(x, |y|) and a side outline over (x, z), smooth fields over control points from the nose tip to the rear
face (user 2026-11-23: no fixed stations, squareness or constant-width sidepods). The milled body is the
part behind Ref A (param_body.build(freeform=...), through the same masks and milling); the printed nose is
the same surfaces ahead of it, clipped to T8.5.1's box, T8.2's 40 mm and T3.7. Nothing outboard of the
12.5 mm spine between the wheels is over 27.175 mm (the team's sidepod top). `fit()` reads the surfaces
off any car (IoU 0.85 on L0044 at 24 x 9 x 12 control points), so stage 2 starts from the stage-1 car;
its nose is not the stage-1 cone but the body's own Ref A section carried forward and rounded off just ahead
of the front wing (`seed_nose`), the fields ahead of it empty but free.

`halo_seat.py` (user 2026-11-23: no recess, nothing blocking the halo, its whole face lofted to the
canister): the halo sits in what the 6.35 mm ball cuts round the OFFICIAL halo, 3.175 mm deep with the floor
at 24.0 (App. ix, T4.4.4) -- quarter-round walls that the halo's rounded base sits in, 0.1 mm off it, flush
at the rim. Air over its plan outline (T4.4.3); in front of it and beside it nothing above the rim up to its
top (T4.4.2, stricter than the rule's 4 mm fillet). One definition serves the coarse mask, the exact zones,
the exact cut and the pocket mask. The body must hold the loft: the halo's whole rear face (+0.3 mm) blended
into the T5.5 safety tube's circle at the chamber's front, required in the field and united exactly with the
mesh (the referee's `team_halo_face_joined`: all of the face above the rim has body behind it). No ceiling
over it. The void under the halo is App. ix's ballast container (the lead goes there).

### car/parts (was Part 4)
`assembly.build(...)`: the team's wheels (their measured files), the official halo in its pocket, the
nose cone lofted onto the body's front section, NACA 0015 front and rear wings at the minimum legal size,
tether guides on stalks, the wheel supports, and Part 4's own gates.

`support_engine.py` designs the searches' wheel supports for each car from that car's body (run_car
`--support engine`). One printed part per axle: a **saddle** flush with the underside (the body's lowest
`saddle_h` over a chord at the axle, milled away from below and printed instead; it follows steps in the
floor such as the front's centre channel, and wraps the body's rounded edge where less than 3 mm of foam
would be left), a **plate** from the body's side to the wheel whose underside continues the body's floor
(the form of the team's example car, 2026-11-23: it leaves the floor at the floor's own line and slope,
eases level within 2 mm and untwists level within 4 mm, so the underside has no step or kink; measured:
`fit_<axle>_flush_with_the_underside`), a concave **transition** into the **disc**, and the **axle** stub with its hubcap (the disc and
the axle are `beam_support.py`'s). The slot's ceiling is computed column by column and opened by the 3.175 mm
ball, so it is what the cutter can mill from below. Every rule and load is measured on the result:
T7.12.1 (inside the wheels' cylinder), T7.13 (claw band clear), T3.7, arm / saddle / stub / disc stress
and bearing sag (3 N radial, 1.2 N side, ABS 20 MPa allowed, 0.15 mm), foam bearing, 3 mm of foam over
the slot or none, slot cut from below, one closed solid. Thicknesses grow until the loads pass. Each car
folder gets `supports.png` (`search/layout/support_render.py`) to inspect the design.
`beam_support.py` (Part 4's pod/plate/strip support) is kept for the team's own car (`--support beam`).

`front_wing_engine.py` designs the searches' front wing: one piece across the centre line or a left and
a right wing (T8.6.1), flat NACA 0015 elements (chord, height, span, sweep, dihedral; swept by shearing so
every vertical cut is the true section), and its own supports: none (held by the nose it runs into), one
pylon on the centre line or two, each cast to the nose's surface and printed with the nose. It repairs
rather than refuses (sweep within T8.2's 40 mm, segments out to 25 mm, dihedral within T8.5.2 and the
track's 5 mm, roots into the nose, a wing lowered to keep 5 mm under a nose that does not hold it) and
measures every T8 rule. The referee measures it again (T8.5-T8.8).
`rear_wing_engine.py` designs the searches' rear wing and its supports, one representation with no modes
(user 2026-11-23): a NACA section (camber either way, angle of attack), span, chord, thickness, sweep and
dihedral, a lift over the lowest height T9.6 and T9.7 allow; and up to two strut pairs, each only continuous
numbers -- thickness (off under the print wall), where on the span and the chord, chord, rake, splay, root
(glued, or a slot this deep). Each strut is cast from the wing along its lean to whatever body is there (the
chamber's top, a sidepod, a rearpod); a slot is a plug the ball can cut, above the T5.5 wall with 3 mm of
foam round it, else glued; a strut that meets nothing is leaned back towards the vertical, else reported.
A tip swept into T7.9's full-height wheel zones is moved aft. Gates: T9.4.1-3, T9.5.1-4, T9.6 (but 5 mm
either side of each strut), T9.7, T3.4, the struts' wall, wheel and T7.9 clearance, the slots.
`joints.make_all` cuts pockets for the printed parts and writes the manufacturing files (skipped in
searches with `--no-joints`; rebuild finalists without it).

### car/build (was Part 5)

The referee measures every rule on every car. Without manufacturing files (the searches build with
`--no-joints`) the zone, visibility, clear-air, chamber, cargo, halo and block rules run on the car as drawn
(`legality.as_drawn_solids`); until 2026-11-23 they ran only on the made files, so search cars were never
measured against T7.9-T7.11, T8.7, T8.8, T9.6, T9.7. Two of them fail on every car of the 1 mm build grid for
the same reason as T5.1 (the bore drawn 0.6 mm small) and are waived only when that is all they are
(`layout_car._grid_bore`).
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
| T3.6 48.0 g | met by lead in the T1.22 container (up to its 15.8 g capacity, else refused) |
| T5.1 chamber diameter | the bore is the block's own drilled 18.1 mm; the 1 mm build grid draws it 0.6 mm small. Finalists are measured on the fine grid |

T9.4.2 (40 mm behind Ref B) is measured on the rear wing and its support only (team's reading,
2026-11-22); the body is limited by the 223 mm block.

## Files a car folder holds

`summary.json` (every check, mass), `layout_car.json` (genes, decoded numbers, verdict, mass with lead,
the supports' sizes, CFD solid report), `supports.png` (the supports, close up), `body_half.stl`, `parts/*.stl` + `assembly.json`, `body_full.stl` (the merged solid,
metres; reduced to 60k faces once timed), `wheelF.stl`/`wheelR.stl`/`wheels.json`, `run_car.log`.
