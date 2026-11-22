"""The air volume around the car as a STEP solid, for SimScale's standard (OpenFOAM) solver.

The same idea as the team's Fusion add-in (OpenCFD_fusion_addin.py): a half wind tunnel, the car cut
out of it with a solid Boolean, the result written as STEP, every face labelled by where it is.
Here it is done with OpenCASCADE (the kernel this repo already uses to read the team's STEP):

  car body (body_full.stl, the whole car, so it crosses the symmetry plane cleanly) and the +y wheels
  -> sewn into solids -> cut from the box  x [-3 L, +8 L], y [0, 5 W], z [0, 5 H]  (Part 2's tunnel)
  -> faces named inlet / outlet / symmetry / side / top / ground (planes of the box) and wheelF /
     wheelR (faces of the wheel solids); every other face is the car
  -> STEP in mm, with the names written on the faces.

    python simscale_step_domain.py <car_folder> [--out <car_folder>/domain.step]
"""
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
import repo_paths  # noqa: E402,F401
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent

ROAD_GAP_MM = 0.15           # the team's choice: the road 0.15 mm BELOW the wheels' lowest point (no contact)
SINK_MM = -ROAD_GAP_MM       # kept for callers: how far the wheels go into the road (negative = a gap)
DOMAIN_MM = ((-771.0, 0.0, 0.0), (2314.0, 192.0, 245.0))   # Part 2's half tunnel for this car


def stl_solid(mesh_mm):
    """A closed triangle mesh (mm) -> an OpenCASCADE solid (one planar face per triangle)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.StlAPI import StlAPI_Reader
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Shape
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m.stl"
        mesh_mm.export(p)
        shape = TopoDS_Shape()
        StlAPI_Reader().Read(shape, str(p))
    sew = BRepBuilderAPI_Sewing(1e-4)
    sew.Add(shape); sew.Perform()
    ex = TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL)
    shell = TopoDS.Shell(ex.Current())
    solid = BRepBuilderAPI_MakeSolid(shell).Solid()
    fix = ShapeFix_Solid(solid); fix.Perform()                      # outward orientation
    return fix.Solid()


def volume(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    g = GProp_GProps(); BRepGProp.VolumeProperties_s(shape, g)
    return g.Mass()


def build(folder: Path, out: Path, domain=DOMAIN_MM):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    t0 = time.time()
    folder = Path(folder)
    body = trimesh.load(folder / "body_full.stl"); body.apply_scale(1e3)
    wheels = {}
    for w in ("wheelF", "wheelR"):
        m = trimesh.load(folder / f"{w}.stl"); m.apply_scale(1e3); wheels[w] = m
    car_s = stl_solid(body)
    wheel_s = {w: stl_solid(m) for w, m in wheels.items()}
    (x0, y0, _), (x1, y1, z1) = domain
    z0 = min(float(m.bounds[0, 2]) for m in wheels.values()) - ROAD_GAP_MM   # e.g. wheels at -0.3 -> road at -0.45
    domain = ((x0, y0, z0), (x1, y1, z1))
    box = BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), gp_Pnt(x1, y1, z1)).Shape()
    cut = BRepAlgoAPI_Cut()
    from OCP.OCP.collections import List_TopoDS_Shape
    args, tools = List_TopoDS_Shape(), List_TopoDS_Shape()
    args.Append(box)
    for s_ in [car_s, *wheel_s.values()]:
        tools.Append(s_)
    cut.SetArguments(args); cut.SetTools(tools)
    cut.SetFuzzyValue(1e-5); cut.Build()
    assert cut.IsDone(), "Boolean failed"
    fluid = cut.Shape()
    v_box = (x1 - x0) * (y1 - y0) * (z1 - z0)
    removed = v_box - volume(fluid)
    expect = 0.5 * body.volume + sum(m.volume for m in wheels.values())
    labels = label_faces(fluid, cut, wheel_s, domain)
    write_step(fluid, labels, out)
    counts = {}
    for n in labels.values():
        counts[n] = counts.get(n, 0) + 1
    return {"step": str(out), "removed_mm3": removed, "expected_mm3": expect,
            "removed_share": removed / expect, "faces": counts, "secs": round(time.time() - t0)}


def label_faces(fluid, cut, wheel_s, domain):
    """{face: name} for the tunnel planes and the wheel faces; the rest (unnamed) is the car."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    (x0, y0, z0), (x1, y1, z1) = domain
    tol = 1e-3
    labels = {}
    # wheel faces: the result faces that come from each wheel solid (unchanged or modified)
    wheel_faces = []
    for name, ws in wheel_s.items():
        ex = TopExp_Explorer(ws, TopAbs_FACE)
        while ex.More():
            f = ex.Current()
            mod = cut.Modified(f)
            if mod.Size() if hasattr(mod, 'Size') else len(mod):
                for g in mod:
                    wheel_faces.append((g, name))
            elif not cut.IsDeleted(f):
                wheel_faces.append((f, name))
            ex.Next()
    ex = TopExp_Explorer(fluid, TopAbs_FACE)
    while ex.More():
        f = TopoDS.Face(ex.Current())
        name = None
        s = BRepAdaptor_Surface(f)
        if s.GetType() == GeomAbs_Plane:
            pl = s.Plane(); n = pl.Axis().Direction(); o = pl.Location()
            nv = np.array([n.X(), n.Y(), n.Z()]); ov = np.array([o.X(), o.Y(), o.Z()])
            for nm, ax, val in (("inlet", 0, x0), ("outlet", 0, x1), ("symmetry", 1, y0), ("side", 1, y1),
                                ("ground", 2, z0), ("top", 2, z1)):
                if abs(abs(nv[ax]) - 1) < 1e-9 and abs(ov[ax] - val) < tol:
                    name = nm
                    break
        if name is None:
            for g, wn in wheel_faces:
                if f.IsSame(g):
                    name = wn
                    break
        if name is not None:
            labels[f] = name
        ex.Next()
    return labels


