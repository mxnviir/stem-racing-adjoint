"""
test_halo_visibility.py -- T4.4.2 / T4.4.3 halo visibility.

T4.4.2 (front and side views, 10 pts): "Visibility of the Halo must not be
physically obstructed by any other component when viewed in the front or side
views." The rule diagram boxes only the halo ABOVE a 4.0 mm base fillet, so
bodywork may blend into the bottom 4 mm.

T4.4.3 (top view, 10 pts): "The Halo must not be physically obstructed in the
plan view except by the helmet." No fillet relief -- the whole plan outline must
be clear. This model carries no helmet, so the requirement is absolute here.

Before this constraint existed the halo was modelled only as a VOID (phi > 0 so
the optimiser could not fill the mount) and nothing stopped bodywork sitting
above, ahead of or outboard of it. Measured on a carved 79 g car: 100% of halo
cells obstructed in top view, 100% in front, 64.7% in side. Both rules were
comprehensively violated and the geometry permitted it.
"""
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "sandbox"))

import numpy as np  # noqa: E402

_passed = _failed = 0


def _run(t):
    global _passed, _failed
    try:
        t()
        print("PASS " + t.__name__)
        _passed += 1
    except Exception as exc:  # noqa: BLE001
        print("FAIL %s: %s" % (t.__name__, exc))
        _failed += 1


def _obstructed(halo, solid, axis, viewer_positive):
    """Halo cells whose line of sight to the viewer passes through solid."""
    n = halo.shape[axis]
    acc = np.zeros(np.delete(np.array(halo.shape), axis), dtype=bool)
    hit = np.zeros_like(halo, dtype=bool)
    order = reversed(range(n)) if viewer_positive else range(n)
    for s in order:
        sl = [slice(None)] * 3
        sl[axis] = s
        sl = tuple(sl)
        hit[sl] = acc & halo[sl]
        acc = acc | solid[sl]
    return hit


def _carved_car(n_iters=10):
    import coarse
    coarse.use_spacing(2.0)
    import phi_updater as pu
    from unified_phi import build_unified_geometry

    geom = build_unified_geometry(120.0, 36.0, 20.0, init_mode="full",
                                  with_cargo=False)
    grads = {"dT_dD20": 0.4618, "dT_dmass": 17.042, "dT_dh_com": 0.0,
             "dT_dx_com": 0.0, "dT_dL": 0.0}

    class _MR:
        total_mass_kg, com_x_m, com_z_m = 0.1494, 0.122, 0.0296

    w = {"w_aero": 1.0, "w_mass": 1.0, "w_com": 0.0, "w_mfg": 0.0}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for _ in range(n_iters):
            pu.apply_adjoint_to_unified(
                geom, np.zeros(0), SimpleNamespace(vertices=np.zeros((0, 3))),
                0.5, w, grads, _MR())
    return geom


def test_top_view_is_completely_unobstructed():
    """T4.4.3 protects the WHOLE plan outline -- no fillet relief."""
    geom = _carved_car()
    halo = geom.fixed_hardware.halo_void_mask
    blocked = _obstructed(halo, geom.phi.grid < 0, axis=2, viewer_positive=True)
    assert blocked.sum() == 0, (
        f"{int(blocked.sum()):,} of {int(halo.sum()):,} halo cells are "
        f"obstructed from above. T4.4.3 allows obstruction only by the helmet, "
        f"which this model does not carry.")


def test_front_and_side_are_unobstructed_above_the_fillet():
    """T4.4.2, as the team builds it (user 2026-11-23): nothing in front of or beside the halo above the
    pocket's rim, up to the halo's top (halo_seat.view_air). The halo mask is the halo's seat and the air
    over its plan outline (up to the grid's top), so the protected cells are those from the rim to the
    halo's top."""
    import geometry_contract as gc
    import halo_seat as hs

    geom = _carved_car()
    halo = geom.fixed_hardware.halo_void_mask
    solid = geom.phi.grid < 0
    zs = (geom.region.origin_m[2] + np.arange(halo.shape[2]) * gc.GRID_SPACING_M) * 1e3
    top = hs.outlines()["top"]
    protected = halo & ((zs >= hs.RIM_Z_MM) & (zs <= top))[None, None, :]
    assert protected.any(), "no halo above the rim"

    front = _obstructed(halo, solid, axis=0, viewer_positive=False)
    side = _obstructed(halo, solid, axis=1, viewer_positive=True)
    bad = int(((front | side) & protected).sum())
    assert bad == 0, (
        f"{bad:,} halo cells above the pocket's rim are obstructed in the front or side view (T4.4.2).")


