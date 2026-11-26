# Seed evolution: test report and campaign go/no-go (2026-11-26)

All verdicts and numbers are in `SEED_EVOLUTION_RESULTS.md`; the marks were fixed in `SEED_EVOLUTION_PLAN.md` before each
run. This page is the summary.

## What passed

| Test | What it checks | Result |
|---|---|---|
| T0 / T0b | seeds ingest from STL; all 9 operators make legal, varied children | pass (after making 4 operators bolder) |
| TP | plumbing on coarse CFD (team drag 449.24 mN reproduced, ESI steps accepted) | pass |
| T3a, TFb, TFc, TS (bench) | evolution beats the reference on the toy; screening helps; final selection works | pass |
| TW | campaign workflow on Actions: rebuild from field, fresh mesh, score, commit, next batch | pass (after one fix) |
| T1 / I1 | wall layers on >= 50 % of wall faces | pass (59.6-62.0 %) |
| T1 / I2 | mesh-to-mesh noise | production 0.57 mN: **one run scores a design**; steady 1.42 mN (needs duels) |
| TR1, TR3 | coarse DAFoam trusted on the team pod; its step beats random steps | pass: along -2.64 mN, against +3.39, random +0.03 / -0.30 |

## What failed, and what it means

- **TR2 (adjoint on shapes unlike the team pod): fail, for lack of a gradient, not a wrong one.** Coarse DAFoam converged
  on 1 of 6 attempts today: the channel seed stalled (GMRES flat at 8.4e-4), and the slotted and windowed seeds lost
  their runner twice each, 100-140 minutes into the adjoint. As registered: the end polish is gradient-free on shapes
  unlike the team pod; the adjoint is used only where its own per-design check passes.
- Where it did converge, the gradient points the right way and overstates the gain about 2.5x (predicted -7.5 mN,
  measured -2.6), as in the hybrid loop. The trust check measures every step with CFD, so that is handled.
- Bench T3b, T3c, T3e', TFa, TC2 failed as registered. In short: evolution is reliably better than the reference on
  average (TFb, TS) but not on every seed (TFa), and the adjoint helps most near the end, not as a breeding signal.
- Reported, to check: on the same mesh, random 0.5 mm morph moves lowered drag on all three new seeds (0.1-1.7 mN).
  Campaign scores use a fresh mesh per design, so this does not touch them; it matters only for sub-2 mN morph claims.

## Fixed along the way (all committed)

- The OpenFOAM package mirror served truncated files; workflows now install from checksum-pinned packages on named
  mirrors, cached between jobs.
- The campaign workflow takes its run mode from the campaign's score key; ingest stops on a mismatch.
- Production scores leave out the cold-start transient (iterations 200-1000): single-run noise 5 mN -> 0.15 mN.
- Probe jobs need the adjoint file only for moves that use it.

## Recommended campaign (needs your go-ahead)

- Score: production scheme, one run per design on a fresh wall-resolved mesh (2.1 M cells, ~2.2 h on a runner).
  No steady continuation.
- Breeding: the 9 operators, MAP-Elites archive (volume x through-openings), model-screened batches (GP + expected
  improvement), 16 explore + 4 control per batch, duel rule of amendment B for close calls.
- Adjoint: end polish only, behind the per-design trust check; gradient-free polish where DAFoam does not converge
  or is not trusted.
- Seeds: the four here plus the seed set you provide (STL).
- Cost and time: about 250 runs (plan, section 6) on up to 20 runners at once: about 13 batches of ~2.5 h, so
  **about 32 hours** back to back in auto mode, plus one run per extra seed in the census. The repository is public,
  so standard runners cost nothing.

## Open decisions (yours)

1. Launch the campaign as above? With which seeds?
2. DAFoam lost runners: (a) larger paid runners, (b) one retry with fewer MPI ranks / smaller GMRES restart, or
   (c) accept gradient-free polish where it fails.
3. Retry the channel seed's adjoint with a stronger preconditioner, or leave it refused.
4. Spend ~6 runs to check the same-mesh morph bias before the end polish relies on it.
