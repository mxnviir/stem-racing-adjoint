"""The 3.0 mm machined wall (team limit, 2026-11-14): thin_wall_mask finds a 2.9 mm wall
wherever it sits on the grid, passes a 3.0 mm one, does not call a convex edge a wall, and a
carve never leaves a new wall under 3.0 mm."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest

D = 1e-3                                   # 1 mm cells, metres


def up_spacing():
    """The spacing start_block set; read it after the build (conftest resets the module value to 0.3 mm)."""
    import unified_phi
    return unified_phi.GRID_SPACING_M


def _thinned_rows(g0, g, bad, n=20):
    """Up to n thinned cells: x, y, z mm and the wall before -> after, mm."""
    from phi_updater import _wall_half
    d = up_spacing()
    o = np.asarray(g0.region.origin_m) * 1e3
    h0, h1 = _wall_half(g0.phi.grid, d) * 2e3, _wall_half(g.phi.grid, d) * 2e3
    return [(*(o + np.array(c) * d * 1e3).round(1).tolist(), round(float(h0[tuple(c)]), 2), round(float(h1[tuple(c)]), 2))
            for c in np.argwhere(bad)[:n]] + [f"{int(bad.sum())} cells"]

def _slab(t_mm, z0_mm):
    z = (np.arange(24) + 0.5) * D
    c = (z0_mm + t_mm / 2.0) * 1e-3
    phi = np.abs(z - c) - t_mm * 1e-3 / 2.0
    return np.broadcast_to(phi, (8, 8, 24)).copy()


@pytest.mark.parametrize("z0", [5.0, 5.25, 5.5, 5.75])
def test_wall_29_fails_30_passes(z0):
    from phi_updater import thin_wall_mask
    assert thin_wall_mask(_slab(2.9, z0), D, 3.0e-3).any()
    assert not thin_wall_mask(_slab(3.0, z0), D, 3.0e-3).any()
    assert not thin_wall_mask(_slab(6.0, z0), D, 3.0e-3).any()


def test_oblique_wall():
    """A 2.9 mm wall at 30 deg to the grid is still found; a 3.2 mm one is not."""
    from phi_updater import thin_wall_mask
    X, Y, Z = np.meshgrid(*[(np.arange(30) + 0.5) * D] * 3, indexing="ij")
    nrm = np.array([0.0, np.sin(np.radians(30)), np.cos(np.radians(30))])
    s = X * nrm[0] + Y * nrm[1] + Z * nrm[2] - 15e-3
    for t, want in ((2.9, True), (3.2, False)):
        assert thin_wall_mask(np.abs(s) - t * 1e-3 / 2, D, 3.0e-3).any() == want


def test_convex_edge_is_not_a_wall():
    from phi_updater import thin_wall_mask
    X, Y, Z = np.meshgrid(*[(np.arange(20) + 0.5) * D] * 3, indexing="ij")
    phi = np.maximum(Y - 10e-3, Z - 10e-3)              # solid where y < 10 and z < 10 mm
    out = np.hypot(np.maximum(Y - 10e-3, 0), np.maximum(Z - 10e-3, 0))
    phi = np.where(phi > 0, out, phi)
    assert not thin_wall_mask(phi, D, 3.0e-3).any()




@pytest.mark.parametrize("mode", ["compare", "freeze"])
def test_guard_a_ridge_that_moved_is_not_a_new_wall(mode):
    """A 2.9 mm wall that was already there and only slid 0.6 mm (its ridge moves a cell)
    is not a new thin wall: the old index check refused every cut on the start block."""
    from phi_updater import wall_guard
    a, b = _slab(2.9, 5.0), _slab(2.9, 5.6)
    g, ok = wall_guard(a, b, D, 3.0e-3, mode=mode)
    assert ok and np.array_equal(g, b)


@pytest.mark.parametrize("mode", ["compare", "freeze"])
def test_guard_stops_a_wall_going_under_3(mode):
    from phi_updater import thin_wall_mask, wall_guard
    a, b = _slab(3.4, 8.0), _slab(2.6, 8.4)              # both faces move in: 3.4 -> 2.6 mm
    g, ok = wall_guard(a, b, D, 3.0e-3, mode=mode)
    assert not thin_wall_mask(g, D, 3.0e-3).any()
    assert ok == (mode == "freeze") and (ok or np.array_equal(g, a))


def test_freeze_keeps_the_move_away_from_the_wall():
    """Freeze undoes the sub-step only around the wall: a face 15 mm away keeps its move."""
    from phi_updater import thin_wall_mask, wall_guard
    z = (np.arange(40) + 0.5) * D
    thin = np.abs(z - 6.7e-3) - 1.7e-3                                  # 3.4 mm wall at 5.0-8.4 mm
    a = np.broadcast_to(np.minimum(thin, 20e-3 - z), (8, 8, 40)).copy()   # + a block from z 20 mm up
    b = a.copy()
    b[..., :12] = np.broadcast_to(np.abs(z[:12] - 6.7e-3) - 1.3e-3, (8, 8, 12))   # wall -> 2.6 mm
    b[..., 14:] -= 0.8e-3                                               # its face grows 0.8 mm
    g, ok = wall_guard(a, b, D, 3.0e-3, mode="freeze")
    assert ok and not thin_wall_mask(g, D, 3.0e-3).any()
    assert np.array_equal(g[..., 14:], b[..., 14:]), "the far move was undone too"




def _box(X, Z, x0, x1, z0, z1):
    return np.maximum.reduce([x0 - X, X - x1, z0 - Z, Z - z1])


def test_freeze_beside_a_thin_bridge_leaves_one_piece_and_a_distance_field():
    """Two blocks joined by a 3.4 mm bridge; the sub-step thins the bridge to 2.6 mm and
    grows the blocks' tops 0.8 mm. Freeze keeps the bridge (one piece, no wall under 3.0),
    and after the loop's reinitialisation |grad phi| is ~1 near the surface, seam included."""
    import coarse
    coarse.use_spacing(1.0)
    from bounding_volumes import BoundingRegion
    from phi_grid import PhiGrid
    from phi_updater import _thinned, reinitialise_sdf, wall_guard
    from scipy.ndimage import label
    X, _, Z = np.meshgrid(*[(np.arange(n) + 0.5) * D for n in (40, 6, 40)], indexing="ij")
    blocks = np.minimum(_box(X, Z, 0, 10e-3, 5e-3, 25e-3), _box(X, Z, 30e-3, 40e-3, 5e-3, 25e-3))
    a = np.minimum(blocks, _box(X, Z, 10e-3, 30e-3, 8e-3, 11.4e-3)).astype(np.float32)
    grown = np.minimum(_box(X, Z, 0, 10e-3, 5e-3, 25.8e-3), _box(X, Z, 30e-3, 40e-3, 5e-3, 25.8e-3))
    b = np.minimum(grown, _box(X, Z, 10e-3, 30e-3, 8.4e-3, 11.0e-3)).astype(np.float32)
    g, ok = wall_guard(a, b, D, 3.0e-3, mode="freeze")
    assert ok and g is not b
    assert label(g < 0)[1] == 1, "the frozen patch cut a piece loose"
    assert not _thinned(a, g, D, 3.0e-3).any()
    assert (g[:, :, 25] < 0).sum() > (a[:, :, 25] < 0).sum(), "the far growth was undone too"
    z = np.zeros(g.shape, bool)
    phi = PhiGrid("main_body", BoundingRegion("main_body", (0.0, 0.0, 0.0), g.shape), g.copy(), z, z.copy())
    reinitialise_sdf(phi)
    gm = np.linalg.norm(np.stack(np.gradient(phi.grid.astype(np.float64), D)), axis=0)
    band = (np.abs(phi.grid) < 2 * D)[1:-1, 1:-1, 1:-1]
    gm = gm[1:-1, 1:-1, 1:-1][band]
    assert 0.9 < np.median(gm) < 1.1 and np.percentile(gm, 95) < 1.3, (np.median(gm), np.percentile(gm, 95))
    assert label(phi.grid < 0)[1] == 1


