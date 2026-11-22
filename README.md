# STEM Racing car optimiser

Designs a STEM Racing Professional Class car (2026-27 regulations) by evolution: every candidate is
built as a real, legal, millable car, timed in CFD on SimScale, and scored by race time.

```
car/            the car builder: one set of numbers -> a whole legal car
  body/           the milled body (layout, rule masks, loft, 3.175 mm ball milling, mass)
  race/           the race-time model (thrust curve, mass and COM, pitch, wheel friction)
  parts/          nose cone, wings, wheels, halo, tether guides, supports, glue joints
  build/          run_car.py (build one car) and legality.py (the scrutineer's checks)
cfd/            the SimScale route: one closed solid -> air volume -> mesh -> run -> forces
search/         the three searches
  sidepod/        CMA-ES on the team car's sidepods (the team's own CAD outside them)
  layout/         stage 1: wheelbase, tail, halo, cargo, nose, wing position (Bayesian, surrogate model)
  shape/          stage 2: free-form body on the best layout (CMA-ES on a control lattice)
docs/           how it works, how to run it, the rules map, every parameter
repo_paths.py   puts every code folder on sys.path (modules import each other by name)
```

Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (what each piece does and how a car flows
through them), then [docs/RUNBOOK.md](docs/RUNBOOK.md) (set up, run, resume, monitor).
[docs/SEARCH.md](docs/SEARCH.md) explains the three searches and why they are built the way they are.
[docs/RULES.md](docs/RULES.md) maps every regulation to its check; [docs/PARAMETERS.md](docs/PARAMETERS.md)
lists every number of the car and whether the search moves it.

Status: the race times are model numbers (CFD drag on a model of the car, a calibrated race model),
not track measurements. The regulations PDF is not included: get it from the organisers.

No licence is granted. All rights reserved.
