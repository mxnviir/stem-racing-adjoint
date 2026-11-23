# Normal-adjoint test on a 4–5 M-cell wall-resolved mesh: instructions for the local agent

**One sentence:** run `esi/run_resolved_test.sh`, which checks whether OpenFOAM's own (ESI, "normal",
continuous) adjoint predicts the measured effect of six small bumps on the car when the mesh resolves the
boundary layer, and report its verdict.

## Why this test exists (read this first)

- The project needs an adjoint (a drag gradient over the whole surface) to polish free-form sidepods.
  DAFoam's discrete adjoint is accurate here (it predicts 66–109 % of measured bump effects) but needs
  ~150 kB of memory per cell: ~128 GB for the medium mesh, ~0.5–1 TB for 5 M cells. The owner wants a
  normal adjoint instead, whose memory is a few times a forward run's.
- On the coarse mesh with **no boundary-layer cells** (wall functions on 2.8–5.6 mm cells, y+ up to 180),
  the normal adjoint got every sign right but only **2–25 % of the size**, unevenly by site
  (`gate_results_coarse_up/esi/`, ROUTES.md 2026-11-21 14:10 and 15:15). Already ruled out: turbulence
  (frozen vs full SST adjoint agree to 1 %), Reynolds number (same flow where DAFoam matches), ESI's
  grid-sensitivity terms (turning them on made it worse; turning off the wall damping crashed it).
- **Leading suspect: the near-wall mesh.** This test gives the adjoint a wall-resolved mesh. The cloud
  session runs the same test on a coarse mesh with layers (`gate_results_coarsewr_up/`); this one is the
  ~5 M-cell version.

## What it runs (one command does all of it; resumable)

| step | what | approx. on 4 cores (owner: a 5 M run takes 1–2 h) |
|---|---|---|
| 1a | production base: half car, 20 m/s, k-ω SST, rolling road, rotating wheels, `resolved` mesh, cold start, 3,000 iterations | 2–3 h incl. meshing |
| 1b | steady continuation: first-order upwind U, 3,000 more iterations; **mark A1**: 100-iteration block means of drag span ≤ 0.10 mN over the last 1,000 | 1.5–2 h |
| 2 | six ±1 mm Gaussian bumps (10 mm radius) at pod_rear, pod_front_low, pod_rear_top: the steady mesh reshaped onto each, warm start, 1,500 iterations | 6 × 1–1.5 h |
| 3 | ESI `adjointOptimisationFoam` on the steady state's exact mesh and flow: frozen turbulence, then full SST adjoint (3,000 adjoint iterations each) | 2 × 1–2 h |
| 4 | verdict | seconds |

Total roughly 12–20 h on 4 cores. **Mesh:** Part 2 `resolved`: background cell 22.5 mm, every wall at
level 5 (~0.7 mm; wheels ~0.35 mm), ~11 prism layers from a 15 µm first layer (growth 1.3, last layer a
quarter of the wall cell), target y+ ≤ 2, wake boxes. ~4–5 M cells (measured and printed in step 1).

## Machine and setup

1. **Linux.** Native Ubuntu, or WSL2 Ubuntu 24.04 on Windows. In WSL, clone into the Linux home
   (`~/`), never under `/mnt/c` (very slow). Give WSL enough memory: `%UserProfile%\.wslconfig` with
   `[wsl2]` `memory=<most of your RAM>GB` `swap=32GB`, then `wsl --shutdown` and reopen.
2. **Memory and disk:** RAM + swap ≥ 24 GB (meshing 5 M cells with layers is the peak; the ESI adjoint is
   a few times a forward run). ≥ 40 GB free disk (the script stops below that).
3. **OpenFOAM v2412 (ESI):**
   `curl -s https://dl.openfoam.com/add-debian-repo.sh | sudo bash && sudo apt-get install -y openfoam2412-default`
4. **Code:** `git clone https://github.com/mxnviir/stem-racing-paper.git && cd stem-racing-paper &&
   git checkout claude/dazzling-ritchie-3q792g && git pull` (pull again right before starting: fixes found
   by the cloud run land on this branch).
5. **Python 3.11+ venv:** `python3 -m venv ~/venv && ~/venv/bin/pip install -r part1-simulation/requirements.txt`

## Run

```bash
cd stem-racing-paper
source /usr/lib/openfoam/openfoam2412/etc/bashrc
nohup env NP=4 PY=$HOME/venv/bin/python bash research/sidepod_opt/esi/run_resolved_test.sh > resolved_test.out 2>&1 &
tail -f research/sidepod_opt/gate/resolved_test.log
```

- `NP` = physical cores to use. Keep the same `NP` for the whole test.
- It is **resumable**: after a crash, reboot or Ctrl-C, run the same command; finished steps are skipped.
- Add `PUSH=1` to commit and push the results to the branch at the end (never to `main`).

## Layer check first (mark L)

