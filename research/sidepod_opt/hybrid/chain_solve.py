"""Generation 2+ solve with chained explicit morphs (hybrid/HYBRID_TEST.md). The parent is a chain of accepted steps,
"levels" separated by '|' (each level: one or more f@amp parts summed). The wall-resolved mesh is morphed level by
level (morph only, checkMesh each), then by the child's own step, and the child is solved (warm start from the base
steady state's fields, 1000 steady iterations) as gate.py bump does. Env as resolved_bumps (GATE_RES=resolved,
GATE_RESULTS with base.json, P2_MORPH_STRICT=1, P2_MORPH_STRICT_RULE=acceptable, P2_MORPH_EXPLICIT=1, P2_WARM_COPY=1).
    python hybrid/chain_solve.py <name> <parent levels "f@a[+f@a]|f@a..."> <field> <amp_mm>"""
import json, os, re, runpy, shutil, subprocess, sys
from pathlib import Path
import numpy as np
SP = Path(__file__).resolve().parents[1]
os.chdir(SP); sys.path.insert(0, str(SP.parents[1] / 'part2-simulation')); sys.path.insert(0, str(SP))
import openfoam_case as oc  # noqa: E402
import trimesh  # noqa: E402
import cadio as CI  # noqa: E402

name, parent, field, amp = sys.argv[1:5]
G = SP / 'gate'; R = Path(os.environ['GATE_RESULTS'])
env = {k: v for k, v in os.environ.items() if k != 'STEP_PARENT'}
# the moves are built here (the solve stage), not in the workflow's step-candidate stage: give them that stage's
# settings (smoothed normals, ground clearance), or a 1 mm parent is built on raw normals and folds (2026-11-24 22:35)
for k, v in (('STEP_NORMAL_SIGMA_MM', '1.5'), ('STEP_ZMIN_MM', '1.5')):
    if not env.get(k) or env[k] == '0':
        env[k] = v
levels = [l for l in parent.split('|') if l] + [f'{field}@{amp}']
D = []
for i, lv in enumerate(levels):                       # each level's own displacement on the base STL vertices
    subprocess.run([sys.executable, '-W', 'ignore', 'esi/make_step.py', f'{name}_l{i}', 'zero', '0'], check=True,
                   env=dict(env, STEP_PARENT=lv))
    D.append(np.load(G / f'bump_{name}_l{i}/morph_field.npz')['D'])
V = np.load(G / f'bump_{name}_l0/morph_field.npz')['V']
cum = np.cumsum(np.array(D), axis=0)
print('CHAIN levels', levels, 'total peak mm', float(np.linalg.norm(cum[-1], axis=1).max() * 1e3), flush=True)
m = trimesh.load(G / 'original_rm/car_half.stl')
for i in range(len(levels)):                           # level folders: absolute STL, field relative to the level below
    f = G / f'bump_{name}_l{i}'
    m.vertices = V + cum[i]
    CI.write_ascii_named(m, f / 'car_half.stl', 'car', m.volume, 0.01)
    np.savez(f / 'morph_field.npz', V=V + (cum[i - 1] if i else 0.0), D=D[i])
child = G / f'bump_{name}'
if child.exists():
    shutil.rmtree(child)
shutil.copytree(G / f'bump_{name}_l{len(levels) - 1}', child)

if os.environ.get('CHAIN_DRY') == '1':
    raise SystemExit('dry run: level fields built')
base_ref = Path(json.loads((R / 'base.json').read_text())['run_dir_kept'])
times = [d for d in base_ref.iterdir() if d.is_dir() and re.fullmatch(r'[0-9.eE+-]+', d.name)]
latest = max(times, key=lambda d: float(d.name))
orig = oc._run
state = {}


def hook(cmd, run, bashrc, log, timeout_s, *a, **k):
    out = orig(cmd, run, bashrc, log, timeout_s, *a, **k)
    if log == 'checkMesh_morph.log':
        ok = oc.morph_mesh_acceptable(out)
        print(f"CHAIN level {state['i']} morph: {'Mesh OK' if 'Mesh OK' in out else 'acceptable' if ok else 'FAILED'}", flush=True)
        if not ok:
            raise RuntimeError(f"chain level {state['i']} morph failed checkMesh")
        dst = G / f"chain_{name}_l{state['i']}"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(run, dst, ignore=shutil.ignore_patterns('processor*'))
        t = dst / latest.name                                 # the base flow as this mesh's latest state (warm start)
        t.mkdir(exist_ok=True)
        for fl in latest.iterdir():
            if fl.is_file():
                shutil.copy(fl, t / fl.name)
        raise SystemExit(0)
    return out


ref = base_ref
for i in range(len(levels) - 1):
    state['i'] = i
    b = json.loads((R / 'base.json').read_text()); b['run_dir_kept'] = str(ref); (R / 'base.json').write_text(json.dumps(b, indent=1))
    os.environ['P2_MORPH_FIELD'] = str(G / f'bump_{name}_l{i}/morph_field.npz')
    oc._run = hook
    sys.argv = ['gate.py', 'bump', f'{name}_l{i}', '4']
    try:
        runpy.run_path(str(SP / 'gate.py'), run_name='__main__')
    except SystemExit:
        pass
    oc._run = orig
    ref = G / f'chain_{name}_l{i}'
    if not ref.exists():
        raise SystemExit(f'level {i} morph produced no mesh')
b = json.loads((R / 'base.json').read_text()); b['run_dir_kept'] = str(ref); (R / 'base.json').write_text(json.dumps(b, indent=1))
os.environ['P2_MORPH_FIELD'] = str(child / 'morph_field.npz')
sys.argv = ['gate.py', 'bump', name, '4']
runpy.run_path(str(SP / 'gate.py'), run_name='__main__')