def test_the_fillet_exemption_is_actually_used():
    """The bottom band must stay available to bodywork.

    If the constraint were applied to the FULL halo in front/side view -- the
    obvious over-strict reading -- it would forbid any blend into the halo base
    and cut away material the rule explicitly permits. This checks the
    exemption is real rather than decorative, so an over-tightening shows up.
    """
    import geometry_contract as gc
    from fixed_hardware import halo_visibility_air_mask, HALO_VISIBILITY_FILLET_MM

    geom = _carved_car(n_iters=0)
    halo = geom.fixed_hardware.halo_void_mask
    mask = halo_visibility_air_mask(halo, z_origin_m=geom.region.origin_m[2],
                                    dz_m=gc.GRID_SPACING_M)

    ks = np.flatnonzero(halo.any(axis=(0, 1)))
    dz_mm = gc.GRID_SPACING_M * 1000.0
    k_cut = ks[0] + int(np.ceil(HALO_VISIBILITY_FILLET_MM / dz_mm))

    # Directly beside the halo base, below the cut, must NOT be forced air by
    # the front/side rule. Above the cut it must be.
    ii, jj, _ = np.where(halo)
    x0, y0 = int(ii.min()), int(jj.min())
    below = mask[x0, max(y0 - 1, 0), ks[0]]
    assert not below, (
        "a cell beside the halo BASE is forced to air; T4.4.2 exempts the "
        "bottom 4 mm and this over-tightens the rule")


def test_the_constraint_binds_during_the_descent_not_after():
    """It has to be hard AIR, not a post-hoc audit.

    A rule checked only at the end lets the optimiser spend its whole budget
    building something illegal. Forcing the shadow cells into hard_mask_air
    means no candidate can ever fill them.
    """
    geom = _carved_car(n_iters=0)
    halo = geom.fixed_hardware.halo_void_mask
    ks = np.flatnonzero(halo.any(axis=(0, 1)))
    ii, jj, _ = np.where(halo)
    # A cell directly above the halo must be in the hard air mask.
    above = (int(ii.min()) + 1, int(jj.min()) + 1, int(ks[-1]) + 1)
    if above[2] < halo.shape[2]:
        assert geom.phi.hard_mask_air[above], (
            "the cell directly above the halo is not hard air, so the "
            "optimiser is free to fill it and hide the halo from the top view")




def test_the_halo_lofts_to_the_canister():
    """The body joins ALL of the halo's rear face to the cartridge (user 2026-11-23: "make sure that the
    loft connects 100% of the halo face to the canister"): the required solid covers the face's outline in
    the first cells behind the halo, arrives at the T5.5 safety zone's circle at the chamber's front, and is
    in the carved body."""
    import geometry_contract as gc
    import halo_seat as hs
    from fixed_hardware import halo_canister_loft_solid_mask, CANISTER_CLEARANCE_RADIUS_MM

    geom = _carved_car(n_iters=0)
    fh = geom.fixed_hardware
    cyl = getattr(fh, "canister_cylinder", None)
    assert cyl is not None, "no canister bore geometry to loft to"
    r = geom.region
    d = gc.GRID_SPACING_M
    loft = halo_canister_loft_solid_mask(fh.halo_void_mask, cyl, x_origin_m=r.origin_m[0],
                                         y_origin_m=r.origin_m[1], z_origin_m=r.origin_m[2], d_m=d)
    assert loft.any(), "no loft was built at all"
    xs, ys, zs = ((r.origin_m[k] + np.arange(r.shape[k]) * d) * 1e3 for k in range(3))
    i0 = int(np.flatnonzero(loft.any(axis=(1, 2)))[0])
    # every cell centre of the halo's rear face (looking forward), in the loft's first section
    import shapely
    face = hs.outlines()["rear"]
    Y, Z = np.meshgrid(ys, zs, indexing="ij")
    on = shapely.contains_xy(face, Y.ravel(), Z.ravel()).reshape(Y.shape)
    miss = int((on & ~loft[i0]).sum())
    assert on.any() and miss == 0, f"{miss} of {int(on.sum())} cells of the halo's face have no loft behind them"
    # it arrives at the cartridge's safety zone: its circle at the chamber's front
    xc = (cyl.x_center_m - cyl.x_half_width_m) * 1e3
    i1 = int(np.argmin(np.abs(xs - xc))) - 1
    circ = np.hypot(Y, Z - cyl.z_center_m * 1e3) <= CANISTER_CLEARANCE_RADIUS_MM - 1.5 * d * 1e3
    assert (circ & ~loft[i1]).sum() == 0, "the loft does not arrive at the cartridge's safety zone"
    # required, so in the body
    lost = int((loft & ~(geom.phi.grid < 0)).sum())
    assert lost <= 0.01 * loft.sum(), f"{lost} of {int(loft.sum())} loft cells are not body"


def test_the_loft_ceiling_and_deck_agree():
    """No ceiling over the loft any more (the search shapes the top); the required loft must not be forced
    air anywhere either (hard_solid &= ~hard_air would cut holes in it)."""
    import geometry_contract as gc
    from fixed_hardware import halo_canister_loft_solid_mask

    geom = _carved_car(n_iters=0)
    fh = geom.fixed_hardware
    kw = dict(x_origin_m=geom.region.origin_m[0], y_origin_m=geom.region.origin_m[1],
              z_origin_m=geom.region.origin_m[2], d_m=gc.GRID_SPACING_M)
    deck = halo_canister_loft_solid_mask(fh.halo_void_mask, fh.canister_cylinder, **kw)
    overlap = int((geom.phi.hard_mask_air & deck).sum())
    assert overlap == 0, f"{overlap:,} loft cells are forced air"
