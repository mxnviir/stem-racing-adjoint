"""Adjoint-predicted drag change (mN, half car) of the +1 mm bump at every gate.py site, from an ESI
sensitivity file. Linear, so this is also the predicted half-difference (D+ - D-)/2.
    python esi/predict_sites.py <esi_sens_*.npz> <bumps.json>      (run from research/sidepod_opt)"""
import sys, json
import numpy as np, trimesh
sys.path.insert(0, '.'); sys.path.insert(0, 'dafoam'); sys.path.insert(0, '../../part2-simulation')
import gate
from pair_judge import displacement_at

S = np.load(sys.argv[1]); X, Gd = S['Xs'], S['dD_dXs']
base = trimesh.load('gate/original_rm/car_half.stl', process=False)
for s, v in json.load(open(sys.argv[2])).items():
    if 'centre_on_surface_m' not in v:
        continue
    w, _ = gate.bump_field(base, v['centre_on_surface_m'])
    print(f"{s:16s} {float((Gd * displacement_at(X, base.vertices, base.vertex_normals * w[:, None])).sum()) * 1e3:+.3f}")
