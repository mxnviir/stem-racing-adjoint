"""The searches' rear wing (rear_wing_engine.py) on a synthetic tail: a spine over the chamber and two
rearpods. The wing is straight; its supports are a pair at its sides -- each covers a tip, where the aerofoil
shows, and is lofted down to the body (wing_loft.py), as appendix iv's rear wings all stand. Every gate passes."""
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


def _spine_only():
    m = trimesh.creation.box(bounds=[[150.0, 0.0, 8.0], [240.0, 14.0, 43.0]])
    m.apply_scale(1e-3)
    return m


BODY, SPINE = _tail(), _spine_only()
S = rwe.Support
CASES = {
    "the middle of every range, over the pods": (rwe.RearWingDesign(), BODY),
    "a wide wing, its sides down onto the pods, flared": (rwe.RearWingDesign(half_span_mm=29.0, support=S(
        plate_mm=5.0, ext=0.6, rise_mm=6.0, foot_scale=1.8, waist=0.4)), BODY),
    "nothing under the tips: the sides curve in to the spine": (rwe.RearWingDesign(half_span_mm=30.0), SPINE),
    "a wide chord, a thick wing, lifted": (rwe.RearWingDesign(chord_mm=22.0, t_mm=4.0, lift_mm=4.0), BODY),
}


@pytest.fixture(scope="module")
def built():
    return {k: (rwe.build(d, b, XF, W, WHEEL, forward_parts=[b]), b) for k, (d, b) in CASES.items()}


@pytest.mark.parametrize("name", list(CASES))
def test_every_gate_passes(built, name):
    r, _ = built[name]
    bad = {k: v for k, v in r["gates"].items() if v < 0}
    assert not bad, (name, bad, r["info"])
    assert r["info"]["supported"] and not r["info"].get("supports_not_placed")
    for m in [r["wing"]] + r["struts"]:
        q = m.copy(); q.apply_scale(1e3)
        assert q.is_volume
    back = trimesh.load(io.BytesIO(trimesh.util.concatenate([r["wing"]] + r["struts"]).export(file_type="stl_ascii").encode()),
                        file_type="stl")
    assert back.is_volume


@pytest.mark.parametrize("name", list(CASES))
def test_the_supports_are_at_the_sides_covering_the_aerofoil(built, name):
    """Each side support covers its tip's whole aerofoil face, there and not under the wing."""
    r, _ = built[name]
    w = r["wing"].copy(); w.apply_scale(1e3)
    s = r["struts"][0].copy(); s.apply_scale(1e3)
    tip = w.bounds[1, 1]
    face = w.section(plane_origin=[0, tip - 0.05, 0], plane_normal=[0, 1.0, 0]).vertices
    P = np.c_[face[:, 0], np.full(len(face), tip + 0.1), np.clip(face[:, 2], w.bounds[0, 2] + 0.05, w.bounds[1, 2] - 0.05)]
    assert s.contains(P).mean() > 0.97
    under = s.vertices[(s.vertices[:, 2] > w.bounds[0, 2] + 0.05) & (s.vertices[:, 2] < w.bounds[1, 2])]
    assert under[:, 1].min() >= tip - 0.31             # nothing of it under the wing, inboard of the tip


def test_the_wing_is_straight(built):
    w = built["a wide chord, a thick wing, lifted"][0]["wing"].copy(); w.apply_scale(1e3)
    b = [w.section(plane_origin=[0, y, 0], plane_normal=[0, 1.0, 0]).bounds for y in (3.0, 12.0, 24.0)]
    assert np.allclose(b[0][:, [0, 2]], b[1][:, [0, 2]], atol=1e-3) and np.allclose(b[1][:, [0, 2]], b[2][:, [0, 2]], atol=1e-3)


def test_sides_land_on_whatever_body_is_there(built):
    f = built["a wide wing, its sides down onto the pods, flared"][0]["info"]["struts"][0]["foot_mm"]
    assert f[1] > 13.0 and abs(f[2] - 26.0) < 0.5, f
    g = built["nothing under the tips: the sides curve in to the spine"][0]["info"]["struts"][0]["foot_mm"]
    assert g[1] <= 14.0 + 1e-6, g


def test_a_support_meets_the_body_flush_not_inside_it(built):
    r, b = built["the middle of every range, over the pods"]
    s = r["struts"][0].copy(); s.apply_scale(1e3)
    bb = b.copy(); bb.apply_scale(1e3)
    i = trimesh.boolean.intersection([s, bb], engine="manifold")
    assert i.is_empty or abs(i.volume) < 0.05
    assert trimesh.proximity.closest_point(bb, s.vertices)[1].min() < 1e-3


def test_limits_are_repaired_into_t9():
    r = rwe.build(rwe.RearWingDesign(chord_mm=40.0, t_mm=9.0, half_span_mm=10.0, x_le_mm=60.0), BODY, XF, W, WHEEL,
                  forward_parts=[BODY])
    for k in ("T9.4.1_rw_behind_ref_B", "T9.4.2_rw_overhang", "T9.5.1_rw_span", "T9.5.2_rw_chord_max",
              "T9.5.3_rw_thick_max", "T3.4_rw_width"):
        assert r["gates"][k] >= 0, (k, r["gates"][k], r["info"])
