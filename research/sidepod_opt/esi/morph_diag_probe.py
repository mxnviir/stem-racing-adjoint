"""Morph-only probe (plan B step 1, DECISIONS.md D9) on the wall-resolved mesh via gate.py's own bump path (strict: no fresh-mesh fallback, no solve).
After the morph's checkMesh it runs `checkMesh -writeSets raw` and classifies every bad cell/face.
    probe.py <site>        (env: GATE_RES=resolved GATE_RESULTS=<dir with base.json> GATE_MORPH_REF_RM=1 P2_MORPH_STRICT=1)"""
import os, runpy, sys, glob, json, re
from pathlib import Path
import numpy as np
SP = Path('/home/user/esp32-line-follower/research/sidepod_opt'); site = sys.argv[1]
os.chdir(SP); sys.path.insert(0, str(SP.parents[1] / 'part2-simulation')); sys.path.insert(0, str(SP))
import openfoam_case as oc  # noqa: E402
orig = oc._run


def vtk_points(f):
    """checkMesh -writeSets raw: plain-text rows, x y z first (comment lines start with #)."""
    rows = [l.split() for l in open(f) if l.strip() and not l.startswith('#')]
    return np.array([[float(v) for v in r[:3]] for r in rows if len(r) >= 3]).reshape(-1, 3)


def classify(run):
    import trimesh
    car = trimesh.load(str(Path(run) / 'constant/triSurface/car.stl'), force='mesh')
    ang = car.face_adjacency_angles; e = car.face_adjacency_edges[ang > np.radians(30)]
    ep = car.vertices[e]                                     # sharp edges as segments
    centre = None
    bj = SP / 'gate' / f'bump_{site.removesuffix("_m")}'
    B = json.load(open(os.environ['GATE_RESULTS'] + '/bumps.json')) if Path(os.environ['GATE_RESULTS'] + '/bumps.json').exists() else {}
    key = B.get(site, {}).get('site') or site.removesuffix('_m')
    if key in B and 'centre_on_surface_m' in B[key]: centre = np.array(B[key]['centre_on_surface_m'])
    out = {}
    files = [f for f in glob.glob(f'{run}/**/*', recursive=True) if f.endswith('.raw') and 'processor' not in f]
    print('SET_FILES', [str(Path(f).relative_to(run)) for f in files][:20], flush=True)
    for f in files:
        name = Path(f).stem
        if not re.search(r'wrong|neg|concave|underdetermined|zeroVol|skew', name, re.I):
            continue
        P = vtk_points(f)
        if len(P) == 0: continue
        c = P.mean(0)   # crude: per-set; also per point stats below
        a, b = ep[:, 0], ep[:, 1]; ab = b - a
        def dseg(p):
            t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-18), 0, 1)
            return np.linalg.norm(a + t[:, None] * ab - p, axis=1).min()
        de = np.array([dseg(p) for p in P[:: max(1, len(P) // 200)]]) * 1e3
        ds = np.abs(trimesh.proximity.signed_distance(car, P[:: max(1, len(P) // 200)])) * 1e3
        z = P[:, 2] * 1e3
        dc = np.linalg.norm(P - centre, axis=1) * 1e3 if centre is not None else np.array([np.nan])
        out[name] = dict(n_points=len(P), sharp_edge_mm=[round(float(np.median(de)), 3), round(float(de.max()), 3)],
                         wall_mm=[round(float(np.median(ds)), 3), round(float(ds.max()), 3)],
                         z_mm=[round(float(z.min()), 2), round(float(z.max()), 2)],
                         centre_mm=[round(float(np.min(dc)), 2), round(float(np.median(dc)), 2), round(float(np.max(dc)), 2)],
                         bbox_mm=(P.min(0) * 1e3).round(2).tolist() + (P.max(0) * 1e3).round(2).tolist())
    return out


def probe(cmd, run, bashrc, log, timeout_s, *a, **k):
    out = orig(cmd, run, bashrc, log, timeout_s, *a, **k)
    if log == 'checkMesh_morph.log':
        bad = [l.strip() for l in out.splitlines() if l.strip().startswith('***')]
        ok = 'Mesh OK' in out
        md = Path(run) / 'logs' / 'morph_displacement.txt'
        print(f"MORPH_RESULT {site} amp={os.environ.get('GATE_BUMP_A_MM', '1')}: {'Mesh OK' if ok else 'FAILED ' + str(bad)}", flush=True)
        if md.exists(): print('MORPH_DISPLACEMENT', md.read_text().replace('\n', ' | ')[:600], flush=True)
        if not ok:
            try:
                orig('checkMesh -writeSets raw', run, bashrc, 'checkMesh_sets.log', timeout_s)
                print('BAD_CELLS ' + json.dumps(classify(run)), flush=True)
            except Exception as e:
                print('CLASSIFY_ERROR', repr(e)[:300], flush=True)
        import shutil; shutil.rmtree(run, ignore_errors=True)
        raise SystemExit(0)
    return out


oc._run = probe
sys.argv = ['gate.py', 'bump', site, '4']
runpy.run_path(str(SP / 'gate.py'), run_name='__main__')