def write_step(fluid, labels, out: Path):
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    lab = st.AddShape(fluid, False)
    TDataStd_Name.Set_s(lab, TCollection_ExtendedString("fluid"))
    for f, name in labels.items():
        sub = st.AddSubShape(lab, f)
        if not sub.IsNull():
            TDataStd_Name.Set_s(sub, TCollection_ExtendedString(name))
    from OCP.STEPCAFControl import STEPCAFControl_Controller
    STEPCAFControl_Controller.Init_s()                              # registers the write.stepcaf.* options
    assert Interface_Static.SetIVal_s("write.stepcaf.subshapes.name", 1), "subshape-name option missing"
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    w = STEPCAFControl_Writer()
    w.SetNameMode(True)
    assert w.Transfer(doc, STEPControl_AsIs), "STEP transfer failed"
    assert w.Write(str(out)) == IFSelect_RetDone, "STEP write failed"


def to_car_frame(shape, x_nose_mm):
    """STEP frame -> car frame (mm): x from the nose tip (x' = x_nose - X), flow +x. A mirror."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf
    tr = gp_Trsf(); tr.SetMirror(gp_Ax2(gp_Pnt(x_nose_mm / 2.0, 0, 0), gp_Dir(1, 0, 0)))
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def build_exact(out: Path, spec=None, domain=DOMAIN_MM):
    """The team's car exactly as in its STEP (no triangles): body and the +y wheels cut from the tunnel."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.OCP.collections import List_TopoDS_Shape
    from OCP.gp import gp_Pnt
    import cadio as CI
    from geometry import CarSpec
    t0 = time.time()
    s = spec or CarSpec()
    solids = CI.read_step_solids(s.step)
    body = to_car_frame(CI.outer_solid(solids[s.body_solid]), s.x_nose_mm)
    wheel_s = {"wheelF": to_car_frame(solids["wheel_fl"], s.x_nose_mm), "wheelR": to_car_frame(solids["wheel_rl"], s.x_nose_mm)}
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    zmin = []
    for w in wheel_s.values():
        b = Bnd_Box(); BRepBndLib.Add_s(w, b, False); zmin.append(b.CornerMin().Z())
    # The team's choice: car and wheels exactly as in the STEP; the road ROAD_GAP_MM under the wheels' lowest point
    drop = 0.0
    (x0, y0, _), (x1, y1, z1) = domain
    z0 = min(zmin) - ROAD_GAP_MM
    domain = ((x0, y0, z0), (x1, y1, z1))
    box = BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), gp_Pnt(x1, y1, z1)).Shape()
    cut = BRepAlgoAPI_Cut()
    args, tools = List_TopoDS_Shape(), List_TopoDS_Shape()
    args.Append(box)
    for sh in [body, *wheel_s.values()]:
        tools.Append(sh)
    cut.SetArguments(args); cut.SetTools(tools); cut.SetFuzzyValue(1e-5); cut.Build()
    assert cut.IsDone(), "Boolean failed"
    fluid = cut.Shape()
    removed = (x1 - x0) * (y1 - y0) * (z1 - z0) - volume(fluid)
    expect = 0.5 * volume(body) + sum(volume(w) for w in wheel_s.values())
    labels = label_faces(fluid, cut, wheel_s, domain)
    write_step(fluid, labels, out)
    counts = {}
    for n in labels.values():
        counts[n] = counts.get(n, 0) + 1
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    nf = 0; ex = TopExp_Explorer(fluid, TopAbs_FACE)
    while ex.More():
        nf += 1; ex.Next()
    return {"step": str(out), "removed_mm3": removed, "expected_mm3": expect, "removed_share": removed / expect,
            "faces_total": nf, "named": counts, "ground_mm": z0, "wheel_bottom_mm": min(zmin), "road_gap_mm": ROAD_GAP_MM, "secs": round(time.time() - t0)}


