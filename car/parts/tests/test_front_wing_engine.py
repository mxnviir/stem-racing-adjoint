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
S = fwe.Strut
OFF = S(t_mm=0.0)
CASES = {
    "one piece through the nose": dict(struts=(OFF, OFF)),
    "two halves rooted in the nose": dict(pieces=2, root_y_mm=9.0, struts=(OFF, OFF)),
    "one piece under the nose on a centre strut": dict(z_mm=6.5, chord_mm=18.0, struts=(S(t_mm=2.5, y_frac=0.0), OFF)),
    "two swept halves on raked, splayed pairs": dict(pieces=2, root_y_mm=5.0, sweep_deg=15.0, dihedral_deg=6.0,
                                                     chord_mm=20.0, z_mm=10.0,
                                                     struts=(S(t_mm=2.0, y_frac=0.4, rake_deg=15.0, splay_deg=-10.0),
                                                             S(t_mm=2.5, y_frac=0.9))),
    "the middle of every range": dict(),
}


@pytest.mark.parametrize("name", list(CASES))
def test_every_t8_gate_passes(name):
    r = fwe.build(fwe.FrontWingDesign(**CASES[name]), NOSE, X_FRONT, WHEEL)
    bad = {k: v for k, v in r["gates"].items() if v < 0}
    assert not bad, (name, bad, r["info"])
    assert r["info"]["supported"]
    w = r["wing"].copy(); w.apply_scale(1e3)
    assert w.is_watertight and len(w.split(only_watertight=False)) == 1


def test_sweep_is_repaired_not_refused():
    """A sweep that would carry the tip past Ref A moves the root forward; one that cannot fit in the
    40 mm overhang is reduced."""
    r = fwe.build(fwe.FrontWingDesign(sweep_deg=60.0, chord_mm=20.0), NOSE, X_FRONT, WHEEL)
    assert r["info"]["sweep_used_deg"] < 60.0
    assert r["gates"]["T8.5.2_fw_ahead_of_ref_A"] >= 0 and r["gates"]["T8.2_fw_inside_overhang"] >= 0


def test_a_short_tip_is_pushed_out_to_a_25_mm_segment():
    r = fwe.build(fwe.FrontWingDesign(tip_y_mm=20.0), NOSE, X_FRONT, WHEEL)
    assert r["gates"]["T8.6.1_fw_segment"] >= 0, r["info"]


def test_struts_reach_the_nose_or_are_reported():
    """Struts asked for far out (T8.5.1's 15 mm) where the nose is narrower land on the nose (leaned back
    if need be) or are reported; never a strut outside the support band."""
    r = fwe.build(fwe.FrontWingDesign(**CASES["two swept halves on raked, splayed pairs"]), NOSE, X_FRONT, WHEEL)
    for p in r["info"]["struts"]:
        assert abs(p["nose_mm"][1]) + p["t_mm"] / 2 <= fwe.SUPPORT_BAND_MM
    assert len(r["info"]["struts"]) + len(r["info"].get("struts_not_placed", [])) + len(r["info"].get("struts_in_the_nose", [])) == 2


def test_struts_all_under_the_wall_keep_the_thickest_when_nothing_holds_the_wing():
    r = fwe.build(fwe.FrontWingDesign(z_mm=6.5, chord_mm=18.0, struts=(S(t_mm=0.5), S(t_mm=0.8))), NOSE, X_FRONT, WHEEL)
    assert r["info"]["supported"]
