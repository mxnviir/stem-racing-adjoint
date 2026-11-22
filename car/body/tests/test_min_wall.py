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


def test_carve_leaves_no_new_thin_wall():
    """Hard thinning through carve.carve (2 mm grid): no wall under 3.0 mm that the start
    block did not already have."""
    import carve
    import cutter
    from phi_updater import thin_wall_mask
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    g0 = cutter.start_block(lay, spacing_mm=2.0)
    GRID_SPACING_M = up_spacing()          # after the build: conftest resets the module value to 0.3 mm
    t0 = thin_wall_mask(g0.phi.grid, GRID_SPACING_M, 3.0e-3)
    g, reps = carve.carve(lay, [{"bias_mm": -2.5, "trust_mm": 2.0}] * 4, spacing_mm=2.0)
    assert not (thin_wall_mask(g.phi.grid, GRID_SPACING_M, 3.0e-3) & ~t0).any()
    assert all(r["status"] == "ok" for r in reps), reps          # a thinning cut must move, not be refused


def test_finished_body_reports_and_gates_its_wall(tmp_path):
    """cutter.finish measures the sized, milled body's thinnest wall and refuses it under
    3.0 mm; sizing never searched a skin below the wall-legal one."""
    import carve
    import cutter
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    g, _ = carve.carve(lay, [{"bias_mm": -1.5, "trust_mm": 2.0}], spacing_mm=2.0)
    res = cutter.finish(g, lay, target_body_g=50.0, out_dir=tmp_path)
    w = res["min_machined_wall_mm"]
    assert w is not None
    assert (res["status"] != "ok") or w >= 3.0, res
    if res["status"] == "refused" and res["reason"].startswith("min_wall"):
        assert w < 3.0
    # cut.json leaves sizing_tried out by design; the same sizing, rebuilt with finish's own call
    # (deterministic), gives the skins it tried: none below the floor it reports.
    import param_body as pb
    body = pb.build(lay["W"], lay["x_front"], lay["d_halo"], pb.BodyParams(),
                    target_body_kg=50.0e-3, field_mm=g.phi.grid * 1e3)
    tried = body.build_report["sizing_tried"]
    assert body.build_report["skin_lo_mm"] == res["report"]["skin_lo_mm"]
    assert min(t[0] for t in tried) >= body.build_report["skin_lo_mm"] - 1e-9


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


@pytest.mark.parametrize("amp", [1.0, -1.0])
def test_a_1mm_bump_on_the_start_block_moves_it_and_keeps_every_wall(amp):
    """A +-1 mm bump (sigma 10 mm, speed in mm, trust 1 mm) on the side of the start block,
    once thinned 2 mm (the block fills the envelope, so it cannot grow, and its top over the
    halo is a rule face), moves the surface there by about 1 mm the right way, leaves it
    alone 40 mm away, and makes no wall thinner than 3.0 mm that was not already that thin."""
    import carve
    import cutter
    from phi_updater import _thinned
    from unified_phi import extract_half_surface
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    thin2 = {"bias_mm": -2.0, "unit": False, "trust_mm": 2.0}
    g0, r0 = carve.carve(lay, [thin2], spacing_mm=2.0)
    GRID_SPACING_M = up_spacing()          # after the build: conftest resets the module value to 0.3 mm
    assert r0[0]["status"] == "ok", r0
    V = np.asarray(extract_half_surface(g0).vertices) * 1e3
    mx, mz = 0.5 * (V[:, 0].min() + V[:, 0].max()), 0.5 * (V[:, 2].min() + V[:, 2].max())
    side = V[(np.abs(V[:, 0] - mx) < 10) & (np.abs(V[:, 2] - mz) < 5)]
    c = side[side[:, 1].argmax()]
    g, reps = carve.carve(lay, [thin2, {"bumps": [{"c_mm": c.tolist(), "amp_mm": amp, "sigma_mm": 10.0}],
                                        "unit": False, "trust_mm": 1.0}], spacing_mm=2.0)
    assert reps[1]["status"] == "ok", reps
    d = (g.phi.grid - g0.phi.grid) * 1e3                 # mm; growing lowers phi
    ijk = lambda p: tuple(np.clip(np.rint((p * 1e-3 - np.asarray(g0.region.origin_m)) / GRID_SPACING_M).astype(int),  # noqa: E731
                                  0, np.array(d.shape) - 1))
    moved = -d[ijk(c)]
    assert 0.5 <= moved * np.sign(amp) <= 1.5, f"moved {moved:+.2f} mm at the bump for amp {amp:+.1f}"
    far = c + np.array([-40.0, 0.0, 0.0])
    assert abs(d[ijk(far)]) < 0.25, f"{d[ijk(far)]:+.2f} mm 40 mm away"
    bad = _thinned(g0.phi.grid, g.phi.grid, GRID_SPACING_M, 3.0e-3)
    assert not bad.any(), _thinned_rows(g0, g, bad)


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


