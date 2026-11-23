"""
run_car.py -- one whole car: build it and judge it.

    python car/build/run_car.py --out <dir> [--W 138 --x-front 55.4 --d-halo 23.2 --rear-mm 63.75 ...]

  1. BODY      car/body: the lofted body (param_body), the rule masks (cargo, halo pocket, ballast
               container, chamber wall, wheel keep-clear zones), milled top and bottom with the
               3.175 mm ball, 3 mm walls; a fixed skin (--skin-mm) or sized to 48.2 g.
  2. PARTS     car/parts: wheels, halo, nose cone, front and rear wings, tether guides, supports
               (or none: --no-supports); glue joints and manufacturing files unless --no-joints.
  3. LEGAL     car/build/legality.py: the scrutineer's checks on the assembled car.
  4. REPORT    report.md + summary.json (mass, COM, every check with its margin).

The searches (search/layout, search/shape) call this per car with --support engine --no-joints and a
fixed skin, then time the car on SimScale themselves (cfd/). Every stage writes its artefacts to
--out; the run never hides a failure.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import paths  # noqa: F401

PARTS = paths.PARTS
MAX_BODY_FACES = 400_000


def _peak_gb() -> str:
    try:
        import resource
        return f" [peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6:.1f} GB]"
    except ImportError:         # Windows
        return ""


def log(msg: str) -> None:
    print(f"[run_car {time.strftime('%H:%M:%S')}] {msg}{_peak_gb()}", flush=True)


# --------------------------------------------------------------------------- body
def _freeform(a):
    """The searches' free-form body and nose (car/body/freeform.py), or None."""
    if not getattr(a, "freeform_json", None):
        return None
    import freeform as fr
    src = a.freeform_json
    d = json.loads(Path(src).read_text()) if not src.lstrip().startswith("{") else json.loads(src)
    return fr.Freeform.from_dict(d)


def build_body(a, out: Path):
    """The parametric body (Part 1 param_body): drawn, made machinable, and
    sized by a skin offset (or at a fixed skin with --skin-mm)."""
    from coarse import use_spacing
    import param_body as pb
    use_spacing(a.cfd_mm)
    bp = pb.BodyParams.from_dict(json.loads(a.body_json))
    g = pb.build(a.W, a.x_front, a.d_halo, bp,
                 target_body_kg=getattr(a, "_body_target_kg", None),
                 skin_offset_mm=getattr(a, "skin_mm", None),
                 rear_len_mm=getattr(a, "rear_mm", None), with_cargo=not getattr(a, "no_cargo", False),
                 cargo_placement=json.loads(a.cargo_json) if getattr(a, "cargo_json", None) else None,
                 lattice=json.loads(a.lattice_json) if getattr(a, "lattice_json", None) else None,
                 freeform=_freeform(a))
    return g, {"param_body": bp.as_dict(), "spacing_mm": a.cfd_mm,
               "build": getattr(g, "build_report", {})}



def parts_and_joints(a, out: Path, geom, body_stl: Path, parts_dir: str, **p4kw) -> dict:
    """Part 4 parts on this body, then the joints: every printed part becomes a
    positive glued into a milled pocket (Part 4 joints.py). The mass the
    joints move (plastic plugs for foam, buried CAD trimmed off) goes into the
    hardware masses the rollup uses. Manufacturing files go to out/manufacture."""
    import assembly as p4
    import joints
    asm = p4.build(a.W, a.x_front, a.d_halo, str(body_stl), str(out / parts_dir), **p4kw)
    asm["_dir"] = str(out / parts_dir)
    asm["ballast_g"] = getattr(a, "ballast_g", 0.0)
    if getattr(a, "no_joints", False):
        # Search builds (search/layout/layout_car.py): no pockets or glue joints (joints.make_all's
        # Minkowski sliver pass takes 20+ minutes on the halo mesh). The car's mass is the drawn body's
        # foam plus the printed parts as drawn; a finalist is rebuilt with the joints.
        import unified_phi as up
        body_g = sum(c.mass_kg for c in up.compute_mass_com(geom)) * 1e3
        asm["joints"] = {"manufactured_g": body_g + sum(asm["parts_mass_g"].values()), "mass_delta_kg": {},
                         "manufactured": {}, "skipped": True}
        return asm
    import trimesh
    lm = geom.landmarks
    jr = joints.make_all(trimesh.load(str(body_stl), force="mesh"), asm,
                         lm["ref_plane_A_m"] * 1e3, lm["rear_face_m"] * 1e3,
                         out / "manufacture")
    f, d = asm["fixed_hardware_kwargs"], jr["mass_delta_kg"]
    sup = d.get("supports", 0.0)
    f["wheels_front_mass_kg"] += sup / 2
    f["wheels_rear_mass_kg"] += sup / 2
    f["wheels_axles_mass_kg"] += sup
    f["rear_wing_mass_kg"] += sum(v for k, v in d.items() if k != "supports")
    asm["joints"] = jr
    return asm


