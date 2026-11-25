"""Production-scheme marks P2/P3/P4 and the increments I34, I56 (hybrid/HYBRID_TEST.md), block-mean SE, with and
without the first 200-iteration block. python hybrid/increments_verdict.py"""
import re
from pathlib import Path
import numpy as np
R = Path('gate_results_resolved_up')


def blocks(n, drop=0):
    f = R / 'forces' / f'bump_{n}' / 'forces.dat'
    if not f.exists():
        return None
    rows = [[float(x) for x in re.sub(r'[()]', ' ', l).split()] for l in open(f) if not l.startswith('#')]
    b = (np.array([r[1] for r in rows])[-2000:] * 1e3).reshape(10, 200).mean(1)[drop:]
    return b.mean(), b.std(ddof=1) / np.sqrt(len(b))


for drop in (0, 1):
    print(f'--- blocks dropped: {drop}')
    V = {n: blocks(n, drop) for n in ('step_zero_P', 'step_best2_P', 'step_best4_P', 'step_final_P')}
    for n, v in V.items():
        print(f'  {n:14s}', 'missing' if v is None else f'{v[0]:.3f} +/- {v[1]:.3f}')
    for name, a, b in (('P2 best2 < zero', 'step_best2_P', 'step_zero_P'), ('P3 best4 < zero', 'step_best4_P', 'step_zero_P'),
                       ('P4 final < zero', 'step_final_P', 'step_zero_P'), ('I34 best4 < best2', 'step_best4_P', 'step_best2_P'),
                       ('I56 final < best4', 'step_final_P', 'step_best4_P')):
        if V[a] and V[b]:
            d, s = V[a][0] - V[b][0], 3 * np.hypot(V[a][1], V[b][1])
            print(f'  {name:18s} {d:+.3f} (3 SE {s:.3f}): {"met" if d <= -s else "NOT met"}')