def test_finish_own_scope_sizes_the_block_and_thins_no_wall(tmp_path, monkeypatch):
    """WALL_SCOPE "own": the 2 mm start block sizes to 40 g (the whole block is under 48.2 g at 2 mm, test_cutter) (it was mass_unreachable
    5.14 g with the old floor) and sizing thins no wall under 3.0 mm."""
    import carve
    import cutter
    import param_body
    monkeypatch.setattr(param_body, "WALL_SCOPE", "own")
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    g, _ = carve.carve(lay, [{"bias_mm": -1.0, "trust_mm": 1.0}], spacing_mm=2.0)
    res = cutter.finish(g, lay, target_body_g=40.0, out_dir=tmp_path)
    assert res["status"] == "ok", res.get("reason")
    assert res["report"]["walls_thinned_under_min"] == 0


def test_own_scope_sizing_leaves_every_designed_thin_wall_as_given(monkeypatch):
    """WALL_SCOPE "own": the -1 mm cut start block sizes to its target, no wall is thinned
    under 3.0 mm, and every wall the carved field already had under 3.0 mm is no thinner
    (the skin and the shave hold off within one wall width of it)."""
    import carve
    import param_body
    from phi_updater import _thinned, thin_wall_mask
    monkeypatch.setattr(param_body, "WALL_SCOPE", "own")
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    g, _ = carve.carve(lay, [{"bias_mm": -1.0, "trust_mm": 1.0}], spacing_mm=2.0)
    GRID_SPACING_M = up_spacing()          # after the build: conftest resets the module value to 0.3 mm
    f0 = g.phi.grid.astype(np.float64)
    designed = thin_wall_mask(f0, GRID_SPACING_M, 3.0e-3)
    body = param_body.build(lay["W"], lay["x_front"], lay["d_halo"], param_body.BodyParams(),
                            target_body_kg=0.040, field_mm=f0 * 1e3)
    br = body.build_report
    assert abs(br["mass_error_g"]) <= 0.05 and not br.get("mass_unreachable"), br.get("mass_error_g")
    assert br["walls_thinned_under_min"] == 0
    thinned = _thinned(f0, body.phi.grid, GRID_SPACING_M, 3.0e-3)
    assert not (thinned & designed).any(), "a designed thin wall got thinner"


@pytest.mark.parametrize("sp", [2.0, 1.0])
def test_own_start_block_has_no_free_wall_under_3(sp, monkeypatch):
    """WALL_SCOPE "own": the start block loses only its unforced slivers. (a) every rule zone
    still holds; (b) no unforced wall under 3.0 mm is left; (c) the mass drops by about the
    removed volume, printed; (d) the deck-ceiling ledge at x ~152, |y| ~14, z 34-44 is gone."""
    import cutter
    import param_body
    import unified_phi as up
    from phi_updater import thin_wall_mask
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    monkeypatch.setattr(param_body, "WALL_SCOPE", "all")
    m_all = sum(c.mass_kg for c in up.compute_mass_com(cutter.start_block(lay, spacing_mm=sp)))
    monkeypatch.setattr(param_body, "WALL_SCOPE", "own")
    g = cutter.start_block(lay, spacing_mm=sp)
    d = up.GRID_SPACING_M
    solid = g.phi.grid < 0
    assert not (solid & g.phi.hard_mask_air).any() and not (~solid & g.phi.hard_mask_solid).any()   # (a)
    thin = thin_wall_mask(g.phi.grid, d, 3.0e-3)
    assert not (thin & ~g.phi.hard_mask_solid).any(), g.start_clean                               # (b)
    drop_g = (m_all - sum(c.mass_kg for c in up.compute_mass_com(g))) * 1e3
    print(f"start clean {sp} mm: {g.start_clean}, mass drop {drop_g:.3f} g")
    assert 0.0 <= drop_g < 2.0, (drop_g, g.start_clean)                                            # (c)
    X, Y, Z = (np.asarray(g.region.origin_m)[k] * 1e3 + np.arange(g.phi.grid.shape[k]) * sp for k in range(3))
    box = np.ix_((X > 145) & (X < 162), (np.abs(Y) > 11) & (np.abs(Y) < 17), (Z > 33) & (Z < 45))
    assert not thin[box].any(), "the deck-ceiling ledge is still there"                            # (d)


