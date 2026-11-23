"""The free-form body and nose (freeform.py): a known solid read into the three surfaces comes back; the nose
stays inside T8.5.1's box, T8.2's 40 mm and T3.7's 1.5 mm and is one closed solid; CMA's numbers at zero
give the seed, and move the surfaces the way they say; the 27.175 mm sidepod top holds between the wheels."""
import numpy as np
import pytest
import trimesh

import freeform as fr

X_TIP, X_REAR = 0.0, 240.0


def _car():
    """A fuselage (40 wide, z 4-32) with wider sidepods (60 wide, z 6-22) between x 70 and 170, from x 0 to 240."""
    a = trimesh.creation.box(bounds=[[0, -20, 4], [240, 20, 32]])
    b = trimesh.creation.box(bounds=[[70, -30, 6], [170, 30, 22]])
    return trimesh.boolean.union([a, b], engine="manifold")


@pytest.fixture(scope="module")
def ff():
    return fr.fit([_car()], X_TIP, X_REAR, 24, 9, 12, blend_mm=0.5)


def test_a_known_solid_comes_back(ff):
    rng = np.random.default_rng(0)
    P = np.c_[rng.uniform(1, 239, 20000), rng.uniform(-35, 35, 20000), rng.uniform(0, 50, 20000)]
    inside = _car().contains(P)
    o = fr.field(ff, P[:, 0], P[:, 1], P[:, 2], X_TIP, X_REAR) < 0
    iou = (inside & o).sum() / (inside | o).sum()
    assert iou > 0.8, iou


def test_the_nose_is_legal_and_one_solid(ff):
    ref_a = 38.0
    nm = fr.build_nose(ff, X_TIP, X_REAR, ref_a)
    assert nm is not None
    v = nm["_full"].vertices * 1e3
    assert nm["_full"].is_watertight and len(nm["_full"].split(only_watertight=False)) == 1
    assert v[:, 1].max() <= fr.NOSE_HALF_MAX_MM + 1e-6           # T8.5.1 (the car is 40 wide: clipped to 30)
    assert v[:, 2].max() <= fr.NOSE_Z_MAX_MM + 1e-6 and v[:, 2].min() >= fr.TRACK_MM - 1e-6
    assert v[:, 0].min() >= ref_a - fr.NOSE_OVERHANG_MM - 1e-6
    assert nm["nose"].is_watertight and nm["nose"].vertices[:, 1].min() >= -1e-9


def test_cma_numbers_move_the_surfaces(ff):
    n = fr.n_genes()
    same = fr.from_unit(ff, np.zeros(n))
    assert np.allclose(same.top, ff.top) and np.allclose(same.side, ff.side)
    up = np.zeros(n); up[:10] = 1.0                              # the top's coarse grid all +1: 6 mm higher
    hi = fr.from_unit(ff, up)
    assert np.allclose(np.asarray(hi.top) - np.asarray(ff.top), 6.0, atol=1e-6)
    assert np.allclose(hi.bottom, ff.bottom)


def test_the_sidepod_top_holds_between_the_wheels(ff):
    u = np.zeros(fr.n_genes()); u[:10] = 3.0; u[20:] = 2.0      # top +18 mm, sides +12 mm everywhere
    tall = fr.from_unit(ff, u)
    P = np.array([[120.0, 25.0, 20.0], [120.0, 25.0, 30.0], [120.0, 5.0, 40.0], [20.0, 25.0, 30.0]])
    phi = fr.field(tall, P[:, 0], P[:, 1], P[:, 2], X_TIP, X_REAR, axles=(55.0, 185.0, None))
    assert phi[0] < 0                    # a sidepod under 27.175 mm
    assert phi[1] > 0                    # over it, outboard of the spine, between the wheels: cut
    assert phi[2] < 0                    # the spine itself may be taller
    assert phi[3] < 0                    # ahead of the front wheel the cap does not apply


def test_the_seed_nose_is_the_body_rounded_off_not_a_cone():
    """seed_nose: the body's Ref A section carried forward and rounded off at the tip asked for: round, not a
    point (halfway along, a cone is half as wide as at Ref A; this is over 0.7), nothing ahead of the tip."""
    ref_a, tip = 40.0, 20.0
    body = trimesh.boolean.intersection([_car(), trimesh.creation.box(bounds=[[ref_a, -50, 0], [240, 50, 60]])],
                                        engine="manifold")
    ff = fr.seed_nose(fr.fit([body], X_TIP, X_REAR, 24, 9, 12, blend_mm=0.5), body, ref_a, tip)
    nm = fr.build_nose(ff, X_TIP, X_REAR, ref_a)
    m = nm["_full"].copy(); m.apply_scale(1e3)
    assert m.bounds[0, 0] > tip - 4.0, m.bounds                  # the bicubic grid (10 mm) rounds the tip a little

    def half(x):
        s = m.section(plane_origin=np.array([x, 0.0, 0.0]), plane_normal=np.array([1.0, 0.0, 0.0]))
        return 0.0 if s is None else float(s.vertices[:, 1].max())
    front = m.bounds[0, 0]
    mid = 0.5 * (front + ref_a)
    assert half(mid) > 0.7 * half(ref_a - 1.0), (half(mid), half(ref_a - 1.0))
    assert half(ref_a - 1.0) > 14.5                              # the body's 20 mm half-width, clipped to T8.5.1 (15 less 0.2)


def test_the_floor_can_form_a_tunnel(ff):
    """Four points across the floor (gb=4): the centre raised between two lower hulls -- a catamaran tunnel --
    is something the search can make (with two the floor could only tilt into a V)."""
    gu, gv, gw, gb = 5, 2, 3, 4
    n = fr.n_genes(gu, gv, gw, gb)
    u = np.zeros(n)
    i0 = gu * gv                                           # the bottom's grid: (gu, gb), row-major
    B = np.zeros((gu, gb)); B[1:4, 0:2] = 1.5; B[1:4, 3] = -1.0   # centre up, outer edge down, mid-car
    u[i0:i0 + gu * gb] = B.ravel()
    t = fr.from_unit(ff, u, (6.0, 4.0, 6.0), gu, gv, gw, gb)
    _, bot, _ = fr.surfaces(t, np.array([120.0, 120.0]), np.array([0.0, 30.0]), np.array([0.0, 0.0]), X_TIP, X_REAR)
    _, bot0, _ = fr.surfaces(ff, np.array([120.0, 120.0]), np.array([0.0, 30.0]), np.array([0.0, 0.0]), X_TIP, X_REAR)
    assert bot[0] - bot0[0] > 4.0 and bot[1] - bot0[1] < -2.0   # the centre up, the edge down