The whole point is a wall-resolved mesh, so after step 1 the script reads snappyHexMesh's
`Extruding X out of Y faces (P%)` and **stops if fewer than 50 % of wall faces got layers**. Why it
matters: on the 2.8 mm coarse walls the stack formed on **0 of 5,666 faces** (2026-11-21 15:30), and Part 2
measured y+ ≤ 2 on only 57 % of the body faces of this resolved mesh (`openfoam_case.py`, 2026-09-30). If
mark L fails, report the coverage and stop; the adjoint verdict would not answer the question.

## Pass marks (fixed before any result; do not change them)

For each ESI version (frozen, sst): **PASS** only if Pearson r ≥ 0.9, every sign agrees, and
predicted/measured is between 0.5 and 2 at all three sites. The script prints this as
`gate_results_resolved_up/esi/VERDICT.txt`.

| outcome | meaning |
|---|---|
| PASS | the normal adjoint works on wall-resolved meshes; it can drive the free-form pod loop at a few times a forward run's memory |
| signs right, sizes still far off | wall resolution is not enough: next suspects are overall resolution and the adjoint's wall damping (ATC); report, don't tune |
| A1 FAIL (step 1 stops) | the steady model doesn't go steady on this mesh: the adjoint can't be judged here; report the block means |
| a bump `morph_fallback: true` | reshaping the layered mesh failed for that bump; that pair is unusable; report which |
| ESI crash (SIGFPE in `adjointkOmegaSST`) | report it; the frozen result still counts on its own |

## Reshaping the layered mesh onto the bumps (rule added 2026-11-23, before the bump rerun)

The first CI bump run (inverseDistance morph, the Part 2 default) failed checkMesh on all six bumps
(2-12 inverted wall-layer cells where counted) and every one fell back to a fresh mesh, so no usable
pair was left. Owner's ruling for this test only:

1. The bumps are morphed with `diffusivity quadratic inverseDistance (car)` (opt-in:
   `P2_MORPH_DIFFUSIVITY`; Part 2's default stays `inverseDistance`), so the thin layer cells ride
   with the wall.
2. Strict: a morph whose checkMesh is not `Mesh OK` stops that bump with an error
   (`P2_MORPH_STRICT=1`); no fresh-mesh fallback.
3. Accepted only if checkMesh says `Mesh OK` for both `pod_front_low` (+1 mm) and `pod_front_low_m`
   (-1 mm) in a morph-only test first; then all six bumps are re-run with it. The adjoints are not
   re-run (their state is unchanged).
4. If quadratic still inverts cells on any bump: keep the 1 mm height and widen the footprint of
   all six bumps together, Gaussian radius 10 mm -> 15 mm, then 20 mm; stop at 20 mm and report a
   morph failure if it still fails. The predictions for the new shapes come from the existing
   sensitivities (`pair_judge.py` integrates `esi_sens_*.npz` against the new bump surfaces); no
   adjoint re-run. The pass marks above do not change.

**Outcome (2026-11-23): morph failure.** Rule 3's test failed (quadratic: 50 and 5 inverted cells on
the pod_front_low pair), so no bump was re-run. Testing found a separate defect and fixed it: the
morph measured the shape change from the surface state A was snapped to (`gate/original`), not from
the bumps' base (`original_rm`); the two differ by up to 0.2 mm, which a no-bump morph pushed into
the 15 um layer. With that fixed (opt-in `GATE_MORPH_REF_RM=1`) a no-bump morph moves nothing and is
`Mesh OK`, but the registered bumps still fold layer cells at 10 mm, and rule 4's 15 mm and 20 mm
footprints are worse at all three sites under both diffusivities. Only `tail_side` (not registered)
morphs cleanly at both signs. The bump check cannot be made on this mesh by morphing; the verdict is
inconclusive, not an adjoint failure. Full checkMesh tables: ROUTES.md, 2026-11-23.

## Report back (to the owner, and append a dated entry to `research/sidepod_opt/ROUTES.md`)

1. Mesh: cells, y+ min/max, and the layer coverage line (`Extruding X out of Y faces`).
2. Production and steady drag; the A1 block span.
3. The six bump drags and the three measured half-differences with their stderr.
4. `VERDICT.txt` for frozen and sst.
5. Peak memory and wall time per step (`gate_results_resolved*/resources_*.json`).

## Rules

- Never change a pass mark, iteration count or tolerance to turn a FAIL into a PASS. A failure is reported
  with its cause.
- Never push to `main`; never paste or print tokens.
- If something breaks, fix the cause, write it in ROUTES.md, and re-run the same command.

## Files (all on the branch; the zip holds copies for reading)

`esi/run_resolved_test.sh` (driver), `esi/esi_on_state.py` (ESI adjoint on an existing state),
`fine_campaign/campaign.sh` (`steady`, `bumps` stages), `fine_campaign/steady_base.py` (steady
continuation + A1), `prodcheck.py`, `gate.py` (bump geometry, solves), `dafoam/pair_judge.py` (judge).
