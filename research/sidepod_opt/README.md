# sidepod_opt: organic sidepod search, production version

**Start here: [HANDOVER.md](HANDOVER.md) (whole project, current state) and [DECISIONS.md](DECISIONS.md).** Lab log of the free-form search: [ROUTES.md](ROUTES.md). Hand-off for a local agent that runs it on Codespaces: [HANDOFF_LOCAL.md](HANDOFF_LOCAL.md).**

Finds the fastest **sidepod** for a fixed car: you give the STEP and the region, it searches
organic shapes, makes each one exactly as the CNC would, times it with real CFD, and scores it on
**race time** with Part 2's race model. Nothing outside the region is ever changed.

This replaces `research/sidepod_region` (the 3 mm test bench). That bench's low-Reynolds
lattice-Boltzmann tunnel and its differentiable copy are **removed**: they ranked sidepods wrongly
(Re ~2×10³ against the car's ~2.7×10⁵). Every car here is timed by full-Reynolds RANS only:
OpenFOAM (local or on Actions) or SimScale.

## How a design becomes a timed car

1. **Field**: a method proposes a field over the region (foam where it's positive). It is a
   *whole* shape each time: any method can add and remove material anywhere in the region.
   Methods may start from the team's sidepod (`original`), from none (`lean`, cargo only), or
   anywhere between (`blend`). The first bench only started from the box and could never reach
   "no sidepod".
2. **Finish** (`geometry.py`, 1 mm grid of the STEP)
   - forced air: the T7.9.2 and T7.9.3 wheel wedges, and above 27 mm beside the halo (T4.4.2)
   - forced foam: the T4.2 cargo wedge
   - locked: the spine zone (deck, cockpit, halo pocket), **air included**, copied from the STEP
3. **Mill**: Part 1's own machining rule (team process: 3-axis, 6.35 mm ball end, setups top,
   bottom, left and right).
   - air the cutter can't clear stays foam
   - sealed voids stay foam
   - loose pieces are dropped
4. **Check**: the car is never timed unless all of these hold.
   - one piece
   - nothing changed outside the region
   - no foam in forced air
   - the cargo is inside the body
   - ≥ 1.5 mm off the track (T3.7)
5. **Weigh**: exact foam mass and COM from the milled 1 mm body.
   - A light car gets lead in the T1.22 container up to 48.2 g (T3.6 floor plus margin).
   - A heavy car simply pays for it: there is no upper limit.
   - Needing more lead than fits makes the car illegal.
   - The race model's mass includes the empty cartridge shell (21.15 g), as in Part 2.
6. **Export**: `cars/<id>/`, in the same folder format as Part 2's stopwatch.
   - `car_half.stl` (solid `car`, m, x from the nose, y ≥ 0, closed at y = 0)
   - `wheelF.stl` and `wheelR.stl` (rotating, sunk 0.3 mm as in Part 4)
   - `assembly.json`, `mass_report.json`
   - `body_full.stl` (whole body, for SimScale and the CNC)
7. **Time**: an evaluator returns D20 and L20 (see below). `objective.py` turns them into race time
   with Part 2's race model, using this car's axles, thrust line and guides, the measured thrust
   sheet and the 0.802 calibration.

**Rates for the trial car** (original, D20 0.39 N):
- **Drag:** 0.18 ms per mN.
- **Weight:** 7.5 ms per gram over 48.2 g.
- **COM:** no effect (the thrust never lifts a wheel pair here).

So at the floor weight the sidepod question is a drag question. The first bench used an older
thrust sheet that gave the COM a large effect; that was wrong.

## Methods (`methods.py`): every one is batch ask/tell

| name | representation | how it moves | needs |
|---|---|---|---|
| `cma` | lattice | CMA-ES | any |
| `bo` | lattice | GP + expected improvement in a trust region; **multi-fidelity**: cheaper results enter as a second fidelity | any |
| `sail` | lattice | MAP-Elites on the GP (foam volume × pod height); returns several *different* good pods | any |
| `neat` | CPPN (x, \|y\|, z, distance to cargo, original and lean shapes) | NEAT, seeded with 6 hand networks | any |
| `spsa` | level set, 2 mm (≈18 k variables) or lattice | gradient from ± perturbations, 2 runs per step | any |
| `adjoint` | level set | exact race-time gradient: adjoint aero + exact mass and COM | `adjoint` evaluator, **after the gate passes** |

## Evaluators (`evaluators.py`)

| kind | what | cost | status |
|---|---|---|---|
| `openfoam` | Part 2's pipeline on this machine (snappyHexMesh + kOmegaSST, rolling road, rotating wheels), both frozen states | medium: 38 min on 4 cores fresh, ~80 min on 2 cores on the morph path (measured on the trial car) | uses Part 2 code unchanged; run here on the trial car (`gate.py`) |
| `actions` | the same OpenFOAM job on GitHub Actions (`.github/workflows/sidepod_eval.yml`), any number of repos. The batch goes up as a release asset (nothing committed); one job per car group **and** frozen state (each state gets its own 6 h limit); collect is idempotent and a failed job comes back as a failed car | parallel | dry run and mocked `gh` tested; real dispatch not run |
| `simscale` | SimScale API, cloned from one template simulation set up in the web UI; face references re-mapped by solid name. Each car walks import → mesh → run in a state file, so cron ticks never block and survive restarts; a cost cap per car | per SimScale's pricing | calls checked against the SDK source; state machine and a whole campaign loop tested with a mocked SDK (`test_simscale.py`); **not yet run against SimScale**. Setup: `SIMSCALE.md`, config `config.simscale.json` |
| `adjoint` | OpenFOAM adjoint (Part 2's ESI path, or DAFoam), per-vertex drag sensitivity → race-time gradient on the field | ~2 primal runs | ESI failed Part 3's wing test. Must pass `gate-adjoint` first |

**SimScale:** good for every derivative-free method (`cma`, `bo`, `sail`, `neat`,
`spsa`). It has no adjoint. Use its k-omega SST (RANS) solver, the same model as OpenFOAM.

**Frozen states:** `campaign.py make-refs <dir> medium` builds states A and B of this car's
original. Your existing frozen states are of the repo car and are not valid here.
- **Small changes** (`mode: morph`): reshape the reference mesh. This is the 0.09 ms noise path,
  but it only holds for shapes close to the original.
- **Big organic changes** (`mode: warm`): a fresh mesh with the reference flow mapped in. Expect
  the fresh-mesh noise Part 2 measured (several ms).
- **`auto`** tries morph first and falls back to warm.

## Campaign (`campaign.py`, `config.example.json`)

| stage | what | budget (cars) | why |
|---|---|---|---|
| search | BO and SAIL on OpenFOAM medium, {original, lean} starts | 60 per run, 120 | the real search |
| fine | best 6 at the fine mesh, both states | 6 | — |
| gate_medium | Spearman ≥ 0.8 between medium and fine | 0 | — |
| polish | SPSA level set (or adjoint after `gate-adjoint` passes) on fine | 30 | final local shape |
| confirm | best 2 at the resolved mesh | 2 | then URANS (Part 2 `transient.py`) for the wake state, and a printed car on the track |

At your stated 15–25 fine-run equivalents a day (medium ≈ 1/6 fine), the OpenFOAM stages come to
about 2 weeks.

## Run it

```bash
pip install numpy scipy scikit-image trimesh numba cma neat-python scikit-learn jax cadquery-ocp
python campaign.py init  runs/trial config.example.json      # voxelises the STEP once (~30 s)
python campaign.py run   runs/trial                         # local evaluators: loops to the end
python campaign.py report runs/trial                        # runs.md, convergence.png, best.png, best/<car folders>
# remote evaluators (actions / simscale): run `tick` from cron; each call collects, tells, asks, submits
python campaign.py tick  runs/real
```

**Changing the car or region:** edit `CarSpec` in `geometry.py` (or override it in the config
under `"car"`). The region box, spine lock, halo cap, cargo position, lead container, part masses
and thrust line are all there.

## Assumed, to confirm with the team

- **Cargo position:** z 17–27 mm, wide end forward, x 76–136. That is the layer where the trial
  car is solid across its full width, which keeps its tunnel free.
- **Part masses:** non-body parts = 48.2 g minus the drawn body's foam, with their COM
  mid-wheelbase at z 16 mm.
- **Thrust line:** z 30 mm; the cartridge sticks out 13 mm (the STEP has no bore).
- **Lead container:** at x 130, z 21 mm.

## What was tested here (2026-11-19)

- **Geometry, milling, checks, weighing and STL export** (`car_half.stl`, wheels, `body_full.stl`
  all watertight; the half-car volume is exactly half the whole) on the trial car.
- An earlier end-to-end campaign ran on the LBM tunnel; that tunnel is now removed, and the
  campaign has **not** been re-run end to end on OpenFOAM yet.
- **Actions dry run**: batch written, `eval_one.py` run, results collected.
- **OpenFOAM on the trial car** (`gate.py`, results in `gate_results/`): the original converged
  at D20 0.366 N (whole car), and the adjoint accuracy test is running.
- **Not run:** SimScale (no access from here).