# ---------------------------------------------------------------------- designed cars
SEAM_MM = 0.3                # exact-CAD / triangle-pod seam this far outside the design region (seam_region)
SEAM_OVERLAP_MM = 0.0        # pod and kept CAD meet exactly on the seam planes (any overlap broke the OCC cut on some cars)
POD_FACES = 4500             # triangles kept on the designed pod (SimScale imports a few thousand faces; 32k failed)


def _geom_error(msg):
    from simscale_step_eval import GeometryError
    return GeometryError(msg)


def _fused(shape):
    """Merge coplanar neighbouring faces (the region's flat cut planes come in as many triangles)."""
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    u = ShapeUpgrade_UnifySameDomain(shape, True, True, False)
    u.Build()
    return u.Shape()


def _region_solid(M):
    """manifold3d region (STEP frame, mm, planar faces) -> OCC solid with merged planar faces."""
    import cadio as CI
    return _fused(stl_solid(CI.from_manifold(M)))


def _car_frame_mesh(m, x_nose_mm):
    t = m.copy()
    t.vertices[:, 0] = x_nose_mm - t.vertices[:, 0]
    t.invert()
    return t


def seam_region(car, grow_mm):
    """The sidepod region grown by `grow_mm` on every side, the ceiling included (manifold3d, STEP frame).
    The SimScale seam between exact CAD and the triangle pod lies on this, SEAM_MM outside the design
    region: the region's own planes (the 27.175 mm sidepod top, the spine underside at z = 17) are
    planes of the team's CAD, and a seam lying ON a CAD face gives faults SimScale's import cannot heal."""
    import dataclasses
    s0 = car.s
    if s0.ceiling_mm is not None:
        car.s = dataclasses.replace(s0, ceiling_mm=s0.ceiling_mm + grow_mm)
    try:
        return car._region_manifold(grow_mm)
    finally:
        car.s = s0