def test_roof_over_the_halo_shadow_keeps_3mm_at_1mm():
    """The roof over the halo's front-shadow rule air (x < 73.7, |y| <= 12.5, air z 28-45 mm)
    is the wall a shrink thins (Jdiejei 43910468954). On the 1 mm grid the loop uses (run_car
    --cfd-mm default 1.0), a -1 mm shrink with the switches on leaves it at 3.0 mm or more, and
    the cut still moves."""
    import carve
    import param_body
    import phi_updater
    from geometry_contract import GRID_SPACING_M  # noqa: F401  (set by carve's start_block)
    import unified_phi as up
    from phi_updater import thin_wall_mask
    assert phi_updater.WALL_GUARD == "freeze" and param_body.WALL_SCOPE == "own"
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    g, reps = carve.carve(lay, [{"bias_mm": -1.0, "trust_mm": 1.0}], spacing_mm=1.0)
    assert reps[0]["status"] == "ok" and reps[0]["substeps"] > 0, reps
    d = up.GRID_SPACING_M
    X, Y, Z = (np.asarray(g.region.origin_m)[k] * 1e3 + np.arange(g.phi.grid.shape[k]) * d * 1e3 for k in range(3))
    box = np.ix_((X > 30) & (X < 73), np.abs(Y) <= 12.5, Z > 44)
    thin = thin_wall_mask(g.phi.grid, d, 3.0e-3) & ~g.phi.hard_mask_solid
    assert not thin[box].any(), "the roof over the halo shadow went under 3.0 mm"


def test_shrink_at_2mm_moves_with_the_roof_held():
    """2:1 of the wall lab (dT_dn +1 everywhere, 2 mm block): the cut is ok and moves
    (substeps > 0); freeze holds the halo-shadow roof as one wall, not edge by edge."""
    import cutter
    from phi_updater import _thinned
    from types import SimpleNamespace
    from unified_phi import extract_half_surface
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    g0 = cutter.start_block(lay, spacing_mm=2.0)
    GRID_SPACING_M = up_spacing()          # after the build: conftest resets the module value to 0.3 mm
    mesh = SimpleNamespace(vertices=np.asarray(extract_half_surface(g0).vertices))
    g, rep = cutter.cut(g0, np.ones(len(mesh.vertices)), mesh, step_m=1.0)
    assert rep["status"] == "ok" and rep["substeps"] > 0, rep
    assert (g.phi.grid < 0).sum() < (g0.phi.grid < 0).sum()
    assert not _thinned(g0.phi.grid, g.phi.grid, GRID_SPACING_M, 3.0e-3).any()


def _tunnel_case():
    import carve
    import param_body as pb
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    g, _ = carve.carve(lay, [{"bias_mm": -1.0, "trust_mm": 1.0}], spacing_mm=2.0)
    f = g.phi.grid * 1e3
    run = lambda bp, **k: pb.build(lay["W"], lay["x_front"], lay["d_halo"], bp, field_mm=f, **k)  # noqa: E731
    tun = lambda h, w=6.0: pb.BodyParams(ft_h=h, ft_w=w, ft_x0=60.0, ft_x1=160.0, ft_ramp=20.0)  # noqa: E731
    return run, tun


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


def test_carved_tunnel_off_is_byte_identical():
    """ft_h = 0 with the other ft_* set builds the same field and the same half-body STL as
    the default params, so stored cars keep their ids and results."""
    run, tun = _tunnel_case()
    import param_body as pb
    a, b = run(pb.BodyParams(), skin_offset_mm=0.0), run(tun(0.0), skin_offset_mm=0.0)
    assert np.array_equal(a.phi.grid, b.phi.grid)
    assert _stl_hash(a) == _stl_hash(b)


