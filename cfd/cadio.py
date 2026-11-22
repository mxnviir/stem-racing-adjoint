"""Exact CAD in, exact meshes out.

STEP -> named B-rep solids (OCP) -> one tessellation per solid (BRepMesh, shared edges) ->
mesh repair only where the tessellator leaves slivers at degenerate edges (sphere poles of the
halo/helmet: 39 open edges on the trial car) -> watertight, coherently wound, manifold mesh.
Acceptance (asserted): watertight, winding consistent, manifold3d NoError, volume within
VOL_TOL of the B-rep's own volume.

Also: a ray-parity voxeliser for any grid (3 axes, majority vote), used for the checks and the
design grid. Voxels never become CFD geometry: they are only used inside the sidepod region and
always re-surfaced and Boolean-joined to the exact CAD.
"""
from __future__ import annotations

import sys
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
import repo_paths  # noqa: E402,F401
from pathlib import Path

import numpy as np

VOL_TOL = 0.005                       # 0.5 % of the B-rep volume


def read_step_solids(path) -> dict:
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    r = STEPControl_Reader()
    if r.ReadFile(str(path)) != 1:
        raise IOError(f"cannot read STEP {path}")
    r.TransferRoots()
    tr = r.WS().TransferReader()
    out = {}
    ex = TopExp_Explorer(r.OneShape(), TopAbs_SOLID)
    while ex.More():
        s = TopoDS.Solid(ex.Current())
        e = tr.EntityFromShapeResult(s, 1)
        name = e.Name().ToCString() if e is not None and e.Name() is not None else f"solid{len(out)}"
        out[name] = s
        ex.Next()
    return out


def brep_volume(solid) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, p)
    return float(p.Mass())


