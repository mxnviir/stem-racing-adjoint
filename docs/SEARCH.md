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
2. **Stage 2, shape (search/shape, CMA-ES).** On the best layout from stage 1, a lattice of 4 x 2 x 3
   control points over the body (mirrored), cubic-interpolated, grows or cuts the drawn body by up to
   +-6 mm per unit before the rule masks and the milling are applied. So every vector is a legal,
   millable body. CMA-ES, 8 cars a generation, 40 cars.

At equal drag the layout changes race time by only ~0.15 ms over its whole legal range (the car is
always ballasted to 48.2 g), while 1 % of drag is ~0.7 ms: the layout matters through drag, which is
why it needs CFD at all, and why the CFD noise (measured by the reference twice) sets what can be ranked.

The weakness: stage 1 ranks layouts with the default body. If the top layouts are within the noise,
take each into stage 2 rather than pick one.

## What is searched and what is fixed

`search/layout/layout_params.json` holds every number of the car (137), each `evolve` (a gene,
between `lo` and `hi`) or `fixed` (held at `value`); `python search/layout/layout_catalogue.py --md`
rewrites [PARAMETERS.md](PARAMETERS.md). Fixed by choice: flat NACA 0015 wings at the minimum legal
size (low drag, low lift), the loft stations (set so the body meets the nose), the underfloor tunnel
(off), the 56 sculpt bumps (stage 2's lattice does that job). Fixed by the build: the thrust line
(31 mm), the team's wheels, the wheel track.

The layout genes are decoded so that every vector is a legal layout:

- `W` 120-140 (T7.3); `rear` 36 .. 207 - W (the 223 mm block, T1.14);
- `halo_rear` (pocket front -> rear face) in (max(rear + 50, 102), W + rear]: the pocket front on or
  behind the front axle, its rear ahead of the rear axle and of the 52 mm cartridge bore;
- `cargo_x` is a preference: Part 1 places the cargo at the legal position nearest it (wheel keep-clear
  zones, bore, halo pocket), keeping the wanted orientation when any position allows it.

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