def test_carved_tunnel_depth_and_slope():
    """On a carved car (before 2026-11-17 build() dropped the tunnel, so Part 3's five floor
    variables did nothing): at fixed skins 0 and +1 mm the floor at x 110, y 0 is ft_h = 4
    above the floor at y 12, within one 2 mm cell; the built mass falls as ft_h grows."""
    run, tun = _tunnel_case()
    for skin in (0.0, 1.0):
        t = run(tun(4.0), skin_offset_mm=skin)
        depth = _floor(t, 110.0, 0.0) - _floor(t, 110.0, 12.0)
        assert abs(depth - 4.0) <= up_spacing() * 1e3, f"tunnel {depth:.1f} mm deep at skin {skin}"
    m = [_mass_g(run(tun(h), skin_offset_mm=0.0)) for h in (0.0, 4.0, 8.0)]
    print(f"mass at ft_h 0/4/8: {m}")
    assert m[0] > m[1] > m[2], m


def test_carved_tunnel_narrower_than_the_tool_is_not_cut():
    """A slot under 2 * TOOL_R (ft_w 3.1, 6.2 mm < 6.35) is not cut: the body is the
    tunnel-less one."""
    run, tun = _tunnel_case()
    import machining
    assert 2 * 3.1 < 2 * machining.TOOL_R_MM
    assert np.array_equal(run(tun(4.0, w=3.1), skin_offset_mm=0.0).phi.grid,
                          run(tun(0.0), skin_offset_mm=0.0).phi.grid)


def test_carved_tunnel_at_the_narrowest_window_width_survives_milling():
    """ft_w 3.2 (pattern.FLOOR low edge, a 6.4 mm slot, just over 2 * TOOL_R 6.35): after
    make_machinable the tunnel is still there at x 110, y 0. If not, the low edge is dead."""
    run, tun = _tunnel_case()
    t = run(tun(4.0, w=3.2), skin_offset_mm=0.0)
    depth = _floor(t, 110.0, 0.0) - _floor(t, 110.0, 12.0)
    print(f"ft_w 3.2: depth {depth:.1f} mm")
    assert depth > 0.0, depth


@pytest.mark.parametrize("h,w", [(5.0, 6.0), (10.0, 14.0)])   # middle and the window max (pattern.FLOOR)
def test_carved_tunnel_sizes_to_target(h, w):
    """Sized to 40 g with the tunnel: error <= 0.05 g, no wall thinned under 3.0 mm, the
    tunnel ft_h deep within one 2 mm cell, and no wall under 3.0 mm in the tunnel's region
    that the carved field did not already have. The start block is wider beside the cargo
    (|y| to 32 mm) than ahead of it (20 mm), so the region crosses that side lobe; a carved
    sidepod narrower than the fuselage under it is a known untested case."""
    from phi_updater import thin_wall_mask
    run, tun = _tunnel_case()
    s = run(tun(h, w), target_body_kg=0.040)
    br = s.build_report
    print(f"ft_h {h} ft_w {w}: error {br.get('mass_error_g')} g, skin {br.get('skin_offset_mm')}")
    assert abs(br["mass_error_g"]) <= 0.05 and not br.get("mass_unreachable"), br.get("mass_error_g")
    assert br["walls_thinned_under_min"] == 0
    depth = _floor(s, 110.0, 0.0) - _floor(s, 110.0, 12.0 + w)
    assert abs(depth - h) <= up_spacing() * 1e3, depth
    d = up_spacing()
    base = run(tun(0.0), target_body_kg=0.040)
    o = np.asarray(s.region.origin_m) * 1e3
    X, Y = (o[k] + np.arange(s.phi.grid.shape[k]) * d * 1e3 for k in range(2))
    box = np.ix_((X >= 60) & (X <= 160), np.abs(Y) <= w + 10, np.ones(s.phi.grid.shape[2], bool))
    new = thin_wall_mask(s.phi.grid, d, 3.0e-3) & ~thin_wall_mask(base.phi.grid, d, 3.0e-3) & ~s.phi.hard_mask_solid
    assert not new[box].any(), int(new[box].sum())