def manufactured_mass_kg(asm) -> float:
    """The car as it is made, without the cartridge: every machined and printed
    file's own volume x its material (Part 4 joints), the wheels with their
    bearings, and the halo. This, not the model's rollup, is what the
    scrutineer's scale reads: on 2026-09-30 a car the rollup put at 48.21 g
    was 47.84 g as manufactured -- under the 48.0 g floor."""
    wd = asm["wheel_design"]
    return (asm["joints"]["manufactured_g"] + 2 * wd["front"]["mass_g"] + 2 * wd["rear"]["mass_g"]
            + asm.get("ballast_g", 0.0)) * 1e-3 + asm["fixed_hardware_kwargs"]["halo_mass_kg"]


MASS_TOL_KG = 5e-5            # the car as manufactured: 48.2 +- 0.05 g (BUILD_SPEC 12.4)


def mass_refusal(err_kg: float, fixed_skin: bool) -> str | None:
    """Why a sized car is refused on its mass, or None. A fixed-skin build (gradient checks,
    stress cars) is not sized, so it is never refused here; the referee still weighs it."""
    if fixed_skin or abs(err_kg) <= MASS_TOL_KG:
        return None
    return f"mass_not_converged: car {err_kg * 1e3:+.3f} g from the target (tolerance 0.05 g)"


