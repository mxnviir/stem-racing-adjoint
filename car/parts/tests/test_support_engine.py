"""The searches' wheel supports (support_engine.py) on a synthetic body whose floor has a channel along
its centre (as the front of the search cars has): one closed printed piece per axle, the saddle flush
with the underside and continuous across the channel, every rule, load and machining gate passing, the
slot cut from below with 3 mm of foam over it, and a design that cannot fit refused by name."""
import numpy as np
import pytest

import support_engine as se

R = 14.12
Z_AXLE = R - 0.3
HUB = (5.25, 8.25)


def _body_m():
    """Right half (y >= 0), metres: a 200 x 14 x 24 mm block, floor at z 4, with a 3 mm-wide, 4 mm-deep
    channel along the centre of its floor, and a rounded lower side."""
    import manifold3d as mf
    blk = mf.Manifold.cube([200.0, 14.0, 24.0]).translate([0.0, 0.0, 4.0])
    chan = mf.Manifold.cube([202.0, 3.0, 4.0]).translate([-1.0, -0.5, 3.5])
    side = (mf.Manifold.cube([202.0, 5.0, 5.0]).translate([-1.0, 10.0, 3.0])
            - mf.Manifold.cylinder(202.0, 4.0, 4.0, 64).rotate([0.0, 90.0, 0.0]).translate([-1.0, 10.0, 8.0]))
    M = (blk - chan) - side
    t = se._to_trimesh(M)
    t.apply_scale(1e-3)
    return t


AXLES = [("front", 50.0, Z_AXLE, R, 23.25, 13.25, HUB), ("rear", 170.0, Z_AXLE, R, 16.25, 17.25, HUB)]


@pytest.fixture(scope="module")
def built():
    return se.build(se.SupportDesign(), _body_m(), AXLES)


def test_one_closed_piece_per_axle_and_every_gate_passes(built):
    t = built["support"]
    parts = t.split(only_watertight=False)
    assert t.is_watertight and len(parts) == 2, (t.is_watertight, len(parts))
    bad = {k: v for k, v in built["gates"].items() if v < 0}
    assert not bad, bad
    for tag in ("front", "rear"):
        st = built["info"][tag]
        assert st["pieces"] == 1 and st["pinch_edges_left"] == 0, st
        assert 0.5 < st["part_g_each"] < 6.0, st
        assert st["net_g_each"] < st["part_g_each"]                     # the foam it replaces is taken off


def test_saddle_is_flush_and_spans_the_channel(built):
    """Across the axle the support's underside is the body's: on the floor (z 4) either side of the
    channel and on the channel's ceiling (z 7.5); and the section is ONE region across the channel."""
    t = built["support"].copy(); t.apply_scale(1e3)
    sec = t.section(plane_origin=[50.0, 0, 0], plane_normal=[1, 0, 0])
    p, _ = sec.to_planar(to_2D=np.array([[0, 1.0, 0, 0], [0, 0, 1.0, 0], [1.0, 0, 0, -50.0], [0, 0, 0, 1.0]]), check=False)
    polys = p.polygons_full
    big = max(polys, key=lambda q: q.area)
    from shapely.geometry import Point
    assert big.contains(Point(1.5, 8.0))                 # over the channel (y < 3): on its ceiling
    assert big.contains(Point(5.0, 4.5))                 # over the floor beside it
    assert big.contains(Point(3.2, 6.0))                 # up the channel's wall: one piece across
    from shapely.geometry import box
    under = big.intersection(box(4.0, -1.0, 9.0, 30.0))                 # under the body, beside the channel
    assert under.bounds[1] == pytest.approx(4.0, abs=0.05)              # its underside is the floor's


def test_rules_measured_not_assumed(built):
    g = built["gates"]
    for tag in ("front", "rear"):
        assert g[f"T7.12.1_{tag}_support_in_cylinder"] >= 0.0
        assert g[f"T7.13_{tag}_support_clear_of_claw"] >= 0.0
        assert g[f"T3.7_{tag}_support_clearance"] >= 0.0
        assert g[f"machining_{tag}_foam_over_slot"] >= 0.0
        assert g[f"machining_{tag}_slot_cut_from_below"] >= 0.0
        assert g[f"load_{tag}_bearing_sag"] >= 0.0


def test_loads_size_a_thin_arm_up():
    """An arm asked 1.2 mm thick is grown until the loads pass (lightest that passes)."""
    r = se.build(se.SupportDesign(t_mm=1.2), _body_m(), AXLES[:1])
    st = r["info"]["front"]
    assert st["t_mm"] > 1.2 and st["sizing_iterations"] >= 1, st
    assert r["gates"]["load_front_arm_stress"] >= 0 and r["gates"]["load_front_bearing_sag"] >= 0


def test_a_disc_too_big_for_the_rim_is_refused():
    r = se.build(se.SupportDesign(disc_r_mm=13.6), _body_m(), AXLES[:1])
    assert r["gates"]["fit_front_disc_in_rim"] < 0


def test_ceiling_is_what_the_ball_can_mill():
    """A step in the ceiling narrower than the ball is not cut: the opening never raises the ceiling and
    leaves no bump narrower than the ball's diameter."""
    xs = np.arange(0.0, 20.0, se.GRID_MM)
    ys = np.arange(0.0, 15.0, se.GRID_MM)
    zb = np.full((len(xs), len(ys)), 4.0)
    zt = np.full_like(zb, 28.0)
    Z, short = se.slot_ceiling(zb, zt, xs, 10.0, 12.0, 3.0)
    inside = Z[np.abs(xs - 10.0) < 2.0][:, 5]
    assert np.allclose(inside, 7.0, atol=1e-6), inside                 # h over the floor in the middle
    edge = Z[np.argmin(np.abs(xs - 15.9)), 5]
    assert edge < 7.0                                                   # the ball's radius at the chord's end
    assert not short.any()
