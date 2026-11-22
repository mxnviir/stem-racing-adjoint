"""A pocket face meeting the skin at 15 deg leaves a knife edge of foam (start car: 0.02-0.06 mm
beside the front pod and the nose socket, lab 43907299154). sliver_wedges takes it out within
the pocket's band and nowhere else; join_wedge refuses a wedge that would stand alone."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "build"))
import joints  # noqa: E402
import legality as lg  # noqa: E402

MM = 1e-3


def _foam_and_cut():
    foam = trimesh.creation.box(bounds=[[0, -20 * MM, 0], [60 * MM, 20 * MM, 20 * MM]])
    # a slab whose top face rises at 15 deg and meets the foam's top (z 20) at x 30
    slab = trimesh.creation.box(extents=[120 * MM, 60 * MM, 40 * MM])
    slab.apply_translation([0, 0, -20 * MM])                              # top face at z 0
    slab.apply_transform(trimesh.transformations.rotation_matrix(math.radians(15), [0, -1, 0]))
    slab.apply_translation([30 * MM, 0, 20 * MM])
    cut = joints._bool("intersection", [slab, trimesh.creation.box(
        bounds=[[5 * MM, -25 * MM, 8 * MM], [45 * MM, 25 * MM, 30 * MM]])])
    pocketed = joints._bool("difference", [foam, cut])
    return pocketed, cut


def _wall(mesh, tmp_path, name, n=20000):
    m = mesh.copy()
    m.apply_scale(1e3)
    p = tmp_path / f"{name}.stl"
    m.export(p)
    return lg._min_wall_mm(str(p), n=n)[0]


def test_knife_edge_before_none_after(tmp_path):
    foam, cut = _foam_and_cut()
    assert _wall(foam, tmp_path, "before") < 1.0                          # the knife edge is there
    wedges, after = joints.sliver_wedges(foam, {"supports": cut})
    assert set(wedges) == {"supports"} and wedges["supports"].volume > 0
    assert _wall(after, tmp_path, "after") >= joints.MACHINED_WALL_MM     # the referee's own rule


def test_nothing_moves_outside_the_band():
    foam, cut = _foam_and_cut()
    wedges, after = joints.sliver_wedges(foam, {"supports": cut})
    w = wedges["supports"]
    # foam before = foam after + wedge (asserted inside sliver_wedges too), and the wedge is
    # within the band of the cut
    assert abs(foam.volume - after.volume - w.volume) < 1e-11            # 0.01 mm3
    lo, hi = cut.bounds
    r = joints.MACHINED_WALL_MM / 2 + joints.SLIVER_MARGIN_MM
    band = (joints.SLIVER_BAND_MM + 3 * r + 0.2) * MM + 1e-6                # the wedge's stated reach
    assert np.all(w.bounds[0] >= lo - band) and np.all(w.bounds[1] <= hi + band)
    # the foam's far end and its sharp outer corners (x 60, no pocket near) are untouched
    far = trimesh.creation.box(bounds=[[55 * MM, -21 * MM, -1 * MM], [61 * MM, 21 * MM, 21 * MM]])
    a = joints._bool("intersection", [foam, far]).volume
    b = joints._bool("intersection", [after, far]).volume
    assert abs(a - b) < 1e-15                                             # not a vertex moved
    # the square rim (the cut's x 45 face meets the top at 90 deg) is not thin: it stays foam
    rim = trimesh.creation.box(bounds=[[45 * MM, -15 * MM, 16 * MM], [48 * MM, 15 * MM, 21 * MM]])
    a = joints._bool("intersection", [foam, rim]).volume
    b = joints._bool("intersection", [after, rim]).volume
    assert abs(a - b) < 1e-12


def test_the_wedge_meets_the_skin_steeply(tmp_path):
    # the plastic wedge must not be a knife edge of its own (printed 1.0 mm gate)
    foam, cut = _foam_and_cut()
    wedges, _ = joints.sliver_wedges(foam, {"supports": cut})
    part = joints._bool("union", [cut, wedges["supports"]])
    assert _wall(part, tmp_path, "part") >= 1.0                           # the part as printed, here the cut


def test_no_pocket_no_change():
    foam = trimesh.creation.box(bounds=[[0, -20 * MM, 0], [60 * MM, 20 * MM, 20 * MM]])
    far_cut = trimesh.creation.box(bounds=[[100 * MM, -5 * MM, 0], [110 * MM, 5 * MM, 5 * MM]])
    wedges, after = joints.sliver_wedges(foam, {"supports": far_cut})
    assert wedges == {} and after is foam


def test_a_wedge_that_cannot_join_is_refused_by_name():
    part = trimesh.creation.box(bounds=[[0, 0, 0], [10 * MM, 10 * MM, 10 * MM]])
    wedge = trimesh.creation.box(bounds=[[40 * MM, 0, 0], [41 * MM, 1 * MM, 1 * MM]])
    cut = part.copy()
    body = trimesh.creation.box(bounds=[[-1, -1, -1], [1, 1, 1]])
    with pytest.raises(ValueError, match="sliver wedge of supports"):
        joints.join_wedge("supports", part, wedge, cut, body)


def _part_and_touching_wedge(t_mm=10.0):
    part = trimesh.creation.box(bounds=[[0, -10 * MM, 0], [20 * MM, 10 * MM, t_mm * MM]])
    wedge = trimesh.creation.box(bounds=[[20 * MM, -2 * MM, 0], [22 * MM, 2 * MM, t_mm * MM]])
    cut = trimesh.creation.box(bounds=[[-1 * MM, -11 * MM, -1 * MM], [20.15 * MM, 11 * MM, (t_mm + 1) * MM]])
    body = trimesh.creation.box(bounds=[[-1, -1, -1], [1, 1, 1]])
    return part, wedge, cut, body


def test_a_wedge_inside_the_support_zone_joins():
    part, wedge, cut, body = _part_and_touching_wedge()
    j = joints.join_wedge("supports", part, wedge, cut, body, axles=((10.0, 5.0, 30.0),))
    assert len(joints._solid_shells(j)) == 1


def test_a_wedge_past_the_claw_lip_is_refused_by_name():
    part, wedge, cut, body = _part_and_touching_wedge()
    # the wedge's far corner is ~12.9 mm from this axle: past R - lip = 11.5
    with pytest.raises(ValueError, match="T7.12.1 / T7.13"):
        joints.join_wedge("supports", part, wedge, cut, body, axles=((10.0, 5.0, 13.0),))


def test_a_wedge_on_a_thin_part_is_refused_by_name():
    part, wedge, cut, body = _part_and_touching_wedge(t_mm=0.6)     # a 0.6 mm plate: under 1.0
    with pytest.raises(ValueError, match="mm thick"):
        joints.join_wedge("nose", part, wedge, cut, body)
