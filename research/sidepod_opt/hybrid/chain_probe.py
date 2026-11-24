"""Chained explicit morph, morph-only (no solve): morph the wall-resolved mesh onto design A (base + D_A), then morph
THAT mesh onto B = A + increment, checkMesh after each. Tells whether generations can accumulate past ~1 mm without a
new mesh. Env as morph_check (GATE_RES=resolved, GATE_RESULTS with base.json, P2_MORPH_STRICT=1, P2_MORPH_EXPLICIT=1).
    python hybrid/chain_probe.py <A_field> <A_amp_mm> <inc_field> <inc_amp_mm>"""
import json, os, runpy, shutil, subprocess, sys
from pathlib import Path
import numpy as np
SP = Path(__file__).resolve().parents[1]
os.chdir(SP); sys.path.insert(0, str(SP.parents[1] / 'part2-simulation')); sys.path.insert(0, str(SP))
import openfoam_case as oc  # noqa: E402
import trimesh  # noqa: E402
import cadio as CI  # noqa: E402

fa, aa, fi, ai = sys.argv[1:5]
env = dict(os.environ, STEP_NORMAL_SIGMA_MM=os.environ.get('STEP_NORMAL_SIGMA_MM', '1.5'), STEP_ZMIN_MM=os.environ.get('STEP_ZMIN_MM', '1.5'))
for name, f, a in (('chA', fa, aa), ('chI', fi, ai)):
    subprocess.run([sys.executable, '-W', 'ignore', 'esi/make_step.py', name, f, a], check=True, env=env)
G = SP / 'gate'
FA, FI = np.load(G / 'bump_chA/morph_field.npz'), np.load(G / 'bump_chI/morph_field.npz')
B = G / 'bump_chB'
if B.exists():
    shutil.rmtree(B)
shutil.copytree(G / 'bump_chI', B)
m = trimesh.load(G / 'original_rm/car_half.stl')
m.vertices = FA['V'] + FA['D'] + FI['D']
CI.write_ascii_named(m, B / 'car_half.stl', 'car', m.volume, 0.01)
np.savez(B / 'morph_field.npz', V=FA['V'] + FA['D'], D=FI['D'])
print('CHAIN B peak total move mm', float(np.linalg.norm(FA['D'] + FI['D'], axis=1).max() * 1e3), flush=True)

orig = oc._run
state = {}


def hook(cmd, run, bashrc, log, timeout_s, *a, **k):
    out = orig(cmd, run, bashrc, log, timeout_s, *a, **k)
    if log == 'checkMesh_morph.log':
        bad = [l.strip() for l in out.splitlines() if l.strip().startswith('***')]
        acc = oc.morph_mesh_acceptable(out)
        print(f"MORPH_RESULT {state['tag']}: {'Mesh OK' if 'Mesh OK' in out else 'FAILED ' + str(bad)} (acceptable {acc})", flush=True)
        if state['tag'] == 'A':
            dst = G / 'chainA'
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(run, dst, ignore=shutil.ignore_patterns('processor*'))
        raise SystemExit(0)
    return out


oc._run = hook
R = Path(os.environ['GATE_RESULTS'])
for tag, k, ref in (('A', 'chA', None), ('B', 'chB', G / 'chainA')):
    state['tag'] = tag
    os.environ['P2_MORPH_FIELD'] = str(G / f'bump_{k}/morph_field.npz')
    if ref is not None:
        if not ref.exists():
            print('MORPH_RESULT B: not run (A did not produce a mesh)'); break
        b = json.loads((R / 'base.json').read_text()); b['run_dir_kept'] = str(ref); (R / 'base.json').write_text(json.dumps(b, indent=1))
    sys.argv = ['gate.py', 'bump', k, '4']
    try:
        runpy.run_path(str(SP / 'gate.py'), run_name='__main__')
    except SystemExit:
        pass
