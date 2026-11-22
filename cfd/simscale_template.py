"""Create the SimScale simulation + mesh operation for one air-volume geometry, all through the API.

Faces are found by the names written into the STEP (simscale_step_domain.py): inlet, outlet,
symmetry, side, top, ground, wheelF, wheelR; every other face is the car. Settings as Part 2:

  incompressible, steady, k-omega SST; air (nu 1.48e-5); inlet (20, 0, 0) m/s; outlet 0 Pa;
  symmetry at y = 0; slip side and top; ground moving at (20, 0, 0) m/s (rolling road);
  wheels rotating about +y at -1416.43 rad/s (rim speed 20 m/s, rolling with the road);
  car no-slip; "Forces and moments" on car + wheels.
Mesh: SimScale's standard (Simmetrix) mesher, automatic sizing + a refinement box around the car.

    python simscale_template.py <project_id> <geometry_id> [--fineness 6] [--box_mm 1.5] [--iters 1000]
"""
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
import repo_paths  # noqa: E402,F401
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

U = 20.0
OMEGA = -1416.43                     # rad/s about +y: wheel bottom moves at +20 m/s with the road
NAMES = ("inlet", "outlet", "symmetry", "side", "top", "ground", "wheelF", "wheelR")


def faces_by_name(s, api, P, gid):
    """name -> [entity] from SDL/TYSA_UNAME; 'car' = every face without a name."""
    g = s.GeometriesApi(api)
    out, named = {}, set()
    for n in NAMES:
        es = g.get_geometry_mappings(P, gid, _class="face", attributes=["SDL/TYSA_UNAME"], values=[n], limit=1000, page=1).embedded
        out[n] = [e.name for e in es]
        named |= set(out[n])
    allf, page = [], 1
    while True:
        es = g.get_geometry_mappings(P, gid, _class="face", limit=1000, page=page).embedded
        allf += [e.name for e in es]
        if len(es) < 1000:
            break
        page += 1
    out["car"] = [f for f in allf if f not in named]
    vols = g.get_geometry_mappings(P, gid, _class="region", limit=10, page=1).embedded
    out["volume"] = [v.name for v in vols]
    return out


def wheel_centres_m():
    """Wheel axle centres in the car frame (m), from the team's STEP (bounding-box centres)."""
    import cadio as CI
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from geometry import CarSpec
    import simscale_step_domain as SD
    sp = CarSpec()
    solids = CI.read_step_solids(sp.step)
    out = {}
    zb = []
    for sol in ("wheel_fl", "wheel_rl"):
        b = Bnd_Box(); BRepBndLib.Add_s(SD.to_car_frame(solids[sol], sp.x_nose_mm), b, False); zb.append(b.CornerMin().Z())
    drop_mm = 0.0                                                    # wheels stay where the STEP has them
    for name, sol in (("wheelF", "wheel_fl"), ("wheelR", "wheel_rl")):
        b = Bnd_Box(); BRepBndLib.Add_s(SD.to_car_frame(solids[sol], sp.x_nose_mm), b)
        lo, hi = b.CornerMin(), b.CornerMax()
        x0, y0, z0, x1, y1, z1 = lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()
        out[name] = ((x0 + x1) / 2e3, (y0 + y1) / 2e3, (z0 + z1) / 2e3 - drop_mm / 1e3)   # wheels lowered like the domain
    return out


def vec(s, x, y, z, unit="m"):
    return s.DimensionalVectorLength(value=s.DecimalVector(x=x, y=y, z=z), unit=unit)


