"""Mark P3 verdict (hybrid/HYBRID_TEST.md), written before step_best4_P's solve: production scheme, SE from ten
200-iteration block means. python hybrid/p2_verdict.py"""
import re
from pathlib import Path
import numpy as np
R = Path('gate_results_resolved_up')


def blocks(n):
    rows = [[float(x) for x in re.sub(r'[()]', ' ', l).split()] for l in open(R / 'forces' / f'bump_{n}' / 'forces.dat') if not l.startswith('#')]
    d = np.array([r[1] for r in rows])[-2000:] * 1e3
    b = d.reshape(10, 200).mean(1)
    return b.mean(), b.std(ddof=1) / np.sqrt(10)


z, sz = blocks('step_zero_P'); b, sb = blocks('step_best4_P')
d, s = b - z, 3 * np.hypot(sz, sb)
print(f'zero_P {z:.3f} +/- {sz:.3f}; best4_P {b:.3f} +/- {sb:.3f}; difference {d:+.3f} (3 SE {s:.3f}); '
      f"Mark P3 {'met' if d <= -s else 'NOT met'}; ratio to the steady model's -9.50: {d / -9.50:.2f}")
