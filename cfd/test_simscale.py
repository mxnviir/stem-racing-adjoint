"""The SimScale route without SimScale: what runs on this machine before a car is uploaded, and the
evaluator's bookkeeping when SimScale answers.

  * a car solid -> clean surface (layout_wrap) -> reduced -> air volume with exact, rounded wheels (STEP),
    every boundary named, the car's volume removed, nothing sealed;
  * a diverged or absurd force history is not scored;
  * a key SimScale refuses (403) is retired and its unfinished cases move to the next key.

    python -m pytest cfd/test_simscale.py -q
"""
import json
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
import repo_paths  # noqa: E402,F401
from types import SimpleNamespace  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402


def _toy_car(folder):
    """A rounded slab 120 x 40 x 20 mm on two pairs of 28 mm wheels: body_full.stl (m) and the +y wheels."""
    import manifold3d as mf
    import trimesh
    body = mf.Manifold.cube([120.0, 40.0, 20.0], True).translate([70.0, 0.0, 16.0])
    body = body + mf.Manifold.sphere(12.0, 48).scale([1.0, 1.6, 0.8]).translate([10.0, 0.0, 16.0])
    g = body.to_mesh()
    car = trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts), process=True)
    car.apply_scale(1e-3)
    car.export(folder / "body_full.stl")
    wheels = {}
    for name, x in (("wheelF", 30.0), ("wheelR", 120.0)):
        w = trimesh.creation.cylinder(radius=14.0, height=14.0, sections=96)
        w.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        w.apply_translation([x, 30.0, 14.0 - 0.3])
        w.apply_scale(1e-3)
        w.export(folder / f"{name}.stl")
        wheels[name] = [x / 1e3, 30.0 / 1e3, (14.0 - 0.3) / 1e3]
    (folder / "wheels.json").write_text(json.dumps(wheels))
    return car


def test_air_volume_of_a_toy_car(tmp_path):
    import manifold3d as mf
    import trimesh
    import layout_wrap as LW
    import simscale_layout as SL
    car = _toy_car(tmp_path)
    M = mf.Manifold(mf.Mesh(vert_properties=np.array(car.vertices * 1e3, np.float32),
                            tri_verts=np.array(car.faces, np.uint32)))
    w = LW.wrap(M, 0.5)
    q = LW.quality(w)
    assert q["closed"] and abs(w.volume / M.volume() - 1) < 0.02, (q, w.volume, M.volume())
    dec = LW.reduce(w, 4000)
    assert LW.quality(dec)["closed"] and LW.self_intersections(dec) == 0
    boxes = {n: trimesh.load(tmp_path / f"{n}.stl", force="mesh").bounds * 1e3 for n in ("wheelF", "wheelR")}
    rep = SL.air_volume(dec, boxes, tmp_path / "domain.step", domain=((-200.0, 0.0, 0.0), (500.0, 120.0, 150.0)))
    assert 0.97 < rep["removed_share"] < 1.03, rep
    assert rep["sealed_mm3"] == 0.0, rep
    for n in ("inlet", "outlet", "symmetry", "side", "top", "ground", "wheelF", "wheelR"):
        assert rep["faces"].get(n), (n, rep["faces"])
    assert (tmp_path / "domain.step").stat().st_size > 0


def test_diverged_forces_are_not_scored():
    from simscale_step_eval import diverged_forces
    assert not diverged_forces(0.20, 0.01, {"Fx_window_std": 0.001})
    assert diverged_forces(float("nan"), 0.01, {"Fx_window_std": 0.001})
    assert diverged_forces(4.64, 637.0, {"Fx_window_std": 0.001})          # the c00068 blow-up
    assert diverged_forces(0.20, 0.01, {"Fx_window_std": 0.05})            # still swinging


def test_a_refused_key_is_retired_and_its_cases_move(tmp_path, monkeypatch):
    import simscale_step_eval as SE

    class ApiException(Exception):
        def __init__(self, status):
            super().__init__(f"({status})")
            self.status = status

    monkeypatch.setenv("SIMSCALE_API_KEYS", "simscale_ak_firstkey,simscale_ak_secondkey")
    ev = SE.SimScaleStepEvaluator(None, tmp_path / "state.json", runs_per_key=None,
                                  sdk=SimpleNamespace(ApiException=ApiException))
    k1, k2 = list(ev.keys)
    ev.submit([{"id": "a", "folder": str(tmp_path)}, {"id": "b", "folder": str(tmp_path)}])
    ev.st["cases"]["a"].update(fp=k1, phase="import")
    ev.st["cases"]["b"].update(fp=k1, phase="run")                        # already running: it stays
    ev._on_error("a", ApiException(403))
    assert ev.st["keys"][k1]["retired"]
    assert ev.st["cases"]["a"]["fp"] is None and ev.st["cases"]["a"]["phase"] == "wait"
    assert ev.st["cases"]["b"]["fp"] == k1
    assert ev._live_keys() == [k2]
    assert ev.st["events"][-1]["event"] == "key_retired"


if __name__ == "__main__":
    sys_exit = pytest.main([__file__, "-q"])
    raise SystemExit(sys_exit)
