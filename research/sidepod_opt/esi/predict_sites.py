"""Adjoint-predicted half-difference (D+ - D-)/2 (mN, half car) for every bump pair in gate/, from an ESI
sensitivity file. Uses the actual bump STLs (gate/bump_<site>/car_half.stl, gate/bump_<site>_m/...),
the same mapping as dafoam/pair_judge.py, so it reproduces the verdict's numbers.
    python esi/predict_sites.py <esi_sens_*.npz>      (run from research/sidepod_opt)"""
import sys
from pathlib import Path
import numpy as np, trimesh
sys.path.insert(0, 'dafoam')
from pair_judge import displacement_at

S = np.load(sys.argv[1]); X, Gd = S['Xs'], S['dD_dXs']
base = trimesh.load('gate/original_rm/car_half.stl', process=False)


def pred(k):
    f = Path('gate') / f'bump_{k}' / 'car_half.stl'
    if not f.exists():
        return None
    mk = trimesh.load(f, process=False)
    return float((Gd * displacement_at(X, base.vertices, mk.vertices - base.vertices)).sum()) * 1e3


for d in sorted(Path('gate').glob('bump_*/car_half.stl')):
    k = d.parent.name[5:]
    if k.endswith('_m'):
        continue
    p, m = pred(k), pred(k + '_m')
    print(f"{k:16s} {(p - m) / 2 if m is not None else p:+.3f}{'' if m is not None else '  (+ only)'}")