def pod_mesh(car, body_mesh, faces=POD_FACES, grow_mm=2.0):
    """The designed body inside the seam region (+y side, STEP frame, mm), reduced to `faces`
    well-shaped triangles, meeting the kept CAD on the seam planes. Outside the design region the
    body IS the team's CAD, so the band between the region and the seam is the original shape."""
    import manifold3d as mf
    import pymeshlab as ml
    import cadio as CI
    plus_y = mf.Manifold.cube([1000.0, 500.0, 500.0]).translate([-500.0, -1.0, -100.0])
    m = CI.from_manifold(CI.to_manifold(body_mesh) ^ (seam_region(car, SEAM_MM + grow_mm) ^ plus_y))
    if len(m.faces) > faces:
        ms = ml.MeshSet(); ms.add_mesh(ml.Mesh(m.vertices, m.faces))
        ms.meshing_decimation_quadric_edge_collapse(targetfacenum=faces, qualitythr=0.5, preservenormal=True, planarquadric=True,
                                                     planarweight=0.002, optimalplacement=True, preservetopology=True, autoclean=True)
        mm = ms.current_mesh()
        m = trimesh.Trimesh(mm.vertex_matrix(), mm.face_matrix(), process=True)
        if m.volume < 0:
            m.invert()
        if not m.is_watertight:
            m = CI.repair(m)
    pod = CI.from_manifold(CI.to_manifold(m) ^ (seam_region(car, SEAM_MM + SEAM_OVERLAP_MM) ^ plus_y))
    return CI.clean(pod)


