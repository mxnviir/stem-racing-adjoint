"""The searches' rear wing (rear_wing_engine.py) on a synthetic tail: a spine over the chamber and two
rearpods. The same few numbers reach every kind of support -- a strut on the chamber's top, a pair splayed
onto the pods, a slotted root in a pod -- and each built wing passes every gate it measures. A strut aimed
at nothing is leaned back until it lands or is reported, never dropped silently."""
import numpy as np
import pytest
import trimesh

import component_contract as cc
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
S = rwe.Strut
CASES = {
    "one strut on the chamber's top": rwe.RearWingDesign(),
    "a pair splayed onto the pods": rwe.RearWingDesign(half_span_mm=34.0, struts=(S(t_mm=2.5, y_frac=0.55, splay_deg=20.0),)),
    "a slotted pair in the pods": rwe.RearWingDesign(half_span_mm=34.0, chord_mm=20.0,
                                                     struts=(S(t_mm=2.5, y_frac=0.75, slot_mm=5.0, chord_mm=8.0),)),
    "two pairs, swept and inverted": rwe.RearWingDesign(camber=-0.04, aoa_deg=-3.0, sweep_deg=12.0, dihedral_deg=6.0,
                                                        half_span_mm=33.0,
                                                        struts=(S(t_mm=2.0), S(t_mm=2.2, y_frac=0.8, rake_deg=10.0))),
}


@pytest.fixture(scope="module")
def built():
    return {k: rwe.build(d, BODY, XF, W, WHEEL, forward_parts=[BODY]) for k, d in CASES.items()}


@pytest.mark.parametrize("name", list(CASES))
def test_every_gate_passes(built, name):
    r = built[name]
    bad = {k: v for k, v in r["gates"].items() if v < 0}
    assert not bad, (name, bad, r["info"])
    assert r["info"]["supported"] and not r["info"].get("struts_not_placed")
    for m in [r["wing"]] + r["struts"]:
        q = m.copy(); q.apply_scale(1e3)
        assert q.is_volume


def test_the_pods_hold_the_splayed_pair(built):
    feet = [s["foot_mm"] for s in built["a pair splayed onto the pods"]["info"]["struts"]]
    assert feet and all(f[1] > 13.0 and abs(f[2] - 26.0) < 0.5 for f in feet), feet


def test_a_slot_is_cut_where_there_is_foam_for_it(built):
    r = built["a slotted pair in the pods"]
    st = r["info"]["struts"]
    assert st and st[0]["slot_mm"] > 1.0, r["info"]
    assert r["plugs"] and r["gates"]["rw_slot0_foam"] >= 0


def test_a_slot_over_the_chamber_is_glued_instead():
    """Over the cartridge the body is the T5.5 wall's 3 mm: no slot there, a glued foot instead."""
    r = rwe.build(rwe.RearWingDesign(struts=(S(t_mm=3.0, slot_mm=4.0),)), BODY, XF, W, WHEEL, forward_parts=[BODY])
    assert r["info"]["struts"] and r["info"]["struts"][0]["slot_mm"] == 0.0
    assert r["info"].get("slots_glued_instead") == [0]


def test_a_strut_aimed_at_nothing_is_reported_not_dropped():
    """A pair splayed far outboard past the pods lands (leaned back) or is reported; with none placed the
    wing is not held and the gate says so."""
    r = rwe.build(rwe.RearWingDesign(half_span_mm=40.0, struts=(S(t_mm=2.0, y_frac=1.0, splay_deg=40.0),)),
                  BODY, XF, W, WHEEL, forward_parts=[BODY])
    placed, missed = r["info"]["struts"], r["info"].get("struts_not_placed", [])
    assert placed or missed == [0]
    if not placed:
        assert r["gates"]["rw_supported"] < 0
    else:
        assert abs(placed[0]["lean_deg"][1]) < 40.0      # leaned back towards the vertical


def test_limits_are_repaired_into_t9():
    r = rwe.build(rwe.RearWingDesign(chord_mm=40.0, t_mm=9.0, half_span_mm=10.0, x_le_mm=60.0, sweep_deg=60.0,
                                     dihedral_deg=60.0), BODY, XF, W, WHEEL, forward_parts=[BODY])
    for k in ("T9.4.1_rw_behind_ref_B", "T9.4.2_rw_overhang", "T9.5.1_rw_span", "T9.5.2_rw_chord_max",
              "T9.5.3_rw_thick_max", "T9.5.4_rw_height_change"):
        assert r["gates"][k] >= 0, (k, r["gates"][k], r["info"])
