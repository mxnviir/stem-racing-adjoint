"""Round 2 (H2) verdict, hybrid/HYBRID_TEST.md. Written before any round-2 solve.
Marks: G1 D(guided) < D(es) by >= 3 SE; G2 D(guided) < D(daf) by >= 3 SE (all at 0.125 mm, old morph); PASS = both.
    python hybrid/r2_verdict.py -> hybrid/R2_VERDICT.txt/.json"""
import json, re
from pathlib import Path
import numpy as np
R = Path('gate_results_resolved_up'); H = Path('hybrid')
P = {**json.loads((H / 'pred_r1.json').read_text()), **json.loads((H / 'pred_r1b.json').read_text()),
     **json.loads((H / 'pred_r2.json').read_text())}
LIN = json.loads((H / 'r2' / 'combine.json').read_text())


def run(n):
    j = R / f'bump_{n}.json'; f = R / 'forces' / f'bump_{n}' / 'forces.dat'
    if not (j.exists() and f.exists()):
        return None
    J = json.loads(j.read_text())
    rows = [[float(x) for x in re.sub(r'[()]', ' ', l).split()] for l in open(f) if not l.startswith('#')]
    d = np.array([r[1] for r in rows]) * 1e3
    return dict(D=float(d[-404:].mean()), se=float(J['force_mean_stderr']) * 1e3, fallback=bool(J.get('morph_fallback')))


names = {'zero': 'step_zero', 'es': 'step_es_q', 'guided': 'step_guided_q', 'guided_daf': 'step_guidedaf_q',
         'guided_esi': 'step_guidedesi_q', 'daf': 'step_daf_q', 'rnd1': 'step_rnd1_q',
         'guided_05E': 'step_guided_05E', 'guided_10E': 'step_guided_10E', 'es_10E': 'step_es_10E', 'daf_10E2': 'step_daf_10E2',
         'daf_05E': 'step_daf_05E', 'daf_10E': 'step_daf_10E', 'rnd1_05E': 'step_rnd1_05E', 'esi_05E': 'step_esi_05E',
         'rnd1_qE': 'step_rnd1_qE', 'rnd1_qD': 'step_rnd1_qD'}
M = {k: run(n) for k, n in names.items()}
z = M['zero']
out = ['H2 (hybrid/HYBRID_TEST.md): change vs step_zero, half car, mN; SE whole-signal; linear-model and DAFoam predictions']
for k, m in M.items():
    if m is None:
        out.append(f'  {k:11s} MISSING / failed'); continue
    key = {'es': 'es_q', 'guided': 'guided_q', 'guided_daf': 'guidedaf_q', 'guided_esi': 'guidedesi_q'}.get(k, k)
    lin = LIN.get(k, {}).get('linear_model_mN_at_0p125')
    pd = P.get(key, {}).get('predicted_mN', {}).get('dafoam_coarse')
    out.append(f"  {k:11s} {m['D']:.4f} +/- {m['se']:.4f}  change {m['D'] - z['D']:+.4f}" + (f"  linear model {lin:+.3f}" if lin is not None else '')
               + (f"  DAFoam {pd:+.3f}" if pd is not None else '') + (f"  FALLBACK" if m['fallback'] else ''))


def beats(a, b):
    d = M[a]['D'] - M[b]['D']; s = 3 * np.hypot(M[a]['se'], M[b]['se']); return bool(d <= -s), float(d), float(s)


marks, verdict = {}, 'INVALID (a marked run missing or fell back)'
if all(M[k] and not M[k]['fallback'] for k in ('zero', 'es', 'guided', 'daf')):
    marks = {'G1 guided < es': beats('guided', 'es'), 'G2 guided < daf': beats('guided', 'daf')}
    for k, (ok, d, s) in marks.items():
        out.append(f"{k}: {'met' if ok else 'NOT met'} (difference {d:+.4f} mN, 3 SE {s:.4f})")
    verdict = 'PASS' if all(v[0] for v in marks.values()) else 'FAIL'
out.append(f'VERDICT H2: {verdict}')
if M['rnd1_qE'] and M['rnd1']:
    d = M['rnd1_qE']['D'] - M['rnd1']['D']; s = 3 * np.hypot(M['rnd1_qE']['se'], M['rnd1']['se'])
    out.append(f"Mark E (explicit morph reads the same as the old one, rnd1 0.125): {'met' if abs(d) <= s else 'NOT met'} (difference {d:+.4f}, 3 SE {s:.4f})")
print('\n'.join(out))
(H / 'R2_VERDICT.txt').write_text('\n'.join(out) + '\n')
(H / 'R2_VERDICT.json').write_text(json.dumps({'runs': M, 'marks': marks, 'verdict': verdict}, indent=1))