def build_car(a, out: Path, **p4kw):
    """Body and parts until the car AS MANUFACTURED weighs the target (48.2 +- 0.05 g).

    The parts' masses depend on the body (joints, pockets, and the support's design), so
    the body target is searched on the true manufactured mass: each pass builds the body,
    the parts and the joints and weighs the whole car. The next body mass is a secant
    between passes on either side of the target (bisection if the secant leaves the
    bracket), else a 1:1 step. The old damped fixed point oscillated when the support's
    design flipped with a tiny body change (+0.5 <-> +3.5 g) and judged a body built at a
    stale target after 6 passes (50.53 / 48.10 / 47.42 g, Part 4 43612741618, 2026-11-14).
    The car judged is always one built at its own final target; if no pass is within
    0.05 g, info["mass_converged"] is False and the error is named (never passed quietly)."""
    import ballast
    import unified_phi as up
    T = ballast.target_competition_kg()
    pts, best, t = [], None, None             # pts: (body kg built, car error kg)
    modes = None

    def run(target, pass_):
        a._body_target_kg = target
        geom, info = build_body(a, out)
        info.update(export_body(geom, out / "body_half.stl"))
        # Pass 1 picks the support design; every later pass holds it (Part 4 f52a604), so the
        # parts' mass cannot jump between designs as the body is resized.
        asm = parts_and_joints(a, out, geom, out / "body_half.stl", "parts",
                               **dict(p4kw, **({"support_modes": modes} if modes else {})))
        body = sum(c.mass_kg for c in up.compute_mass_com(geom))
        err = manufactured_mass_kg(asm) - T
        log(f"  pass {pass_}: body {body*1e3:.3f} g, car {(T + err)*1e3:.3f} g ({err*1e3:+.3f}); joints "
            + ", ".join(f"{k} {v*1e3:+.2f}" for k, v in asm["joints"]["mass_delta_kg"].items())
            + f"; supports each {[round(x, 2) for x in asm['info'].get('support_mass_g_each', [])]}")
        return geom, info, asm, body, err

    pass_ = 0
    for pass_ in range(1, 9):
        geom, info, asm, body, err = run(t, pass_)
        pts.append((body, err))
        if modes is None:
            modes = asm["info"].get("support_mode")
        if best is None or abs(err) < abs(best[1]):
            best = (body, err, pass_)
        if getattr(a, "skin_mm", None) is not None or abs(err) <= MASS_TOL_KG:
            break                                  # fixed skin: nothing to iterate
        lo = max((p for p in pts if p[1] < 0), key=lambda p: p[0], default=None)
        hi = min((p for p in pts if p[1] > 0), key=lambda p: p[0], default=None)
        if lo and hi:
            if hi[0] - lo[0] < 1e-6:
                break                              # a jump in the car's mass straddles the target
            x = lo[0] - lo[1] * (hi[0] - lo[0]) / (hi[1] - lo[1])
            if not lo[0] < x < hi[0]:
                x = 0.5 * (lo[0] + hi[0])
            t = x
        else:
            t = body - err                         # one gram of body is one gram of car
    if best[2] != pass_:                           # the files on disk must be the judged car's
        geom, info, asm, body, err = run(best[0], pass_ + 1)
        pass_ += 1
    info["body_target_g"] = body * 1e3
    info["build_passes"] = pass_
    info["body_targets_g"] = [p[0] * 1e3 for p in pts]
    info["car_mass_error_g"] = err * 1e3
    info["mass_converged"] = abs(err) <= MASS_TOL_KG
    if not info["mass_converged"]:
        log(f"  MASS NOT CONVERGED: car {(T + err)*1e3:.3f} g, {err*1e3:+.3f} g from the target")
    return geom, info, asm


def part4_kwargs(a) -> dict:
    import beam_support as bsm
    kind = getattr(a, "support", "beam")
    sup = {"cad": None, "beam": bsm.BeamSupport(), "engine": None}[kind]
    if kind == "beam" and getattr(a, "support_json", None):
        sup = bsm.BeamSupport(**json.loads(a.support_json))
    if kind == "engine":                      # the searches' own supports (car/parts/support_engine.py)
        import support_engine as se
        sup = se.SupportDesign(**json.loads(getattr(a, "support_json", None) or "{}"))
    # The body ends at Ref A; the nose cone is a printed SLS PA12 shell (team
    # spec 2026-09-27) whose root takes the body's section 1 mm aft of Ref A.
    import nose as ns
    nk = dict(blend_after_ref_a_mm=1.0, root_scale=1.0, material="ABS", wall_mm=1.0)
    if getattr(a, "nose_json", None):
        nk.update(json.loads(a.nose_json))
    kw = {"support": sup, "nose": ns.NoseCone(**nk), "freeform": _freeform(a),
          "supports": not getattr(a, "no_supports", False), "tethers": not getattr(a, "no_tethers", False)}
    if getattr(a, "tether_json", None):
        kw["tether_offsets_mm"] = tuple(json.loads(a.tether_json))
    if getattr(a, "rear_mm", None) is not None:
        kw["rear_face_mm"] = a.x_front + a.W + a.rear_mm
    if getattr(a, "fwing_json", None):
        fj = json.loads(a.fwing_json)
        if "pieces" in fj:                    # the searches' wing (car/parts/front_wing_engine.py)
            import front_wing_engine as fwe
            kw["front"] = fwe.from_dict(fj)
        else:
            import wings as wg
            kw["front"] = wg.FrontWing(**fj)
    if getattr(a, "rwing_json", None):
        rj = json.loads(a.rwing_json)
        if "support" in rj:                   # the searches' wing (car/parts/rear_wing_engine.py)
            import rear_wing_engine as rwe
            kw["rear"] = rwe.from_dict(rj)
        else:
            import wings as wg
            kw["rear"] = wg.RearWing(**rj)
    return kw


