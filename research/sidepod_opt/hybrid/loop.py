"""The guided-evolution loop on the good mesh, one generation per call (hybrid/EVOLUTION_ADJOINT_PLAN.md section 1).
State: hybrid/loop_state.json. Rules (fixed 2026-11-24 before generation 3; same as guided_es.py):
- every child of generation k is the parent plus ONE move (peak AMP mm), chained morph (chain_solve.py);
- the parent is re-run as g{k}_zero; the best child replaces the parent if it is below g{k}_zero by >= 3 SE
  (whole-signal SE), else the parent stays;
- children: one move along each guide (fresh coarse DAFoam at the parent when available, else the newest one; ESI);
  N_RND new random smooth moves; and moves along the steepest descent in the span of the previous generation's
  measured moves (all of them: 'comb'; random ones only: 'es'), each at AMP and AMP/2.
    python hybrid/loop.py next <k> [fresh_dafoam_npz]     (reads generation k-1's results, writes generation k's request)"""
import json, re, subprocess, sys
from pathlib import Path
import numpy as np
SP = Path(__file__).resolve().parents[1]
R = SP / 'gate_results_resolved_up'; H = SP / 'hybrid'; ST = H / 'loop_state.json'
AMP, N_RND = 0.5, 6


def run(n):
    j, f = R / f'bump_{n}.json', R / 'forces' / f'bump_{n}' / 'forces.dat'
    if not (j.exists() and f.exists()):
        return None
    J = json.loads(j.read_text())
    if J.get('morph_fallback'):
        return None
    rows = [[float(x) for x in re.sub(r'[()]', ' ', l).split()] for l in open(f) if not l.startswith('#')]
    return float(np.mean([r[1] for r in rows][-404:]) * 1e3), float(J['force_mean_stderr']) * 1e3


def main():
    k = int(sys.argv[2]); fresh = sys.argv[3] if len(sys.argv) > 3 else None
    S = json.loads(ST.read_text())
    prev = S['generations'][str(k - 1)]
    z = run(f'step_g{k - 1}_zero')
    res = {n: run(f'step_{n}') for n in prev['children']}
    ok = {n: v for n, v in res.items() if v is not None}
    log = {'zero': z, 'children': {n: (v[0] - z[0], v[1]) for n, v in ok.items()}, 'failed': [n for n in res if res[n] is None]}
    best = min(ok, key=lambda n: ok[n][0]) if ok else None
    acc = best if best and ok[best][0] - z[0] <= -3 * np.hypot(ok[best][1], z[1]) else None
    log['accepted'] = acc
    if acc:
        f, a = prev['children'][acc]
        S['parent'] = (S['parent'] + '|' if S['parent'] else '') + f'{f}@{a}'
    S['generations'][str(k - 1)]['result'] = log
    print(f'generation {k - 1}: zero {z[0]:.3f}; best {best} {ok[best][0] - z[0]:+.3f}; accepted {acc}; parent now {S["parent"]}')
    # measured moves of generation k-1 -> directions for generation k (relative to the old parent; small change)
    gdir = H / f'g{k}'; gdir.mkdir(exist_ok=True)
    meas = {n: {'field': prev['children'][n][0], 'amp_mm': prev['children'][n][1], 'dF_mN': d}
            for n, (d, s) in log['children'].items() if '@' not in prev['children'][n][0]}
    (gdir / 'measured.json').write_text(json.dumps(meas, indent=1))
    subprocess.run([sys.executable, '-W', 'ignore', str(H / 'combine.py'), str(gdir / 'measured.json'), str(gdir)], check=True, cwd=SP)
    seed0 = S.get('next_seed', 17)
    kids = {'zero': ('zero', 0.0), 'dafnew': (f'dafnpz:{fresh}' if fresh else S['dafoam_latest'], AMP),
            'esi': ('esi_frozen', AMP), 'comb': (f'vec:hybrid/g{k}/guided.npy', AMP), 'combh': (f'vec:hybrid/g{k}/guided.npy', AMP / 2),
            'es': (f'vec:hybrid/g{k}/es.npy', AMP), 'esh': (f'vec:hybrid/g{k}/es.npy', AMP / 2),
            **{f'rnd{s}': (f'rnd{s}', AMP) for s in range(seed0, seed0 + N_RND)}}
    if fresh:
        S['dafoam_latest'] = f'dafnpz:{fresh}'
    S['next_seed'] = seed0 + N_RND
    S['generations'][str(k)] = {'parent': S['parent'], 'children': {f'g{k}_{n}': v for n, v in kids.items() if n != 'zero'}}
    E1 = dict(site='step', direct='1', nsig='1.5', mask='0', explicit='1', zmin='1.5', chainparent=S['parent'])
    cases = [dict(name=f'step_g{k}_{n}', field=f, amp=str(a), **E1) for n, (f, a) in kids.items()]
    req = {'note': f'hybrid loop generation {k}: parent {S["parent"]} (chained) + one move each',
           'steady_release': 'resolved-steady-45125305486', 'bumpgeom_run': 45188798730, 'cases': cases, 'attempt': 100 + k}
    (SP.parents[1] / '.github/resolved_bumps_request.json').write_text(json.dumps(req, indent=1))
    ST.write_text(json.dumps(S, indent=1))
    print(json.dumps({n: v for n, v in kids.items()}, indent=0))


if __name__ == '__main__':
    main()