def outer_solid(solid):
    """The solid rebuilt from its outer shell only (drops CAD void artefacts, e.g. the trial
    car's 0.14 mm3 inner shell), sewn so every edge is shared."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    outer = TopoDS.Shell(TopExp_Explorer(solid, TopAbs_SHELL).Current())
    sew = BRepBuilderAPI_Sewing(1e-3)
    f = TopExp_Explorer(outer, TopAbs_FACE)
    while f.More():
        sew.Add(f.Current())
        f.Next()
    sew.Perform()
    shell = TopoDS.Shell(TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL).Current())
    return ShapeFix_Solid().SolidFromShell(shell)


def tessellate(solid, lin_mm=0.05, ang_rad=0.2, tmp: Path | None = None):
    """B-rep solid -> watertight trimesh (mm). Raises if the acceptance checks fail."""
    import tempfile

    import trimesh
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.StlAPI import StlAPI_Writer
    BRepMesh_IncrementalMesh(solid, lin_mm, False, ang_rad, True)
    tmp = Path(tmp or tempfile.mkdtemp())
    p = tmp / "_tess.stl"
    w = StlAPI_Writer()
    w.ASCIIMode = False
    w.Write(solid, str(p))
    m = trimesh.load(p)
    m.merge_vertices()
    if not m.is_watertight:
        m = repair(m)
    accept(m, brep_volume(solid))
    return m


def repair(m):
    """Close tessellation slivers (merge 1 um, drop duplicate/null faces, mend non-manifold
    edges, close small holes, coherent winding). pymeshlab, as pinned in the workflows."""
    import pymeshlab as ml
    import trimesh
    ms = ml.MeshSet()
    ms.add_mesh(ml.Mesh(np.asarray(m.vertices, float), np.asarray(m.faces)))
    ms.meshing_merge_close_vertices(threshold=ml.PureValue(1e-3))
    ms.meshing_remove_duplicate_faces()
    ms.meshing_remove_null_faces()
    for _ in range(3):                  # Boolean seams can leave fans that need more than one pass
        ms.meshing_repair_non_manifold_edges()
        ms.meshing_repair_non_manifold_vertices()
        ms.meshing_remove_null_faces()
        ms.meshing_remove_unreferenced_vertices()
        tm = ms.get_topological_measures()
        if tm["non_two_manifold_edges"] == 0 and tm["non_two_manifold_vertices"] == 0:
            break
    ms.meshing_close_holes(maxholesize=200)
    ms.meshing_re_orient_faces_coherently()
    r = ms.current_mesh()
    t = trimesh.Trimesh(r.vertex_matrix(), r.face_matrix(), process=True)
    if t.volume < 0:
        t.invert()
    return t


def to_manifold(m):
    import manifold3d as mf
    M = mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                            tri_verts=np.asarray(m.faces, np.uint32)))
    if M.status() != mf.Error.NoError:
        raise ValueError(f"not a manifold: {M.status()}")
    return M


def from_manifold(M):
    import trimesh
    g = M.to_mesh()
    # process=False: manifold3d's output is already exact and watertight; trimesh's vertex
    # welding merges distinct close vertices at Boolean seams and breaks it
    return trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3].astype(np.float64), np.asarray(g.tri_verts), process=False)


def clean(m):
    """A mesh as an STL reader will see it: corners welded, then zero-area slivers (left by
    Booleans and tessellation at degenerate edges) removed and re-welded."""
    import trimesh
    w = trimesh.Trimesh(np.asarray(m.vertices, float), np.asarray(m.faces), process=True)
    w.update_faces(w.nondegenerate_faces())
    w.remove_unreferenced_vertices()
    w.merge_vertices()
    w = repair(w)                       # always: merges vertices < 1 um (mm units), so nothing that
    if w.volume < 0:                    # close survives into a file read back in metres
        w.invert()
    return w


def accept(m, ref_volume=None, tol=VOL_TOL, name="mesh"):
    """Every exported mesh passes this or nothing is written. Tested WELDED, as a reader sees it."""
    import trimesh
    m = trimesh.Trimesh(np.asarray(m.vertices, float), np.asarray(m.faces), process=True)
    problems = []
    if not m.is_watertight:
        problems.append("not watertight")
    if not m.is_winding_consistent:
        problems.append("inconsistent winding")
    if m.volume <= 0:
        problems.append("inside-out")
    try:
        to_manifold(m)
    except ValueError as e:
        problems.append(str(e))
    if ref_volume is not None and abs(m.volume - ref_volume) > tol * ref_volume:
        problems.append(f"volume {m.volume:.1f} vs {ref_volume:.1f} mm3 (> {tol:.1%})")
    if problems:
        raise ValueError(f"{name}: " + "; ".join(problems))
    return True


def voxelize(mesh, xs, ys, zs) -> np.ndarray:
    """Cell-centre inside test by ray parity along x, y and z; a cell is inside when 2 of 3 agree."""
    from _parity import parity
    T = np.asarray(mesh.triangles, np.float64)
    gz = parity(T[:, :, [0, 1, 2]].copy(), xs, ys, zs, len(xs), len(ys), len(zs))
    gy = parity(T[:, :, [0, 2, 1]].copy(), xs, zs, ys, len(xs), len(zs), len(ys)).transpose(0, 2, 1)
    gx = parity(T[:, :, [1, 2, 0]].copy(), ys, zs, xs, len(ys), len(zs), len(xs)).transpose(2, 0, 1)
    return (gx.astype(np.int8) + gy + gz) >= 2


def write_ascii_named(mesh, path: Path, name: str, ref_volume=None, tol=VOL_TOL):
    """Write, then read the FILE back and accept it (the check is on what OpenFOAM will read)."""
    import trimesh
    lines = trimesh.exchange.stl.export_stl_ascii(mesh).splitlines()
    lines[0], lines[-1] = f"solid {name}", f"endsolid {name}"
    Path(path).write_text("\n".join(lines) + "\n")
    back = trimesh.load(path)
    accept(back, ref_volume, tol, name=f"{Path(path).name} (read back)")