SPECK_MM3 = 20.0          # a field piece this small, not in the made body, is not a second body (T4.1)


def export_body(geom, path: Path) -> dict:
    import unified_phi as up
    from scipy.ndimage import label
    half = up.extract_half_surface(geom)
    half.vertices[half.vertices[:, 1] < 0, 1] = 0.0
    if len(half.faces) > MAX_BODY_FACES:      # a 0.3 mm grid otherwise runs a 16 GB machine out of memory
        # manifold's simplify keeps it a closed solid, which decimation does not (20 um)
        import manifold3d as m3
        import numpy as np
        import trimesh
        o = m3.Manifold(m3.Mesh(vert_properties=np.asarray(half.vertices, np.float32),
                                tri_verts=np.asarray(half.faces, np.uint32))).simplify(2e-5).to_mesh()
        half = trimesh.Trimesh(np.asarray(o.vert_properties)[:, :3], np.asarray(o.tri_verts), process=False)
        half.merge_vertices()
    if not half.is_watertight:
        # Zero-area triangles where the surface passes through a grid point pinch it there
        # (four and eight faces on an edge, 1 car in 1000). Without them it closes.
        half.update_faces(half.nondegenerate_faces())
        half.remove_unreferenced_vertices()
        half.merge_vertices()
    half.export(str(path), file_type="stl_ascii")
    lab, n = label(geom.phi.grid < 0)
    if not half.is_watertight:
        raise SystemExit(f"body STL {path.name} is not watertight; Part 2 would reject it")
    # A piece of the field apart from the main one is a second body -- unless the body as made holds it:
    # the halo's loft is united with the mesh exactly (exact_zones.cut_boxes), and on the field's grid it can
    # stand a cell off the rest (gallery G01: "2 bodies", the mesh one piece). Each piece is recorded.
    pieces, n_apart = [], 0
    if n > 1:
        import numpy as np
        r, d = geom.region, None
        from geometry_contract import GRID_SPACING_M as d
        sizes = np.bincount(lab.ravel())
        sizes[0] = 0
        main = int(sizes.argmax())
        for i in range(1, n + 1):
            idx = np.argwhere(lab == i)
            P = (np.asarray(r.origin_m) + idx * d)
            P[:, 1] = np.abs(P[:, 1])
            # (its cells' centres in the made body: 90 %, as a boundary cell's centre can sit just outside)
            held = float(half.contains(P[np.linspace(0, len(P) - 1, min(len(P), 64)).astype(int)]).mean()) >= 0.9
            pieces.append({"cells": int(sizes[i]), "bounds_mm": np.round(np.r_[P.min(0), P.max(0)] * 1e3, 1).tolist(),
                           "main": i == main, "in_the_mesh": held})
            # a speck the mesh dropped (under SPECK_MM3) is not in the car that gets made: recorded, not a body
            speck = sizes[i] * (d * 1e3) ** 3 < SPECK_MM3
            pieces[-1]["speck"] = bool(speck)
            n_apart += int(i != main and not held and not speck)
    return {"faces": len(half.faces), "watertight": bool(half.is_watertight),
            "field_bodies": 1 + n_apart if n > 1 else int(n), "field_pieces": pieces,
            "t55_cells_protected": getattr(geom, "t55_cells_protected", 0)}


