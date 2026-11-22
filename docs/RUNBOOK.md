# Runbook

All commands from the repo root. Run state lives in `runs/` (not in git).

## Set up

```
pip install -r requirements.txt
pip install git+https://github.com/SimScaleGmbH/simscale-python-sdk.git@19.1.0
export SIMSCALE_API_KEYS='key1,key2,key3'      # never in a file in the repo; used in this order
```

A whole-car build peaks at ~5.5 GB of memory; the searches build 3 at a time (`BUILD_WORKERS` in
`search/layout/simscale_layout.py`). The sidepod search needs ~11 GB of disk over a campaign: finished
cars' CAD files are only needed while their case is on SimScale.

## Build and check one car (no CFD)

```
python search/layout/layout_car.py /tmp/car                 # the team layout (every gene at its default)
python search/layout/layout_render.py /tmp/car /tmp/car.png --cfd   # pictures of the solid that goes to CFD
```

`/tmp/car/layout_car.json` says whether it is legal, what failed, its mass with lead, the wheel supports'
sizes, and the CFD solid report (`one_piece`, `watertight`, distance from the built car). `run_car.log`
and `summary.json` hold every check with its margin. `supports.png` shows the car's wheel supports close
up (section through each axle, along the arm, from below, and the part alone):

```
python search/layout/support_render.py /tmp/car /tmp/supports.png
```

## Stage 1: the layout search

```
python search/layout/simscale_layout.py init runs/layout --budget 48
setsid nohup python -W ignore search/layout/simscale_layout.py run runs/layout >> runs/layout/run.log 2>&1 &
python search/layout/simscale_layout.py status runs/layout
```

The first tick submits the reference (the team layout) twice: as is, and with its CFD surface rebuilt on
a 0.25 mm grid instead of 0.3 mm (a different faceting of the same car), so the difference between the
two is the route's noise; then it builds the first 8 cars. `simscale_layout.py noise runs/layout` adds
another such copy (stop `run` first). `run` ticks once a minute: builds the batch it asked for, moves every SimScale case along, logs
results, and asks the next batch once the last one is back. Stop it at any time (`pkill -f
simscale_layout.py`) and start it again: everything is in `runs/layout/state.json`,
`simscale_state.json` and `designs.jsonl`. A batch whose builds were interrupted is rebuilt.

## Stage 2: the shape search

```
python search/shape/simscale_shape.py init runs/shape --from runs/layout [--car L0012] --budget 40
setsid nohup python -W ignore search/shape/simscale_shape.py run runs/shape >> runs/shape/run.log 2>&1 &
```

Takes the fastest car of stage 1 (or `--car`), times it once with no change (`BASE`), then runs CMA on
the lattice.

## The sidepod search

```
python search/sidepod/campaign.py init runs/sidepod search/sidepod/config.simscale.json
setsid nohup python -W ignore search/sidepod/campaign.py run runs/sidepod >> runs/sidepod/run.log 2>&1 &
python search/sidepod/campaign.py status runs/sidepod
python search/sidepod/campaign.py report runs/sidepod
```

## Keys

Each search keeps its own key state in `simscale_state.json` (seeded from the sidepod run's, so a
retired key stays retired). A key is retired when SimScale answers 402/403 or says it is out of
core-hours; its unfinished cases move to the next key, and an event is written to `events` in that
file. Each run costs roughly 20-25 core-hours (4-5 M cells).

## Watching a run

- `runs/<search>/run.log`: one line a minute; `batch` lines carry what the model asked and why.
- `simscale_state.json`: per case `phase` (wait, step, import, mesh, run), `attempt` (which triangle
  count of the ladder), `tries` (why an attempt failed), `cells`, `cost_estimate`.
- A case retries an import or mesh failure at the next triangle count (`CAR_FACES` in
  `simscale_layout.py`: 24 000, 32 000, 40 000 ...) and is dropped after the ladder.

## Meshing (whole-car searches)

The whole car goes to SimScale as one faceted solid: every triangle is a CAD face and every triangle
edge a CAD edge. What makes that mesh, found on 2026-11-22:

- **Small-feature suppression 0.8 mm** (`SMALL_FEATURE_MM` in `search/layout/simscale_layout.py`, the
  smallest cell size). At SimScale's 0.05 mm the mesher failed on 5 of 9 cars ("mesh too coarse",
  "size smaller than tolerance"), and on the reference at 24 000 and 32 000 triangles; at 0.3 mm too.
  At 0.8 mm the reference meshed first time (5.0 M cells).
- **A clean surface** (`cfd/layout_wrap.py`): rebuilt on a 0.3 mm grid, so no slivers, ledges or
  needle triangles; checked closed and free of self-intersections before upload.
- **Wheels as exact solids with rounded rims**, 0.15 mm above the road.

If a case still fails, it retries at the next triangle count and is dropped after the ladder; the
reason is in its `tries`. A run that crashes on its first iterations ("check mesh or numerics") costs
a run: watch for a pattern.

## Tests

```
python -m pytest car/race/tests car/parts/tests car/build/tests car/body/tests search/sidepod cfd -q
```

Part of `car/build/tests` and `car/parts/tests` builds whole cars and takes an hour or more.
`cfd/test_simscale.py` checks the SimScale route without SimScale: a toy car through the surface
rebuild and the air volume, the diverged-force filter, and key retirement.
