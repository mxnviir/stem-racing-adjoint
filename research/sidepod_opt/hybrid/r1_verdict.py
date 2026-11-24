"""Round 1 (H1) verdict, hybrid/HYBRID_TEST.md. Written before any round-1 solve.
    python hybrid/r1_verdict.py   (from research/sidepod_opt) -> hybrid/R1_VERDICT.txt/.json"""
import json, re
from pathlib import Path
import numpy as np
R = Path('gate_results_resolved_up'); H = Path('hybrid')
PRED = json.loads((H / 'pred_r1.json').read_text())


def run(n):
    j = R / f'bump_{n}.json'; f = R / 'forces' / f'bump_{n}' / 'forces.dat'
    if not (j.exists() and f.exists()):
        return None
    J = json.loads(j.read_text())
    rows = [[float(x) for x in re.sub(r'[()]', ' ', l).split()] for l in open(f) if not l.startswith('#')]
    d = np.array([r[1] for r in rows]) * 1e3
    return dict(D=float(d[-404:].mean()), se=float(J['force_mean_stderr']) * 1e3, fallback=bool(J.get('morph_fallback')),
                converged=J.get('converged'))


names = {'zero': 'step_zero', 'zero_r': 'step_zero_r', 'daf': 'step_daf_q', 'daf_opp': 'step_dafopp_q', 'rnd1m': 'step_rnd1m_q',
         'rnd1_h': 'step_rnd1h_q', **{f'rnd{k}': f'step_rnd{k}_q' for k in range(1, 11)}}
M = {k: run(n) for k, n in names.items()}
out = ['H1 (hybrid/HYBRID_TEST.md): drag, half car, mN; change vs step_zero; SE = whole-signal force_mean_stderr']
z = M['zero']
for k, m in M.items():
    if m is None:
        out.append(f'  {k:8s} MISSING / folded'); continue
    p = PRED.get(k if k != 'rnd1_h' else 'rnd1_h', PRED.get(k + '_q', {})).get('predicted_mN', {}) if k not in ('zero',) else {}
    pr = '  '.join(f"{t} {v:+.3f}" for t, v in p.items())
    out.append(f"  {k:8s} {m['D']:.4f} +/- {m['se']:.4f}  change {m['D'] - z['D']:+.4f}  fallback {m['fallback']}  pred: {pr}")


def beats(a, b):
    d = M[a]['D'] - M[b]['D']; s = 3 * np.hypot(M[a]['se'], M[b]['se']); return bool(d <= -s), float(d), float(s)


verdict, marks = 'INVALID (daf or daf_opp missing / folded, or a fallback)', {}
rnds = [f'rnd{k}' for k in range(1, 11) if M[f'rnd{k}'] and not M[f'rnd{k}']['fallback']]
if all(M[k] and not M[k]['fallback'] for k in ('zero', 'daf', 'daf_opp')):
    best = min(rnds, key=lambda k: M[k]['D'])
    marks = {'M1 daf < zero': beats('daf', 'zero'), 'M2 daf < daf_opp': beats('daf', 'daf_opp'),
             f'M3 daf below all {len(rnds)} random steps (best {best})': (bool(M['daf']['D'] < M[best]['D']), M['daf']['D'] - M[best]['D'], 0.0)}
    for k, (ok, d, s) in marks.items():
        out.append(f"{k}: {'met' if ok else 'NOT met'} (difference {d:+.4f} mN, 3 SE {s:.4f})")
    verdict = 'PASS' if all(v[0] for v in marks.values()) else 'FAIL'
out.append(f'VERDICT H1: {verdict}')
new = [k for k in ['daf', 'daf_opp'] + [f'rnd{k}' for k in range(3, 11)] + ['rnd1m'] if M[k] and not M[k]['fallback']]
fid = {}
for t in ('dafoam_coarse', 'esi_resolved', 'esi_coarse'):
    m = np.array([M[k]['D'] - z['D'] for k in new]); p = np.array([PRED[k]['predicted_mN'][t] for k in new])
    fid[t] = dict(n=len(new), r=float(np.corrcoef(m, p)[0, 1]), signs=int((np.sign(m) == np.sign(p)).sum()),
                  slope=float(m @ p / (p @ p)))
    out.append(f"fidelity {t}: n {len(new)}  r {fid[t]['r']:.2f}  signs {fid[t]['signs']}/{len(new)}  slope meas/pred {fid[t]['slope']:.2f}")
F = fid['dafoam_coarse']['r'] >= 0.7 and fid['dafoam_coarse']['signs'] >= 0.8 * fid['dafoam_coarse']['n']
out.append(f"F (coarse DAFoam fidelity, r >= 0.7 and signs >= 80 %): {'met' if F else 'NOT met'}")
rep = []
for a, b in (('rnd1m', 'rnd1'), ('rnd1_h', 'rnd1'), ('zero_r', 'zero')):
    if M[a] and M[b]:
        rep.append(f"  {a}: change {M[a]['D'] - z['D']:+.4f} vs {b} change {M[b]['D'] - z['D']:+.4f}")
if M['daf']:
    for k in ['daf'] + rnds:
        rep.append(f"  per RMS mm: {k} {(M[k]['D'] - z['D']) / PRED.get(k, PRED.get(k + '_q'))['rms_mm']:+.2f} mN/mm")
out += ['reported, not marked:'] + rep
print('\n'.join(out))
(H / 'R1_VERDICT.txt').write_text('\n'.join(out) + '\n')
(H / 'R1_VERDICT.json').write_text(json.dumps({'runs': M, 'marks': marks, 'verdict': verdict, 'fidelity': fid, 'F': F}, indent=1))