# --------------------------------------------------------------------------- mass
def mass_state(geom, asm) -> dict:
    """The model's roll-up: the milled body's cells (car/body compute_mass_com) and the fixed hardware
    (car/race mass_com_ingest) at their COMs; competition mass is without the cartridge."""
    import unified_phi as up
    from mass_com_ingest import FixedHardwareSpec, ingest_mass_com
    from ballast import CARTRIDGE_KG
    m = ingest_mass_com(up.compute_mass_com(geom), FixedHardwareSpec(**asm["fixed_hardware_kwargs"]))
    return {"total_g": m.total_mass_kg * 1e3, "competition_mass_g": (m.total_mass_kg - CARTRIDGE_KG) * 1e3,
            "com_x_mm": m.com_x_m * 1e3, "com_z_mm": m.com_z_m * 1e3}


def recommend(legal: dict) -> list:
    bad = [k for k, v in legal.items() if not v["pass"]]
    return [f"FIX LEGALITY FIRST: {', '.join(bad)}."] if bad else []


# --------------------------------------------------------------------------- report
def write_report(out: Path, S: dict) -> None:
    L = [f"# Car report — W {S['scalars']['W']} mm, x_front {S['scalars']['x_front']} mm, "
         f"d_halo {S['scalars']['d_halo']} mm", ""]
    ms = S["mass"]
    L += ["## Mass", "", "| item | value |", "|---|---|",
          f"| mass as manufactured (T3.6) | {ms.get('manufactured_mass_g', ms['competition_mass_g']):.2f} g |",
          f"| mass by the model's rollup | {ms['competition_mass_g']:.2f} g |",
          f"| COM x / z | {ms['com_x_mm']:.1f} / {ms['com_z_mm']:.1f} mm |",
          f"| wheel design | {S['wheels']['design']} (mean I {S['wheels']['mean_I_kg_m2']*1e9:.1f} g·mm²) |",
          ""]
    lg = S["legality"]
    L += [f"## Legality — {lg['summary']['n_checks']} checks, {lg['summary']['n_failed']} failed", "",
          "| rule | margin | pass | note |", "|---|---|---|---|"]
    for k, v in sorted(lg["checks"].items(), key=lambda kv: (kv[1]["pass"], kv[0])):
        L.append(f"| {k} | {v['margin']:+.2f} | {'yes' if v['pass'] else '**NO**'} | {v['note']} |")
    L += ["", "## Recommendations", ""] + [f"- {r}" for r in S["recommendations"]]
    (out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- main

def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--W", type=float, default=120.3)
    ap.add_argument("--x-front", type=float, default=46.0)
    ap.add_argument("--d-halo", type=float, default=43.72)
    ap.add_argument("--cfd-mm", type=float, default=1.0)
    ap.add_argument("--rear-mm", type=float, default=None,
                    help="rear axle -> body rear face, mm (default Ref B + 40 = 56)")
    ap.add_argument("--no-supports", action="store_true", help="no wheel supports (layout search)")
    ap.add_argument("--no-joints", action="store_true", help="skip the glue joints / pockets (search builds; mass as drawn)")
    ap.add_argument("--no-tethers", action="store_true", help="no tether guides (layout search)")
    ap.add_argument("--no-cargo", action="store_true", help="no T4.2 virtual cargo (team rule, layout search)")
    ap.add_argument("--cargo-json", default=None, help='T4.2 cargo placement {"x_start_m", "z_base_m", "flip"}')
    ap.add_argument("--lattice-json", default=None, help="free-form body change (param_body.build lattice=)")
    ap.add_argument("--freeform-json", default=None,
                    help="free-form body and nose (car/body/freeform.py): JSON, or a path to a JSON file")
    ap.add_argument("--tether-json", default=None, help="[front guide ahead of the front axle, rear guide behind the rear axle], mm (T6.1 <= 10)")
    ap.add_argument("--support", choices=("cad", "beam", "engine"), default="beam",
                    help="beam = the team's architecture, parametric; cad = the v2 CAD supports (reference); "
                         "engine = generated from the body (support_engine.py, the searches)")
    ap.add_argument("--support-json", default=None, help="BeamSupport parameters as JSON")
    ap.add_argument("--nose-json", default=None, help="NoseCone parameters as JSON (parametric body)")
    ap.add_argument("--fwing-json", default=None, help="FrontWing parameters as JSON")
    ap.add_argument("--rwing-json", default=None, help="RearWing parameters as JSON")
    ap.add_argument("--skin-mm", type=float, default=None,
                    help="fixed skin offset: no mass sizing (gradient checks)")
    ap.add_argument("--ballast-g", type=float, default=0.0,
                    help="legal ballast under the halo (T1.22); the body is sized for the rest")
    ap.add_argument("--body-json", default="{}",
                    help="parametric body (Part 1 param_body.BodyParams) as JSON; '{}' = the start car")
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    import legality

    S = {"scalars": {"W": a.W, "x_front": a.x_front, "d_halo": a.d_halo},
         "args": vars(a)}
    log("1-2 BODY + PARTS: parametric body sized against the manufactured parts")
    p4kw = part4_kwargs(a)
    geom, S["body"], asm = build_car(a, out, **dict(p4kw))
    # A short layout: Part 1's heaviest reachable body is still under 48 g, so the rest goes
    # in as lead in the T1.22 container (user's decision, 2026-11-11). The referee checks it.
    need = float(S["body"].get("build", {}).get("ballast_needed_g") or 0.0)
    if need > 0 and not a.ballast_g:
        a.ballast_g = need
        asm["ballast_g"] = need
        log(f"  short layout: {need:.2f} g of ballast in the container under the halo")
    # Refuse a car that did not size (MINI DON, 2026-11-15): no CFD, named in summary.json.
    import ballast as _bt
    why = mass_refusal(manufactured_mass_kg(asm) - _bt.target_competition_kg(), getattr(a, "skin_mm", None) is not None)
    if why:
        S["refused"] = {"reason": why, "car_mass_g": manufactured_mass_kg(asm) * 1e3, "body": S["body"].get("body_targets_g")}
        (out / "summary.json").write_text(json.dumps(S, indent=2, default=str))
        raise SystemExit(f"car refused: {why}")
    S["wheels"] = asm["wheel_design"]
    S["parts_mass_g"] = asm["parts_mass_g"]

    ms = mass_state(geom, asm)
    ms["manufactured_mass_g"] = manufactured_mass_kg(asm) * 1e3
    S["mass"] = {k: v for k, v in ms.items() if not k.startswith("_")}
    # Even triangles in the files that get made, once sizing has settled.
    import mesh_fairing
    for name, part in asm["joints"]["manufactured"].items():
        if "file" in part:
            part.update(mesh_fairing.remesh_file(part["file"], 0.6 if name == "machined_body" else 0.4))
    S["manufactured"] = asm["joints"]["manufactured"]
    import assembly as p4                # mass_report.json for Part 2 (Part 4 writes it)
    S["mass_report"] = p4.write_mass_report(asm, out / "mass_report.json")
    if a.ballast_g:
        import ballast as _b
        S["mass"].update(ballast_g=a.ballast_g, capacity_g=_b.capacity_kg("lead") * 1e3)
    asm["cargo_placement"] = geom.landmarks.get("cargo_placement")

    log("3 LEGAL")
    # --no-joints: the referee judges the body and the parts as drawn (no manufacturing files to read)
    asm_ref = {k: v for k, v in asm.items() if k != "joints"} if asm["joints"].get("skipped") else asm
    chk = legality.check(str(out / "body_half.stl"), asm_ref, S["mass"], S["body"]["field_bodies"],
                         machined_stl=asm["joints"].get("machined_body_half_stl"))
    S["legality"] = {"checks": chk, "summary": legality.summary(chk)}
    sha = lambda p: __import__("hashlib").sha256(Path(p).read_bytes()).hexdigest()
    S["hashes"] = {"judged_body_half_stl": sha(out / "body_half.stl")}
    S["recommendations"] = recommend(S["legality"]["checks"])
    (out / "summary.json").write_text(json.dumps(S, indent=2, default=str))
    write_report(out, S)
    log(f"done: {S['legality']['summary']}")
    return S


if __name__ == "__main__":
    main()
