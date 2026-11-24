"""Morph-only check on the fine mesh: bump the reference car's own surface at a site (+/- a mm), morph the
fine mesh with Part 2's _morph, run checkMesh, report. No solve.  probe.py <site> <amp_mm>"""
import sys, json, shutil, time, os
from pathlib import Path
import numpy as np, trimesh
ROOT = Path('/home/user/esp32-line-follower')
sys.path.insert(0, str(ROOT / 'part2-simulation')); sys.path.insert(0, str(ROOT / 'research/sidepod_opt'))
import openfoam_case as oc
import gate
REF = Path(os.environ.get('FINE_REF', str(ROOT / 'part2-simulation/cfd_case_template/runs/run_569_c920761dd687')))  # a kept fine team-pod mesh
SITES = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else None
site, amp = sys.argv[1], float(sys.argv[2])
W = Path(__file__).parent / f'run_{site}_{amp:+.2f}'
shutil.rmtree(W, ignore_errors=True); W.mkdir()
for d in ('system', '0'):
    shutil.copytree(REF / d, W / d)
(W / 'constant').mkdir()
for p in (REF / 'constant').iterdir():
    if p.name != 'polyMesh':
        (shutil.copytree if p.is_dir() else shutil.copy)(p, W / 'constant' / p.name)
car = trimesh.load(REF / 'constant/triSurface/car.stl', force='mesh')
if site != 'zero':
    w, c = gate.bump_field(car, SITES[site]['centre_on_surface_m'], a=amp * 1e-3)
    car = trimesh.Trimesh(car.vertices + car.vertex_normals * w[:, None], car.faces, process=False)
car.export(W / 'constant/triSurface/car.stl', file_type='stl_ascii')
bashrc = oc.find_openfoam_bashrc(None)
cfg = oc.OpenFOAMRunConfig(morph_from=str(REF))
t = time.time()
oc._morph(W, cfg, bashrc, 7200)
check = oc._run('checkMesh', W, bashrc, 'checkMesh_morph.log', 7200)
bad = [l.strip() for l in check.splitlines() if l.strip().startswith('***')]
ok = 'Mesh OK' in check
print(f"RESULT {site} {amp:+.2f} mm: {'Mesh OK' if ok else ('ACCEPTABLE ' if oc.morph_mesh_acceptable(check) else 'FAILED ') + '; '.join(bad)} "
      f"({time.time() - t:.0f} s) {(W / 'logs/morph_displacement.txt').read_text().splitlines()[0]}", flush=True)
shutil.rmtree(W, ignore_errors=True)
