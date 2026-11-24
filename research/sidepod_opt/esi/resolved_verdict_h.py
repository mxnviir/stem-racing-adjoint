"""Verdict of the wall-resolved normal-adjoint test with the amended bump heights (RESOLVED_TEST.md,
amendment 2026-11-24). Run from research/sidepod_opt after the resolved_bumps results are on the branch:
    python esi/resolved_verdict_h.py            -> gate_results_resolved_up/esi/VERDICT_h.txt (+ .json)

Measured drag of a bump run: mean of total drag (forces.dat column 1) over the last 404 iterations
(4 x the ~101-iteration cycle); SE = sd of the four 101-iteration block means / 2; half-difference SE =
0.5 * sqrt(SE+^2 + SE-^2). Predicted: the ESI sensitivities applied to the bump STLs (same mapping as
dafoam/pair_judge.py). Marks unchanged: r >= 0.9, every sign agrees, predicted/measured within 0.5-2 at
all three sites; any pair below 3 SE -> inconclusive."""
import json, re, sys
from pathlib import Path
import numpy as np
import trimesh
sys.path.insert(0, 'dafoam')
from pair_judge import displacement_at  # noqa: E402

R = Path('gate_results_resolved_up')
PAIRS = [('pod_rear', 'pod_rear_h05'), ('pod_rear_top', 'pod_rear_top_h05'), ('pod_front_low', 'pod_front_low_h025')]
BLOCK, NB = 101, 4


def measured(name):
    f = R / 'forces' / f'bump_{name}' / 'forces.dat'
    rows = [[float(x) for x in re.sub(r'[()]', ' ', l).split()] for l in open(f) if not l.startswith('#')]
    d = np.array([r[1] for r in rows]) * 1e3                     # total drag, mN (half car)
    blocks = d[-BLOCK * NB:].reshape(NB, BLOCK).mean(1)
    return float(blocks.mean()), float(blocks.std(ddof=1) / np.sqrt(NB)), len(d), blocks.round(4).tolist()


def predicted(npz, name):
    S = np.load(npz); X, G = S['Xs'], S['dD_dXs']
    base = trimesh.load('gate/original_rm/car_half.stl', process=False)
    mk = trimesh.load(f'gate/bump_{name}/car_half.stl', process=False)
    return float((G * displacement_at(X, base.vertices, mk.vertices - base.vertices)).sum()) * 1e3


rows = []
for site, name in PAIRS:
    (mp, sp, n_p, bp), (mm, sm, n_m, bm) = measured(name), measured(name + '_m')
    j = {k: json.loads((R / f'bump_{k}.json').read_text()) for k in (name, name + '_m')}
    half, se = (mp - mm) / 2, 0.5 * np.hypot(sp, sm)
    rows.append(dict(site=site, name=name, measured_half_mN=half, se_mN=se, clear=abs(half) >= 3 * se,
                     D_plus=mp, D_minus=mm, iters=(n_p, n_m), blocks_plus=bp, blocks_minus=bm,
                     D20_half_mN=(j[name]['D20_half_N'] - j[name + '_m']['D20_half_N']) * 1e3 / 2,
                     morph_fallback=[j[k].get('morph_fallback') for k in j],
                     **{f'pred_{t}_mN': (predicted(R / 'esi' / f'esi_sens_{t}.npz', name)
                                         - predicted(R / 'esi' / f'esi_sens_{t}.npz', name + '_m')) / 2
                        for t in ('frozen', 'sst')}))

out = [f"Wall-resolved normal-adjoint test, amended heights (RESOLVED_TEST.md 2026-11-24)"]
for r in rows:
    out.append(f"  {r['name']:20s} measured {r['measured_half_mN']:+.4f} +/- {r['se_mN']:.4f} mN "
               f"({'clear' if r['clear'] else 'NOT clear'}; D20 {r['D20_half_mN']:+.4f}); predicted frozen "
               f"{r['pred_frozen_mN']:+.4f}, sst {r['pred_sst_mN']:+.4f}; fallback {r['morph_fallback']}")
verdict = {}
for t in ('frozen', 'sst'):
    if any(any(r['morph_fallback']) for r in rows):
        v = 'INVALID (a bump left the morphed mesh)'
    elif not all(r['clear'] for r in rows):
        v = 'INCONCLUSIVE (a pair is below 3 SE)'
    else:
        m = np.array([r['measured_half_mN'] for r in rows]); p = np.array([r[f'pred_{t}_mN'] for r in rows])
        rr = float(np.corrcoef(m, p)[0, 1]); signs = bool(np.all(np.sign(m) == np.sign(p))); ratio = (p / m).tolist()
        ok = rr >= 0.9 and signs and all(0.5 <= x <= 2 for x in ratio)
        v = f"{'PASS' if ok else 'FAIL'}: r {rr:.3f}, signs {'all agree' if signs else 'disagree'}, predicted/measured " \
            + ', '.join(f'{x:.2f}' for x in ratio)
    verdict[t] = v
    out.append(f"{t}: {v}")
print('\n'.join(out))
(R / 'esi' / 'VERDICT_h.txt').write_text('\n'.join(out) + '\n')
(R / 'esi' / 'VERDICT_h.json').write_text(json.dumps({'pairs': rows, 'verdict': verdict}, indent=1, default=float))
