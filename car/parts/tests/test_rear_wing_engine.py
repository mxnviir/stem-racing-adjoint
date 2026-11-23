"""The searches' rear wing (rear_wing_engine.py) on a synthetic tail: a spine over the chamber and two
rearpods. The wing is straight; its supports are lofts grown from the wing to the body (wing_loft.py), from
just off the centre line out to the tips. Each built wing passes every gate it measures."""
import io

import numpy as np
import pytest
import trimesh

import rear_wing_engine as rwe

XF, W = 53.9, 122.0
WHEEL = (XF + W, 24.875, 14.13, 9.0)


def _tail():
    """Right half (metres): a spine |y| <= 14 up to z 43 (the chamber's wall), pods |y| 18-35 up to z 26."""
    spine = trimesh.creation.box(bounds=[[150.0, 0.0, 8.0], [240.0, 14.0, 43.0]])
    pod = trimesh.creation.box(bounds=[[192.0, 13.0, 8.0], [240.0, 35.0, 26.0]])
    m = trimesh.boolean.union([spine, pod], engine="manifold")
    m.apply_scale(1e-3)
    return m


BODY = _tail()
S = rwe.Support
OFF = S(width_mm=0.0)
CASES = {
    "the middle of every range": rwe.RearWingDesign(),
    "a pair near the centre onto the spine": rwe.RearWingDesign(supports=(S(width_mm=4.0, y_frac=0.0), OFF)),
    "a pair at the tips onto the pods, flared": rwe.RearWingDesign(half_span_mm=34.0, supports=(
        S(width_mm=8.0, y_frac=1.0, chord_frac=1.0, foot_scale=1.8, waist=0.4), OFF)),
    "two pairs, a wide chord, a thick wing": rwe.RearWingDesign(chord_mm=22.0, t_mm=4.0, half_span_mm=32.0, lift_mm=4.0,
                                                               supports=(S(width_mm=3.0, y_frac=0.2), S(width_mm=10.0, y_frac=0.9))),
}


@pytest.fixture(scope="module")
def built():
    return {k: rwe.build(d, BODY, XF, W, WHEEL, forward_parts=[BODY]) for k, d in CASES.items()}


@pytest.mark.parametrize("name", list(CASES))
def test_every_gate_passes(built, name):
    r = built[name]
    bad = {k: v for k, v in r["gates"].items() if v < 0}
    assert not bad, (name, bad, r["info"])
    assert r["info"]["supported"] and not r["info"].get("supports_not_placed")
    for m in [r["wing"]] + r["struts"]:
        q = m.copy(); q.apply_scale(1e3)
        assert q.is_volume
    back = trimesh.load(io.BytesIO(trimesh.util.concatenate([r["wing"]] + r["struts"]).export(file_type="stl_ascii").encode()),
                        file_type="stl")
    assert back.is_volume


def test_the_wing_is_straight(built):
    w = built["two pairs, a wide chord, a thick wing"]["wing"].copy(); w.apply_scale(1e3)
    b = [w.section(plane_origin=[0, y, 0], plane_normal=[0, 1.0, 0]).bounds for y in (3.0, 15.0, 30.0)]
    assert np.allclose(b[0][:, [0, 2]], b[1][:, [0, 2]], atol=1e-3) and np.allclose(b[1][:, [0, 2]], b[2][:, [0, 2]], atol=1e-3)


def test_tip_supports_land_on_the_pods(built):
    feet = [s["foot_mm"] for s in built["a pair at the tips onto the pods, flared"]["info"]["struts"]]
    assert feet and all(f[1] > 13.0 and abs(f[2] - 26.0) < 0.5 for f in feet), feet


def test_a_support_meets_the_body_flush_not_inside_it(built):
    """Its base is cut to the body's surface: no support inside the foam."""
    r = built["a pair near the centre onto the spine"]
    s = r["struts"][0].copy(); s.apply_scale(1e3)
    b = BODY.copy(); b.apply_scale(1e3)
    i = trimesh.boolean.intersection([s, b], engine="manifold")
    assert i.is_empty or abs(i.volume) < 0.05
    assert trimesh.proximity.closest_point(b, s.vertices)[1].min() < 1e-3        # and it touches it


def test_nothing_on_the_centre_line(built):
    for r in built.values():
        for s in r["struts"]:
            assert s.vertices[:, 1].min() * 1e3 >= rwe.CENTRE_CLEAR_MM - 0.06


def test_supports_under_the_wall_widen_the_widest():
    r = rwe.build(rwe.RearWingDesign(supports=(S(width_mm=0.7), S(width_mm=0.5))), BODY, XF, W, WHEEL, forward_parts=[BODY])
    assert r["info"].get("support_widened_to_wall") == 0 and r["info"]["supported"]


def test_limits_are_repaired_into_t9():
    r = rwe.build(rwe.RearWingDesign(chord_mm=40.0, t_mm=9.0, half_span_mm=10.0, x_le_mm=60.0), BODY, XF, W, WHEEL,
                  forward_parts=[BODY])
    for k in ("T9.4.1_rw_behind_ref_B", "T9.4.2_rw_overhang", "T9.5.1_rw_span", "T9.5.2_rw_chord_max",
              "T9.5.3_rw_thick_max"):
        assert r["gates"][k] >= 0, (k, r["gates"][k], r["info"])
