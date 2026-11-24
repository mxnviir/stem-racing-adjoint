"""Generation 2+ solve with a chained explicit morph (hybrid/HYBRID_TEST.md): morph the wall-resolved mesh onto the
parent (base + parent steps, morph only), then morph THAT mesh by the child's increment and solve (warm start from the
base steady state's fields, 1000 steady iterations), as gate.py bump does. Env as resolved_bumps (GATE_RES=resolved,
GATE_RESULTS with base.json, P2_MORPH_STRICT=1, P2_MORPH_STRICT_RULE=acceptable, P2_MORPH_EXPLICIT=1, P2_WARM_COPY=1).
    python hybrid/chain_solve.py <name> <parent spec f@amp[+f@amp]> <field> <amp_mm>"""
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
subprocess.run([sys.executable, '-W', 'ignore', 'esi/make_step.py', f'{name}_inc', field, amp], check=True, env=env)
subprocess.run([sys.executable, '-W', 'ignore', 'esi/make_step.py', f'{name}_par', 'zero', '0'], check=True,
               env=dict(env, STEP_PARENT=parent))
FP, FI = np.load(G / f'bump_{name}_par/morph_field.npz'), np.load(G / f'bump_{name}_inc/morph_field.npz')
child = G / f'bump_{name}'
if child.exists():
    shutil.rmtree(child)
shutil.copytree(G / f'bump_{name}_inc', child)
m = trimesh.load(G / 'original_rm/car_half.stl')
m.vertices = FP['V'] + FP['D'] + FI['D']
CI.write_ascii_named(m, child / 'car_half.stl', 'car', m.volume, 0.01)
np.savez(child / 'morph_field.npz', V=FP['V'] + FP['D'], D=FI['D'])
print('CHAIN child total peak mm', float(np.linalg.norm(FP['D'] + FI['D'], axis=1).max() * 1e3), flush=True)

base_ref = Path(json.loads((R / 'base.json').read_text())['run_dir_kept'])
chainA = G / f'chainA_{name}'
orig = oc._run


def hook(cmd, run, bashrc, log, timeout_s, *a, **k):
    out = orig(cmd, run, bashrc, log, timeout_s, *a, **k)
    if log == 'checkMesh_morph.log':
        print(f"CHAIN parent morph: {'Mesh OK' if 'Mesh OK' in out else 'acceptable' if oc.morph_mesh_acceptable(out) else 'FAILED'}", flush=True)
        if chainA.exists():
            shutil.rmtree(chainA)
        shutil.copytree(run, chainA, ignore=shutil.ignore_patterns('processor*'))
        times = [d for d in base_ref.iterdir() if d.is_dir() and re.fullmatch(r'[0-9.eE+-]+', d.name)]
        latest = max(times, key=lambda d: float(d.name))
        dst = chainA / latest.name                                  # the base flow as the chained mesh's latest state
        dst.mkdir(exist_ok=True)
        for f in latest.iterdir():
            if f.is_file():
                shutil.copy(f, dst / f.name)
        raise SystemExit(0)
    return out


os.environ['P2_MORPH_FIELD'] = str(G / f'bump_{name}_par/morph_field.npz')
oc._run = hook
sys.argv = ['gate.py', 'bump', f'{name}_par', '4']
try:
    runpy.run_path(str(SP / 'gate.py'), run_name='__main__')
except SystemExit:
    pass
oc._run = orig
if not chainA.exists():
    raise SystemExit('parent morph produced no mesh')
b = json.loads((R / 'base.json').read_text()); b['run_dir_kept'] = str(chainA); (R / 'base.json').write_text(json.dumps(b, indent=1))
os.environ['P2_MORPH_FIELD'] = str(child / 'morph_field.npz')
sys.argv = ['gate.py', 'bump', name, '4']
runpy.run_path(str(SP / 'gate.py'), run_name='__main__')