def build_spec(s, f, wheels, iters):
    speed = lambda x, y, z: s.DimensionalVectorFunctionSpeed(value=s.ComponentVectorFunction(
        x=s.ConstantFunction(value=x), y=s.ConstantFunction(value=y), z=s.ConstantFunction(value=z)), unit="m/s")
    tr = lambda names: s.TopologicalReference(entities=list(names))
    bcs = [
        s.VelocityInletBC(name="inlet", velocity=s.FixedValueVBC(value=speed(U, 0, 0)), topological_reference=tr(f["inlet"])),
        s.PressureOutletBC(name="outlet", gauge_pressure=s.FixedValuePBC(value=s.DimensionalFunctionPressure(
            value=s.ConstantFunction(value=0), unit="Pa")), topological_reference=tr(f["outlet"])),
        s.SymmetryBC(name="symmetry", topological_reference=tr(f["symmetry"])),
        s.WallBC(name="side and top", velocity=s.SlipVBC(), topological_reference=tr(f["side"] + f["top"])),
        s.WallBC(name="road", velocity=s.MovingWallVBC(value=s.DimensionalVectorSpeed(value=s.DecimalVector(x=U, y=0, z=0),
                                                                                       unit="m/s")),
                 topological_reference=tr(f["ground"])),
        s.WallBC(name="car", velocity=s.NoSlipVBC(), topological_reference=tr(f["car"])),
    ]
    for w in ("wheelF", "wheelR"):
        cx, cy, cz = wheels[w]
        bcs.append(s.WallBC(name=w, velocity=s.RotatingWallVBC(rotation=s.AngularRotation(
            rotation_center=vec(s, cx, cy, cz), rotation_axis=vec(s, 0, 1, 0),
            angular_velocity=s.DimensionalFunctionRotationSpeed(value=s.ConstantFunction(value=OMEGA), unit="rad/s"))),
            topological_reference=tr(f[w])))
    model = s.Incompressible(
        turbulence_model="KOMEGASST",
        model=s.FluidModel(),
        initial_conditions=s.FluidInitialConditions(),
        advanced_concepts=s.AdvancedConcepts(),
        materials=s.IncompressibleFluidMaterials(),
        numerics=s.FluidNumerics(
            relaxation_factor=s.RelaxationFactor(),
            pressure_reference_value=s.DimensionalPressure(value=0, unit="Pa"),
            residual_controls=s.ResidualControls(velocity=s.Tolerance(), pressure=s.Tolerance(),
                                                 turbulent_kinetic_energy=s.Tolerance(), omega_dissipation_rate=s.Tolerance()),
            solvers=s.FluidSolvers(),
            schemes=s.Schemes(time_differentiation=s.TimeDifferentiationSchemes(), gradient=s.GradientSchemes(),
                              divergence=s.DivergenceSchemes(), laplacian=s.LaplacianSchemes(),
                              interpolation=s.InterpolationSchemes(), surface_normal_gradient=s.SurfaceNormalGradientSchemes())),
        boundary_conditions=bcs,
        simulation_control=s.FluidSimulationControl(
            end_time=s.DimensionalTime(value=iters, unit="s"), delta_t=s.DimensionalTime(value=1, unit="s"),
            write_control=s.TimeStepWriteControl(write_interval=iters), max_run_time=s.DimensionalTime(value=20000, unit="s"),
            decompose_algorithm=s.ScotchDecomposeAlgorithm()),
        result_control=s.FluidResultControls(forces_moments=[s.ForcesMomentsResultControl(
            name="Forces and moments", center_of_rotation=vec(s, 0, 0, 0),
            write_control=s.TimeStepWriteControl(write_interval=1),
            topological_reference=tr(f["car"] + f["wheelF"] + f["wheelR"]))]),
    )
    return model


def set_air(s, api, P, sid, volume_entities):
    m = s.MaterialsApi(api)
    groups = m.get_material_groups().embedded
    grp = next(g for g in groups if g.group_type == s.MaterialGroupType.SIMSCALE_DEFAULT)
    mats = m.get_materials(material_group_id=grp.material_group_id).embedded
    air = next(x for x in mats if x.name == "Air")
    data = m.get_material_data(material_group_id=grp.material_group_id, material_id=air.id)
    s.SimulationsApi(api).update_simulation_materials(P, sid, s.MaterialUpdateRequest(operations=[s.MaterialUpdateOperation(
        path="/materials/fluids", material_data=data,
        reference=s.MaterialUpdateOperationReference(material_group_id=grp.material_group_id, material_id=air.id))]))
    spec = s.SimulationsApi(api).get_simulation(P, sid)
    spec.model.materials.fluids[0].topological_reference = s.TopologicalReference(entities=volume_entities)
    s.SimulationsApi(api).update_simulation(P, sid, spec)


SMALL_FEATURE_MM = 0.05                               # faces/edges smaller than this are ignored by the mesher
BOX_M = ((-0.01, 0.0, -0.001), (0.30, 0.05, 0.06))   # refinement box around the car (car frame, m)


def make_box(s, api, P):
    """The refinement box primitive (one per project, reusable by every mesh operation)."""
    (a, b, c), (d, e, f) = BOX_M
    return s.SimulationsApi(api).create_geometry_primitive(P, s.CartesianBox(name="car box", min=vec(s, a, b, c),
                                                                               max=vec(s, d, e, f))).geometry_primitive_id


def mesh_sizing(s, fineness=6, sizing=None):
    """Automatic sizing (fineness 0-10), or manual: {"max_mm": far-field edge, "min_mm": smallest edge,
    "curv": relative curvature or None}. Manual sizing puts a floor under the cell size, so a faceted,
    lumpy pod cannot drive the cell count up the way automatic curvature refinement does."""
    if not sizing:
        return s.AutomaticMeshSizingSimmetrix(fineness=fineness, curvature=s.AutomaticCurvature())
    curv = s.RelativeCurvature(relative_curvature=sizing["curv"]) if sizing.get("curv") else s.AutomaticCurvature()
    return s.ManualMeshSizingSimmetrix(maximum_edge_length=s.DimensionalLength(value=sizing["max_mm"], unit="mm"),
                                       minimum_edge_length=s.DimensionalLength(value=sizing["min_mm"], unit="mm"),
                                       curvature=curv)


