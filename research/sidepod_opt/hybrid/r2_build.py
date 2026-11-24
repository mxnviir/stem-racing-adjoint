"""Build round 2 (hybrid/HYBRID_TEST.md H2) from the measured 0.125 mm moves: measured.json -> combine.py -> fields,
predictions and the resolved_bumps request. Run after R1_VERDICT, before any round-2 solve.
    python hybrid/r2_build.py      (from research/sidepod_opt)"""
import json, re, subprocess, sys
from pathlib import Path
import numpy as np
R = Path('gate_results_resolved_up'); H = Path('hybrid')


def D(n):
    f = R / 'forces' / f'bump_{n}' / 'forces.dat'; j = R / f'bump_{n}.json'
    if not (f.exists() and j.exists()) or json.loads(j.read_text()).get('morph_fallback'):
        return None
    rows = [[float(x) for x in re.sub(r'[()]', ' ', l).split()] for l in open(f) if not l.startswith('#')]
    return float(np.mean([r[1] for r in rows][-404:]) * 1e3)


z = D('step_zero')
moves = {'step_esi_q': ('esi_frozen', 0.125), 'step_sst_q': ('esi_sst', 0.125), 'step_opp_q': ('opp_frozen', 0.125),
         'step_daf_q': ('daf', 0.125), 'step_dafopp_q': ('daf_opp', 0.125), 'step_rnd1m_q': ('rnd1m', 0.125),
         **{f'step_rnd{k}_q': (f'rnd{k}', 0.125) for k in range(1, 11)}}
meas = {}
for n, (f, a) in moves.items():
    d = D(n)
    if d is not None:
        meas[n] = {'field': f, 'amp_mm': a, 'dF_mN': d - z}
(H / 'r2').mkdir(exist_ok=True)
(H / 'r2' / 'measured.json').write_text(json.dumps(meas, indent=1))
print(len(meas), 'measured moves;', {k: round(v['dF_mN'], 3) for k, v in meas.items()})
subprocess.run([sys.executable, '-W', 'ignore', 'hybrid/combine.py', 'hybrid/r2/measured.json', 'hybrid/r2'], check=True)
