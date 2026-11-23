"""The searches' front wing (front_wing_engine.py) on a synthetic nose: one piece through the nose, two
halves rooted in its sides, one piece on a centre-line pylon, two swept halves on twin pylons. Each
passes every T8 gate it measures; sweep, overhang, span and pylon placement are repaired, not refused."""
import numpy as np
import pytest
import trimesh

import front_wing_engine as fwe

X_FRONT = 55.4                    # Ref A at 39.4
WHEEL = (55.4, 23.25, 14.12)


def _nose_m():
    """A nose ahead of Ref A: an ellipsoid-ish loft from the tip (x 0) to Ref A, 10 mm half-width, z 5-20."""
    import manifold3d as mf
    import support_engine as se
    st = []
    for x in np.linspace(0.5, 41.0, 20):
        s = min(1.0, (x / 41.0) ** 0.5)
        th = np.linspace(0, 2 * np.pi, 48, endpoint=False)
        st.append((x, np.c_[10.0 * s * np.cos(th), 12.5 + 7.5 * s * np.sin(th)]))
    # loft along x: sections in (y, z) stacked along x
    rings = [np.c_[np.full(len(P), x), P[:, 0], P[:, 1]] for x, P in st]
    n, N = len(rings[0]), len(rings)
    V = np.vstack(rings + [rings[0].mean(0)[None], rings[-1].mean(0)[None]])
    F = []
    for i in range(N - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            c, d = (i + 1) * n + j, (i + 1) * n + (j + 1) % n
            F += [(a, b, d), (a, d, c)]
    for j in range(n):
        F.append((N * n, (j + 1) % n, j)); F.append((N * n + 1, (N - 1) * n + j, (N - 1) * n + (j + 1) % n))
    m = trimesh.Trimesh(V, np.array(F), process=False)
    if m.volume < 0:
        m.invert()
    M = se._to_manifold(m) ^ se._box(-1e3, 1e3, 0.0, 1e3, -1e3, 1e3)
    t = se._to_trimesh(M); t.apply_scale(1e-3)
    return t


NOSE = _nose_m()
S = fwe.Support
CASES = {
    "one piece through the nose": dict(),
    "one piece set under the nose: moved into it": dict(pieces=1, z_mm=6.5, chord_mm=18.0),
    "two halves rooted in the nose": dict(pieces=2, root_y_mm=4.0),
    "two halves off the nose, their ends swept into it": dict(pieces=2, root_y_mm=13.0, chord_mm=20.0,
                                                             support=S(aim_out_deg=20.0, leave=0.5, arrive=0.6, flare=2.0)),
    "the middle of every range": dict(pieces=2),
}


@pytest.mark.parametrize("name", list(CASES))
def test_every_t8_gate_passes(name):
    r = fwe.build(fwe.FrontWingDesign(**CASES[name]), NOSE, X_FRONT, WHEEL)
    bad = {k: v for k, v in r["gates"].items() if v < 0}
    assert not bad, (name, bad, r["info"])
    assert r["info"]["supported"]
    w = r["wing"].copy(); w.apply_scale(1e3)
    assert w.is_watertight and len(w.split(only_watertight=False)) == 1


def test_the_wing_is_straight():
    """Level and square to the car: every vertical cut across the span is the same section, at one height."""
    r = fwe.build(fwe.FrontWingDesign(**CASES["the middle of every range"]), NOSE, X_FRONT, WHEEL)
    w = r["wing"].copy(); w.apply_scale(1e3)
    cuts = [w.section(plane_origin=[0, y, 0], plane_normal=[0, 1.0, 0]) for y in (16.0, 26.0, 34.0)]
    b = [c.bounds for c in cuts if c is not None]
    assert len(b) == 3 and np.allclose(b[0][:, [0, 2]], b[1][:, [0, 2]], atol=1e-3) and np.allclose(b[1][:, [0, 2]], b[2][:, [0, 2]], atol=1e-3)


def test_a_short_tip_is_pushed_out_to_a_25_mm_segment():
    r = fwe.build(fwe.FrontWingDesign(tip_y_mm=20.0), NOSE, X_FRONT, WHEEL)
    assert r["gates"]["T8.6.1_fw_segment"] >= 0, r["info"]


def test_a_split_wing_is_held_by_its_ends():
    """Off the nose, each half's inner end (its aerofoil face) is swept into the nose: inside T8.5.1's band."""
    r = fwe.build(fwe.FrontWingDesign(**CASES["two halves off the nose, their ends swept into it"]), NOSE, X_FRONT, WHEEL)
    assert r["info"]["struts"] and r["pylons"] is not None, r["info"]
    pb = r["pylons"].bounds * 1e3
    wb = r["wing"].bounds * 1e3
    assert pb[1, 1] <= wb[0, 1] + 0.31 + 1e-6            # the strut leaves through the end face, inwards
    assert pb[1, 1] <= fwe.SUPPORT_BAND_MM and pb[1, 2] <= 25.0


def test_one_piece_is_always_held_by_the_nose():
    for kw in (CASES["one piece through the nose"], CASES["one piece set under the nose: moved into it"]):
        r = fwe.build(fwe.FrontWingDesign(**kw), NOSE, X_FRONT, WHEEL)
        assert r["info"]["held_by_nose"] and r["info"]["supported"]