def test_wall_floor_beyond_a_designed_thin_wall():
    """min_wall_mm_beyond leaves out a wall already under 3.0 mm: a 2.0 mm and a 5.0 mm wall
    read 5.0 (the old floor read 2.0, so the skin could not thin at all)."""
    from phi_updater import min_wall_mm, min_wall_mm_beyond
    z = (np.arange(40) + 0.5) * D
    phi = np.minimum(np.abs(z - 6e-3) - 1.0e-3, np.abs(z - 25e-3) - 2.5e-3)
    phi = np.broadcast_to(phi, (8, 8, 40)).copy()
    assert abs(min_wall_mm(phi, D) - 2.0) < 0.05
    assert abs(min_wall_mm_beyond(phi, D, 3.0e-3) - 5.0) < 0.05














def _stl_hash(body):
    import hashlib
    from unified_phi import extract_half_surface
    m = extract_half_surface(body)
    return hashlib.sha256(np.ascontiguousarray(m.vertices).tobytes() + np.ascontiguousarray(m.faces).tobytes()).hexdigest()


def _floor(body, x, y):
    d = up_spacing() * 1e3
    o = np.asarray(body.region.origin_m) * 1e3
    col = body.phi.grid[int(round((x - o[0]) / d)), int(round((y - o[1]) / d))] < 0
    return o[2] + np.flatnonzero(col)[0] * d


def _mass_g(body):
    import unified_phi as up
    return sum(c.mass_kg for c in up.compute_mass_com(body)) * 1e3
















