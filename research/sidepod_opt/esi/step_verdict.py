"""Verdict of the step test (esi/STEP_TEST.md, approved 2026-11-24). Written before any step was solved.
Run from research/sidepod_opt once the step solves are on the branch:
    python esi/step_verdict.py      -> gate_results_resolved_up/esi/STEP_VERDICT.txt (+ .json)

Drag of a run: mean of total drag (forces.dat column 1, half car) over the last 404 iterations; SE = sd of the four
101-iteration block means / 2 (as RESOLVED_TEST.md amendment 2026-11-24). A difference is "by >= 3 SE" when it
exceeds 3 * sqrt(SE_a^2 + SE_b^2). A run that left the morphed mesh (morph_fallback) or is missing makes the
verdict INVALID. Amendment 2026-11-24 (owner): every moving candidate at a common 0.125 mm, read as step_<field>_q;
esi_a10 is dropped (it cannot morph clean).
Marks (STEP_TEST.md): M1 esi_a05 < zero; M2 esi_a05 < opp_a05; M3 esi_a05 < min(rnd1_a05, rnd2_a05); PASS = all three.
"""
import json, re, sys
from pathlib import Path
import numpy as np

R = Path('gate_results_resolved_up')
BLOCK, NB = 101, 4
NAMES = ['zero', 'esi_a05', 'esi_a10', 'sst_a05', 'opp_a05', 'rnd1_a05', 'rnd2_a05']


def resolve(k):
    """The candidate as run: step_<k>, or its half-height remake step_<k>_h if only that exists."""
    q = [f'step_{k[:-4]}_q'] if k.endswith('_a05') else []      # amendment 2026-11-24: common 0.125 mm
    for n in q + [f'step_{k}', f'step_{k}_h']:
        if (R / 'forces' / f'bump_{n}' / 'forces.dat').exists():
            return n
    return None


def measured(n):
    f = R / 'forces' / f'bump_{n}' / 'forces.dat'
    rows = [[float(x) for x in re.sub(r'[()]', ' ', l).split()] for l in open(f) if not l.startswith('#')]
    d = np.array([r[1] for r in rows]) * 1e3
    b = d[-BLOCK * NB:].reshape(NB, BLOCK).mean(1)
    j = json.loads((R / f'bump_{n}.json').read_text())
    return dict(name=n, D_mN=float(b.mean()), se_mN=float(b.std(ddof=1) / np.sqrt(NB)), iters=len(d),
                blocks=b.round(4).tolist(), morph_fallback=bool(j.get('morph_fallback')), converged=j.get('converged'))


res = {k: (measured(n) if (n := resolve(k)) else None) for k in NAMES}
out = ['Step test (esi/STEP_TEST.md): drag of each candidate, half car, mN (mean of last 404 its, SE from 4 blocks)']
for k, m in res.items():
    out.append(f"  {k:9s} " + ('MISSING' if m is None else
               f"{m['D_mN']:.4f} +/- {m['se_mN']:.4f}  ({m['name']}, fallback {m['morph_fallback']}, converged {m['converged']})"))


def beats(a, b):
    """a lower than b by >= 3 SE of the difference; returns (bool, difference a-b, 3 SE)."""
    d = res[a]['D_mN'] - res[b]['D_mN']; s = 3 * np.hypot(res[a]['se_mN'], res[b]['se_mN'])
    return bool(d <= -s), float(d), float(s)


need = ['zero', 'esi_a05', 'opp_a05', 'rnd1_a05', 'rnd2_a05']
if any(res[k] is None for k in need) or any(res[k]['morph_fallback'] for k in need):
    verdict, marks = 'INVALID (a required run is missing or left the morphed mesh)', {}
else:
    rnd = min(('rnd1_a05', 'rnd2_a05'), key=lambda k: res[k]['D_mN'])
    marks = {'M1 esi_a05 < zero': beats('esi_a05', 'zero'), 'M2 esi_a05 < opp_a05': beats('esi_a05', 'opp_a05'),
             f'M3 esi_a05 < {rnd} (better random)': beats('esi_a05', rnd)}
    for k, (ok, d, s) in marks.items():
        out.append(f"{k}: {'met' if ok else 'NOT met'} (difference {d:+.4f} mN, 3 SE {s:.4f})")
    verdict = 'PASS' if all(v[0] for v in marks.values()) else 'FAIL'
out.append(f'VERDICT: {verdict}')
for a, b in (('esi_a10', 'esi_a05'), ('sst_a05', 'esi_a05'), ('esi_a10', 'zero'), ('sst_a05', 'zero')):
    if res[a] and res[b]:
        out.append(f"  reported, not marked: {a} - {b} = {res[a]['D_mN'] - res[b]['D_mN']:+.4f} mN "
                   f"(3 SE {3 * np.hypot(res[a]['se_mN'], res[b]['se_mN']):.4f})")
print('\n'.join(out))
(R / 'esi').mkdir(exist_ok=True)
(R / 'esi' / 'STEP_VERDICT.txt').write_text('\n'.join(out) + '\n')
(R / 'esi' / 'STEP_VERDICT.json').write_text(json.dumps({'runs': res, 'marks': marks, 'verdict': verdict}, indent=1))
