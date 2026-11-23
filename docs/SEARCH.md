# The searches

Every search scores a car by **race time** (the race model, with the car's own layout, mass and COM),
not by drag alone. A car that cannot be built or breaks a rule is never sent to CFD.

## Why two stages for the whole car

A CFD run costs roughly 20-25 core-hours, so a few hundred runs is the whole budget. Putting the layout
numbers and a free-form body into one evolution would need many hundreds of runs before it settled.
So the work is split by what each number is:

1. **Stage 1, layout (search/layout, Bayesian).** About ten numbers that place hard parts:
   wheelbase, rear axle -> rear face, halo -> rear face, cargo position and orientation, nose length,
   profile and tip height, front wing height, rear wing position. A Gaussian-process model of race time
   is fitted after every batch; every legal layout (66 934 on a 1 mm grid), each with several settings
   of the other numbers, is scored on the model, and only the 8 most promising are built and timed.
   The first 16 cars are space-filling (Sobol). Budget: 48 cars plus the reference twice.
2. **Stage 2, shape (search/shape, CMA-ES).** On the best layout from stage 1, everything else is designed
   freely: the body and nose (car/body/freeform.py: top, bottom and side surfaces, fitted to the stage-1
   car and moved by a coarse grid of displacements: 5 x 2 top, 5 x 4 bottom -- four across the floor, so it
   can form channels: a catamaran tunnel's two hulls and the raised centre between them --, 5 x 3 side, 6/4/6
   mm per unit),
   the front wing (straight: one piece or two, chord, gap, span, root) and the rear wing (straight: chord,
   thickness, half span, lift), their struts, swept out of the wings' sides to the nose / body (lean out / in,
   fore / aft, carry-out, carry-in, chord, thickness, flare, squareness: car/parts/wing_strut.py)
   and the wheel supports' plates (chord, thickness, taper, transition): 74 numbers. No support design is
   preset: every support number starts at the middle of its range and the search decides. The rule masks and the milling are applied after, so every vector is a legal, millable body;
   what a mask cannot force is measured and refused. CMA-ES, 8 cars a generation.
   The coarse grid is a setting (simscale_shape.COARSE): a finer grid is freer but needs more runs. With
   one key's worth (about 40 runs, 5 generations) CMA moves the car a few steps from the stage-1 car, not to
   an optimum in 51 dimensions; more runs buy more of it.

At equal drag the layout changes race time by only ~0.15 ms over its whole legal range (the car is
always ballasted to 48.2 g), while 1 % of drag is ~0.7 ms: the layout matters through drag, which is
why it needs CFD at all, and why the CFD noise sets what can be ranked. The noise is measured by
timing the reference twice with two different facetings of the same car (surface rebuilt on 0.3 and
0.25 mm grids).

The weakness: stage 1 ranks layouts with the default body. If the top layouts are within the noise,
take each into stage 2 rather than pick one.

## What is searched and what is fixed

`search/layout/layout_params.json` holds every number of the car (137), each `evolve` (a gene,
between `lo` and `hi`) or `fixed` (held at `value`); `python search/layout/layout_catalogue.py --md`
rewrites [PARAMETERS.md](PARAMETERS.md). The wings start at the flat NACA 0015 at the minimum legal
size (user 2026-11-22: low drag, low lift) and stage 2 evolves them and their supports from there.
Fixed by choice: the loft stations (set so the body meets the nose), the underfloor tunnel
(off), the 56 sculpt bumps (stage 2's lattice does that job). Fixed by the build: the thrust line
(31 mm), the team's wheels, the wheel track. The wheel supports are generated for every car
(car/parts/support_engine.py); what the air sees of them is evolved in stage 2, what it does not (the
saddle's depth inside the body, the disc inside the wheel) is sized for the loads or fixed.

CFD setups: a result is compared only with results of the same setup (`setup_key` in
simscale_layout.py: small-feature suppression, wheel rims, cartridge, supports). Cars timed before the
cartridge or the supports were added are brought over by the difference between the reference car's
runs with and without (`data()`); for the supports that shift is only approximately the same for every
layout, so those rows are provisional until a few of them are re-timed with supports.

The layout genes are decoded so that every vector lands inside these analytic limits (the referee still
judges each built car, and can refuse one: e.g. the rear wing crowding the cartridge, T5.6):

- `W` 120-140 (T7.3); `rear` 36 .. 207 - W (the 223 mm block, T1.14);
- `halo_rear` (pocket front -> rear face) in (max(rear + 50, 102), W + rear]: the pocket front on or
  behind the front axle, its rear ahead of the rear axle and of the 52 mm cartridge bore;
- `cargo_x` is a preference: Part 1 places the cargo at the legal position nearest it (wheel keep-clear
  zones, bore, halo pocket), keeping the wanted orientation when any position allows it.

## CFD setup

A result depends on the CFD setup as well as the car: small-feature suppression, wheel rim fillet,
the cartridge's shape, triangle count and the grid the surface was rebuilt on. Each SimScale case records its `setup`, every
timed row in `designs.jsonl` carries it, and the stage-1 model is fitted only on cars timed at the
current setup (0.8 mm suppression, 1 mm rim fillet). Cars from batch 0 meshed before the switch
(0.05 mm, sharp rims; 2026-11-22) are logged but not fitted; the reference was timed under both setups
(REF24000/REF32000 old, REFN30/REFP25 new), so the shift between setups is measured.

The cartridge in the CFD car is the official one (the shell and charge from
`car/body/hardware_cad`, base first in the 52 mm bore, its shoulder and 8.7 mm neck 13 mm out behind
the rear face), since 2026-11-22 17:50; before, an 18 mm cylinder. The cartridge is the same part on
every car, so results timed with the cylinder (at the same suppression and fillet) are brought over by
the difference between the reference timed both ways (REFN30 cylinder, REFC30 official); results from
the 0.05 mm setup are not used at all.

## The sidepod search (search/sidepod)

CMA-ES on the team car's own sidepods: the team STEP outside the sidepod region, a lattice field
inside it, milled with the same ball and walls, and nothing above 27.175 mm. Two runs side by side:
from the team's pod (`cma`, 105 cars, best 0.7558 s against the team car's 0.7532 s) and from no pod at
all (`cma_scratch2`, wider amplitude). Config: `search/sidepod/config.simscale.json`; results:
`search/sidepod/results/`.

## Reading results

`runs/<search>/designs.jsonl` has one or more rows per car (build verdict, then CFD and race time);
`state.json` the search's own state; `simscale_state.json` every SimScale case and key. The layout and
shape searches print `batch` lines with the model's length scales (a long length scale = the number
hardly matters) and noise.