def build_design(car, body_mesh, out: Path, domain=DOMAIN_MM, faces=POD_FACES):
    """A designed car (Car.build's body mesh, STEP frame, mm) as a SimScale air volume: the team's
    exact CAD outside the sidepod region (B-rep minus the exact region), the designed pod inside it
    (faceted, a few thousand triangles), the exact wheels; road ROAD_GAP_MM under the wheels."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.OCP.collections import List_TopoDS_Shape
    from OCP.gp import gp_Pnt
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    import cadio as CI
    t0 = time.time()
    s = car.s
    solids = CI.read_step_solids(s.step)
    body = CI.outer_solid(solids[s.body_solid])
    kc = BRepAlgoAPI_Cut(body, _region_solid(seam_region(car, SEAM_MM))); kc.SetFuzzyValue(1e-5); kc.Build()
    if not kc.IsDone():
        raise _geom_error("kept-CAD Boolean failed")
    kept = to_car_frame(kc.Shape(), s.x_nose_mm)
    pm = pod_mesh(car, body_mesh, faces)
    pod = _fused(stl_solid(_car_frame_mesh(pm, s.x_nose_mm)))
    wheel_s = {"wheelF": to_car_frame(solids["wheel_fl"], s.x_nose_mm), "wheelR": to_car_frame(solids["wheel_rl"], s.x_nose_mm)}
    zmin = []
    for w in wheel_s.values():
        b = Bnd_Box(); BRepBndLib.Add_s(w, b, False); zmin.append(b.CornerMin().Z())
    (x0, y0, _), (x1, y1, z1) = domain
    z0 = min(zmin) - ROAD_GAP_MM
    domain = ((x0, y0, z0), (x1, y1, z1))
    expect = 0.5 * body_mesh.volume + sum(volume(w) for w in wheel_s.values())
    V = (x1 - x0) * (y1 - y0) * (z1 - z0)
    # The fuzzy tolerance that works differs per car (1e-5 mm has removed half the car on one): try a
    # few, keep the first whose removed volume is car + wheels
    for fz in (0.0, 1e-6, 1e-5):
        box = BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), gp_Pnt(x1, y1, z1)).Shape()
        cut = BRepAlgoAPI_Cut()
        args, tools = List_TopoDS_Shape(), List_TopoDS_Shape()
        args.Append(box)
        for sh in [kept, pod, *wheel_s.values()]:
            tools.Append(sh)
        cut.SetArguments(args); cut.SetTools(tools)
        if fz:
            cut.SetFuzzyValue(fz)
        cut.Build()
        if not cut.IsDone():
            continue
        fluid = cut.Shape()
        from OCP.TopAbs import TopAbs_SOLID
        from OCP.TopoDS import TopoDS
        sols = []
        ex = TopExp_Explorer(fluid, TopAbs_SOLID)
        while ex.More():
            sols.append(TopoDS.Solid(ex.Current())); ex.Next()
        dropped = 0.0
        if len(sols) > 1:                     # air sealed inside the body: no flow reaches it
            vols = [volume(x) for x in sols]
            k = int(np.argmax(vols)); dropped = float(sum(vols) - vols[k]); fluid = sols[k]
        removed = V - volume(fluid) - dropped
        if abs(removed / expect - 1) < 0.003:
            break
    else:
        raise _geom_error(f"air-volume Boolean wrong at every tolerance (removed share {removed / expect:.4f})")
    labels = label_faces(fluid, cut, wheel_s, domain)
    counts = {}
    for n in labels.values():
        counts[n] = counts.get(n, 0) + 1
    nf, ns = 0, 0
    ex = TopExp_Explorer(fluid, TopAbs_FACE)
    while ex.More():
        nf += 1; ex.Next()
    from OCP.TopAbs import TopAbs_SOLID
    ex = TopExp_Explorer(fluid, TopAbs_SOLID)
    while ex.More():
        ns += 1; ex.Next()
    rep = {"step": str(out), "removed_mm3": removed, "expected_mm3": expect, "removed_share": removed / expect,
           "faces_total": nf, "solids": ns, "dropped_air_mm3": dropped, "pod_triangles": len(pm.faces), "named": counts, "ground_mm": z0,
           "secs": round(time.time() - t0)}
    ok = ns == 1 and abs(rep["removed_share"] - 1) < 0.003 and all(counts.get(n) for n in
                                                                    ("inlet", "outlet", "symmetry", "side", "top", "ground", "wheelF", "wheelR"))
    rep["ok"] = bool(ok)
    if ok:
        write_step(fluid, labels, out)
    return rep


# ---------------------------------------------------------------------- the route the evolution uses
CAR_FACES = 20000            # triangles on the half body: 0.0002 mm mean, ~0.03 mm worst error vs the full mesh


def car_half_mesh(body_mesh, faces=CAR_FACES):
    """The body (STEP frame, mm) cut at the symmetry plane (+y, overlapping 2 mm past it) and reduced
    to `faces` well-shaped triangles (pymeshlab quadric collapse: quality threshold, no flipped
    normals, flat areas kept flat). Returns (mesh, {mean, p99, max} deviation in mm)."""
    import manifold3d as mf
    import pymeshlab as ml
    import cadio as CI
    half = CI.clean(CI.from_manifold(CI.to_manifold(body_mesh) ^ mf.Manifold.cube([1000.0, 500.0, 500.0]).translate([-500.0, -2.0, -100.0])))
    ms = ml.MeshSet(); ms.add_mesh(ml.Mesh(half.vertices, half.faces))
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=faces, qualitythr=0.5, preservenormal=True, planarquadric=True,
                                                 planarweight=0.002, optimalplacement=True, preservetopology=True, autoclean=True)
    mm = ms.current_mesh()
    m = trimesh.Trimesh(mm.vertex_matrix(), mm.face_matrix(), process=True)
    if m.volume < 0:
        m.invert()
    if not m.is_watertight:
        raise _geom_error("reduced body is not watertight")
    _, d, _ = trimesh.proximity.closest_point(m, half.sample(20000, seed=0))
    return m, {"mean": float(d.mean()), "p99": float(np.percentile(d, 99)), "max": float(d.max())}


def build_faceted(spec, body_mesh, out: Path, domain=DOMAIN_MM, faces=CAR_FACES):
    """A car (body mesh, STEP frame, mm) as the SimScale air volume: the half body as ~20k planar
    triangles (ONE consistent surface: no exact-CAD/triangle seams, which SimScale's import rejects
    as bad face-face / invalid edges), exact wheels, road ROAD_GAP_MM under the wheels."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.OCP.collections import List_TopoDS_Shape
    from OCP.gp import gp_Pnt
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    import cadio as CI
    t0 = time.time()
    s = spec
    m, dev = car_half_mesh(body_mesh, faces)
    car_s = _fused(stl_solid(_car_frame_mesh(m, s.x_nose_mm)))
    solids = CI.read_step_solids(s.step)
    wheel_s = {"wheelF": to_car_frame(solids["wheel_fl"], s.x_nose_mm), "wheelR": to_car_frame(solids["wheel_rl"], s.x_nose_mm)}
    zmin = []
    for w in wheel_s.values():
        b = Bnd_Box(); BRepBndLib.Add_s(w, b, False); zmin.append(b.CornerMin().Z())
    (x0, y0, _), (x1, y1, z1) = domain
    z0 = min(zmin) - ROAD_GAP_MM
    domain = ((x0, y0, z0), (x1, y1, z1))
    box = BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), gp_Pnt(x1, y1, z1)).Shape()
    cut = BRepAlgoAPI_Cut()
    args, tools = List_TopoDS_Shape(), List_TopoDS_Shape()
    args.Append(box)
    for sh in [car_s, *wheel_s.values()]:
        tools.Append(sh)
    cut.SetArguments(args); cut.SetTools(tools); cut.SetFuzzyValue(1e-5); cut.Build()
    if not cut.IsDone():
        raise _geom_error("air-volume Boolean failed")
    fluid = cut.Shape()
    sols = []
    ex = TopExp_Explorer(fluid, TopAbs_SOLID)
    while ex.More():
        sols.append(TopoDS.Solid(ex.Current())); ex.Next()
    dropped = 0.0
    if len(sols) > 1:                         # air sealed inside the body: no flow reaches it
        vols = [volume(x) for x in sols]
        k = int(np.argmax(vols)); dropped = float(sum(vols) - vols[k]); fluid = sols[k]
    removed = (x1 - x0) * (y1 - y0) * (z1 - z0) - volume(fluid) - dropped
    expect = 0.5 * body_mesh.volume + sum(volume(w) for w in wheel_s.values())
    labels = label_faces(fluid, cut, wheel_s, domain)
    counts = {}
    for n in labels.values():
        counts[n] = counts.get(n, 0) + 1
    nf = 0
    ex = TopExp_Explorer(fluid, TopAbs_FACE)
    while ex.More():
        nf += 1; ex.Next()
    rep = {"step": str(out), "removed_share": removed / expect, "faces_total": nf, "car_triangles": len(m.faces),
           "deviation_mm": dev, "dropped_air_mm3": dropped, "named": counts, "ground_mm": z0, "secs": round(time.time() - t0)}
    rep["ok"] = bool(abs(rep["removed_share"] - 1) < 0.003 and dev["max"] < 0.5 and all(
        counts.get(n) for n in ("inlet", "outlet", "symmetry", "side", "top", "ground", "wheelF", "wheelR")))
    if rep["ok"]:
        write_step(fluid, labels, out)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="car folder (faceted car) or 'exact' (the team's STEP as is)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.folder == "exact":
        print(json.dumps(build_exact(Path(a.out or "domain_exact.step")), default=float))
        return
    out = Path(a.out) if a.out else Path(a.folder) / "domain.step"
    print(json.dumps(build(Path(a.folder), out), default=float))


if __name__ == "__main__":
    main()