def test_carve_reports_whether_a_cut_moved():
    """An ok cut says whether anything moved: a -1 mm thin of the block flips cells and loses
    volume (moved True); a bump whose speed is ~1e-8 mm everywhere (centre 60 mm off the
    car's top, sigma 10) flips nothing and says moved False (ok, or refused as no_motion)."""
    import carve
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    _, r = carve.carve(lay, [{"bias_mm": -1.0, "trust_mm": 1.0}], spacing_mm=2.0)
    assert r[0]["status"] == "ok" and r[0]["moved"] and r[0]["cells_flipped"] > 0 and r[0]["dvol_mm3"] < 0, r
    _, r = carve.carve(lay, [{"bumps": [{"c_mm": [110.0, 0.0, 110.0], "amp_mm": 1.0, "sigma_mm": 10.0}],
                              "unit": False}], spacing_mm=2.0)
    assert (r[0]["status"] == "ok" or r[0]["reason"] == "no_motion") and not r[0]["moved"] and r[0]["cells_flipped"] == 0, r


@pytest.mark.parametrize("amp", [1.0, -1.0])
def test_a_1mm_bump_under_the_floor_moves_up_only(amp):
    """Part 3 mode 9 (under the floor, x ~146, y ~5): a +-1 mm bump (sigma 10, unit False) moved
    9e-7 m, because the adjoint despike clips (p99.9 per vertex, 3 x p90 over the band) cut a
    local designed speed to 3 x its value 40 mm away. carve's edits now skip them. The underside
    sits on the grid's bottom layer, the forced-air border seal (track clearance), so the mode is
    one-sided by rule: +1 (grow down) is ok and reports moved False; -1 thins, flips cells and
    moves the surface 0.5-1.5 mm at most."""
    import carve
    import cutter
    from unified_phi import extract_half_surface
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    g0 = cutter.start_block(lay, spacing_mm=2.0)
    V = np.asarray(extract_half_surface(g0).vertices) * 1e3
    near = V[(np.abs(V[:, 0] - 146.0) < 4) & (np.abs(V[:, 1] - 5.0) < 4)]
    c = near[near[:, 2].argmin()]                       # the underside vertex there
    g, r = carve.carve(lay, [{"bumps": [{"c_mm": c.tolist(), "amp_mm": amp, "sigma_mm": 10.0}], "unit": False}],
                       spacing_mm=2.0)
    iface = np.abs(g0.phi.grid) < up_spacing()
    mx = float(np.abs(g.phi.grid - g0.phi.grid)[iface].max()) * 1e3
    print(f"floor bump {amp:+}: largest surface move {mx:.2f} mm, report {r[0]}")
    assert r[0]["status"] == "ok", r
    if amp > 0:
        assert not r[0]["moved"] and r[0]["cells_flipped"] == 0, r
    else:
        assert r[0]["moved"] and r[0]["dvol_mm3"] < 0, r
        assert 0.5 <= mx <= 1.5, mx


def test_bias_moves_the_free_surface_by_its_trust():
    """A -1 mm bias (trust 1) at 1 mm moves the free surface 0.5-1.5 mm: the median phi change
    over the start's interface cells that no rule zone holds. (Cells flipped / half-surface area
    is not this: the grid holds both halves, so it reads twice the move, and the y = 0 cap and the
    rule-held faces are in the area.)"""
    import carve
    import cutter
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    g0 = cutter.start_block(lay, spacing_mm=1.0)
    g, r = carve.carve(lay, [{"bias_mm": -1.0, "trust_mm": 1.0}], spacing_mm=1.0)
    d = up_spacing()
    free = (np.abs(g0.phi.grid) < d) & ~g0.phi.hard_mask_air & ~g0.phi.hard_mask_solid
    dphi = (np.asarray(g.phi.grid, float) - np.asarray(g0.phi.grid, float))[free] * 1e3
    print(f"bias -1 at 1 mm: free interface cells {int(free.sum())}, dphi median {np.median(dphi):.3f} "
          f"p10 {np.percentile(dphi, 10):.3f} p90 {np.percentile(dphi, 90):.3f} mm, report {r[0]}")
    assert r[0]["status"] == "ok", r
    assert 0.5 <= float(np.median(dphi)) <= 1.5
