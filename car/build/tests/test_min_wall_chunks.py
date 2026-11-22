"""legality._min_wall_mm casts its rays in batches (memory): the same thinnest wall and the same
place as casting every ray at once, and the right wall on a known shape."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import paths  # noqa: F401,E402
import legality  # noqa: E402


def _tube(tmp_path, wall=1.2):
    import trimesh
    m = trimesh.creation.annulus(r_min=6.0, r_max=6.0 + wall, height=20.0, sections=96)
    p = tmp_path / "tube.stl"
    m.export(p)
    return str(p), m


def test_batches_give_the_same_answer_as_one_cast(tmp_path, monkeypatch):
    path, m = _tube(tmp_path)
    got = {}
    for chunk in (1, 7, 200, 10 ** 9):
        monkeypatch.setattr(legality._first_hits, "__defaults__", (chunk,))
        got[chunk] = legality._min_wall_mm(path, n=600)
    first = got[10 ** 9]
    for c, v in got.items():
        assert v[0] == first[0] and v[1] == first[1], (c, v, first)


def test_batched_cast_equals_trimesh_per_ray(tmp_path):
    path, m = _tube(tmp_path)
    rng = np.random.default_rng(0)
    pts, fi = __import__("trimesh").sample.sample_surface_even(m, 300, seed=1)
    nrm = m.face_normals[fi]
    o = pts - nrm * 1e-4
    l1, r1, t1 = m.ray.intersects_location(o, -nrm, multiple_hits=False)
    l2, r2, t2 = legality._first_hits(m, o, -nrm, chunk=int(rng.integers(3, 50)))
    a = sorted(zip(r1.tolist(), t1.tolist()))
    b = sorted(zip(r2.tolist(), t2.tolist()))
    assert a == b
    assert np.allclose(sorted(map(tuple, np.round(l1, 9))), sorted(map(tuple, np.round(l2, 9))))


def test_known_wall(tmp_path):
    path, _ = _tube(tmp_path, wall=1.2)
    t, where = legality._min_wall_mm(path, n=800)
    assert abs(t - 1.2) < 0.05, t          # straight across the tube wall (end faces are 20 mm apart)
    assert where is not None
