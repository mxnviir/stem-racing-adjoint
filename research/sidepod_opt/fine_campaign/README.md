# Fine-mesh campaign: re-test the conclusions, and the adjoint, on finer meshes

Why (ROUTES.md 2026-11-21): the adjoint design's −10 mN on the coarse mesh (~105 k cells) became about
−1.5 to −3 mN on the medium mesh (~522 k cells); control runs showed the cause is mesh resolution. Every
other conclusion so far was reached on coarse or medium meshes. This campaign re-tests them on `fine`
and `resolved` (~5 M cells, wall-resolved layers, y+ ≤ 2), and tests whether the adjoint works there.

Everything is resumable: a finished job leaves `prodcheck_<tag>.json` (or `bump_<k>.json` …) and is
skipped next time. Results go to `gate_results_<TAG>/` and `gate_results_<TAG>_up/` and are committed and
pushed after every job (`PUSH=0` to switch off). Run folders are deleted after the numbers are saved,
except the two base states the bumps and adjoint need (`gate/refA_<TAG>`, `gate/refA_<TAG>_up`).

## Machine

- OpenFOAM v2412 (`OF_BASHRC`), Python 3 with `part1-simulation/requirements.txt` (`PY`), Docker with the
  DAFoam image `dafoam/opt-packages:v5.1.1` (adjoint stages only). On an HPC system without Docker,
  `dafoam/run_docker.sh` must be swapped for Apptainer/Singularity.
- Sizes below are **extrapolated** from this repo's measurements until `stage0` measures them:
  - medium, 522 k cells: 2,000 iterations on 4 cores ≈ 32 min (measured);
  - resolved, ~5 M cells: ≈ 30 core-hours per run for 3,000 iterations (≈ 7 µs per cell-iteration-core,
    measured on medium), plus meshing with the layer stack: ~8 h on 4 cores, ~1–2 h on 32 cores;
  - forward-run memory: a few GB per million cells (fine; to be measured);
  - **adjoint memory: ~150 kB per cell** (coarse: colouring peaked at 14.4 GB for 105 k cells and the
    final product was killed on 16 GB; medium: colouring passed 40 GB at 520 k cells). So medium needs
    a **~128 GB** machine and resolved **~0.5–1 TB** (one big-memory node, or DAFoam across several MPI
    nodes). The `adjoint` stage refuses to start below the estimate (`FORCE_ADJOINT=1` overrides).

## Order (cheapest first; each step decides whether the next is worth paying for)

```bash
cd research/sidepod_opt
bash fine_campaign/campaign.sh cars                          # all test cars, rebuilt from code
RES=coarse NP=4 bash fine_campaign/campaign.sh bccheck       # DAFoam + wall-resolved boundary conditions (16 GB is enough)
RES=medium NP=16 bash fine_campaign/campaign.sh steady       # does the steady model go steady one step finer?
RES=medium NP=16 JOBS=3 bash fine_campaign/campaign.sh bumps
RES=medium NP=16 bash fine_campaign/campaign.sh adjoint      # needs ~128 GB
RES=medium bash fine_campaign/campaign.sh judge
RES=fine NP=16 bash fine_campaign/campaign.sh stage0         # STOP: read cells / y+ / memory / time
RES=fine NP=16 JOBS=4 bash fine_campaign/campaign.sh forward
RES=resolved NP=32 bash fine_campaign/campaign.sh stage0     # STOP: read it
RES=resolved NP=32 JOBS=2 bash fine_campaign/campaign.sh forward
RES=resolved NP=32 bash fine_campaign/campaign.sh steady     # only if medium's adjoint passed
RES=resolved NP=32 JOBS=3 bash fine_campaign/campaign.sh bumps
RES=resolved NP=64 bash fine_campaign/campaign.sh adjoint    # ~0.5–1 TB
RES=resolved bash fine_campaign/campaign.sh judge
RES=<res> bash fine_campaign/campaign.sh summary             # -> fine_campaign/SUMMARY_<res>.md
```

Keep `NP` the same for every run of one comparison, and record it (it is written into every result).

## The 18 forward runs per mesh

team ×3, groove ×3, adjoint design 8 ×3, 3 windows ×2, no pod ×2, blend 50 % ×2, blend 75 % ×2, 5 windows ×1.
A repeat is the **identical car** on a mesh whose frame is shifted by k × 0.37 mm in x (tag `<design>~k`,
`GATE_DOMAIN_DX_MM`): the mesher cuts different cells around the same surface, so mesh-to-mesh noise is measured
for each design. (The `_p05` / `_m05` cars that `make_cars.py` also writes nudge the design field by 0.05 mm;
through the 1 mm voxel builder that moves parts of the surface by 0.2–1.5 mm, so they are different designs, not
repeats: ROUTES.md 2026-11-21 16:05. They are kept only to reproduce the earlier medium runs.)
Clean medium noise: σ = 0.75 mN.

## Pass marks (fixed in ROUTES.md 2026-11-21 13:00, before any fine or resolved result)

SE = pooled mesh-to-mesh sigma × √(1/n₁ + 1/n₂), sigma never below 0.3 mN.

| mark | question | passes if |
|---|---|---|
| M1 | is medium adequate for scoring designs? | team body drag within 3 mN of medium, and every design's difference vs the team pod within max(2 mN, 3 SE) of medium's |
| M2 | can a single run score a design? | pooled sigma ≤ 2 mN |
| C1 | a pod beats no pod | no pod ≥ +15 mN |
| C2 | the valley between no pod and pod (drove the "global search" decision) | blend 50 % worse than no pod by > 3 SE |
| C3 | the groove helps | groove < −3 SE |
| C4 | windows don't help | 3 windows not better than −3 SE |
| C5 | the coarse adjoint design has no real gain | design 8 not better than −3 SE |
| A1 | the steady model goes steady (the adjoint needs it) | 100-iteration block means span ≤ 0.10 mN over the last 1,000 iterations |
| A2 | the adjoint matches measured bumps | as on coarse: r ≥ 0.9, signs agree on every pair above 3 sigma |
| BC | DAFoam accepts the wall-resolved boundary conditions | DAFoam's primal within 2 % of the pipeline's drag |

## Files

`campaign.sh` (launcher), `make_cars.py` (test cars from code; `--check` compares with local runs),
`steady_base.py` (steady-model continuation + mark A1), `summarize.py` (tables + marks M1–C5, A1).
Changed elsewhere: `prodcheck.py` (PRODCHECK_ITERS/TIMEOUT/KEEP/RESULTS/WALL_RESOLVED, cells and y+
recorded), `gate.py` (GATE_ITERS_BASE/ITERS/TIMEOUT/REF/WALL_RESOLVED), `dafoam/runScript.py`
(DAF_PRIMAL_ONLY).