def create_case(s, api, P, gid, name, box, f=None, wheels=None, fineness=6, box_mm=1.5, iters=1000, sizing=None,
                sim_id=None):
    """Simulation + mesh operation for one imported air volume. Returns (simulation_id, mesh_operation_id).
    With sim_id, only a new mesh operation is made (mesh studies on an existing simulation)."""
    f = f or faces_by_name(s, api, P, gid)
    missing = [n for n in NAMES if not f[n]] + ([] if f["car"] else ["car"]) + ([] if f["volume"] else ["volume"])
    if missing:
        from simscale_step_eval import GeometryError
        raise GeometryError(f"named faces missing after import: {missing}")
    if sim_id is None:
        wheels = wheels or wheel_centres_m()
        s_api = s.SimulationsApi(api)
        spec = s.SimulationSpec(name=name, geometry_id=gid, model=build_spec(s, f, wheels, iters))
        sid = s_api.create_simulation(P, spec).simulation_id
        set_air(s, api, P, sid, f["volume"])
    else:
        sid = sim_id
    mo = s.MeshOperationsApi(api).create_mesh_operation(P, s.MeshOperation(name=f"{name} mesh", geometry_id=gid, model=s.SimmetrixMeshingFluid(
        sizing=mesh_sizing(s, fineness, sizing),
        refinements=[s.RegionRefinementWithLength(name="car box", refinement=s.InsideRegionRefinementWithLength(
            length=s.DimensionalLength(value=box_mm, unit="mm")),
            topological_reference=s.TopologicalReference(entities=[]), geometry_primitive_uuids=[box])],
        automatic_layer_settings=s.AutomaticLayerOn(), physics_based_meshing=True,
        advanced_simmetrix_settings=s.AdvancedSimmetrixFluidSettings(          # suppress Boolean-seam slivers
            small_feature_tolerance=s.DimensionalLength(value=SMALL_FEATURE_MM, unit="mm")))))
    return sid, mo.mesh_operation_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project"); ap.add_argument("geometry")
    ap.add_argument("--fineness", type=int, default=6)
    ap.add_argument("--box_mm", type=float, default=1.5)
    ap.add_argument("--iters", type=int, default=1000)
    ap.add_argument("--name", default="sidepod template")
    ap.add_argument("--run", action="store_true", help="mesh and run it now")
    a = ap.parse_args()
    import simscale_tool as T
    s, api = T.client()
    P, gid = a.project, a.geometry
    f = faces_by_name(s, api, P, gid)
    print("faces:", {k: len(v) for k, v in f.items()}, flush=True)
    assert all(f[n] for n in NAMES) and f["car"] and f["volume"], "a named face group is missing"
    wheels = wheel_centres_m()
    print("wheel centres (m):", wheels, flush=True)
    box = make_box(s, api, P)
    sid, mo_id = create_case(s, api, P, gid, a.name, box, f, wheels, a.fineness, a.box_mm, a.iters)
    s_api, m_api = s.SimulationsApi(api), s.MeshOperationsApi(api)
    mo = m_api.get_mesh_operation(P, mo_id)
    chk = m_api.check_mesh_operation_setup(P, mo_id, simulation_id=sid)
    print("mesh check:", [(e.severity, getattr(e, "message", "")) for e in (chk.entries or [])], flush=True)
    try:
        print("mesh estimate:", api.sanitize_for_serialization(m_api.estimate_mesh_operation(P, mo_id)), flush=True)
    except Exception as e:
        print("no mesh estimate:", str(e)[:200])
    ids = {"project_id": P, "geometry_id": gid, "template_sim_id": sid, "mesh_template_id": mo_id, "box_primitive": box}
    print(json.dumps(ids), flush=True)
    (HERE / "simscale_ids.json").write_text(json.dumps(ids, indent=1))
    if a.run:
        m_api.start_mesh_operation(P, mo_id, simulation_id=sid)
        t0 = time.time()
        while True:
            st = m_api.get_mesh_operation(P, mo_id)
            print("mesh", st.status, st.progress, round(time.time() - t0), "s", flush=True)
            if st.status in ("FINISHED", "FAILED", "CANCELED"):
                break
            time.sleep(60)
        if st.status != "FINISHED":
            sys.exit("meshing failed")
        sp = s_api.get_simulation(P, sid); sp.mesh_id = st.mesh_id; s_api.update_simulation(P, sid, sp)
        chk = s_api.check_simulation_setup(P, sid)
        print("sim check:", [(e.severity, getattr(e, "message", "")) for e in (chk.entries or [])], flush=True)
        try:
            print("sim estimate:", api.sanitize_for_serialization(s_api.estimate_simulation_setup(P, sid)), flush=True)
        except Exception as e:
            print("no sim estimate:", str(e)[:200])
        r_api = s.SimulationRunsApi(api)
        run = r_api.create_simulation_run(P, sid, s.SimulationRun(name="team car"))
        r_api.start_simulation_run(P, sid, run.run_id)
        print("run started", run.run_id, flush=True)
        ids["run_id"] = run.run_id
        (HERE / "simscale_ids.json").write_text(json.dumps(ids, indent=1))


if __name__ == "__main__":
    main()
