"""SimScale screenshot reports of finished runs: surface pressure (iso view) and velocity on cut planes. Usage: python simscale_render.py OUTDIR '{"c00000": [sim_id, run_id]}' (keys from SIMSCALE_API_KEYS)."""
import sys
from pathlib import Path
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
import repo_paths  # noqa: E402,F401
import json, sys, time, importlib
import simscale_step_eval as E
s = importlib.import_module('simscale_sdk')
ev = E.SimScaleStepEvaluator.__new__(E.SimScaleStepEvaluator); ev.sim = s; ev._clients = {}
ev.keys = {E.fingerprint(k): k for k in E.keys_from_env()}; api = ev._api(list(ev.keys)[0])
P = __import__('os').environ.get('RENDER_PROJECT', '669525764013223556')
OUT = sys.argv[1]
cases = json.loads(sys.argv[2])            # {name: [sim_id, run_id]}
V = s.Vector3D
def views():
    car_c = V(0.13, 0.0, 0.02)
    iso = s.UserInputCameraSettings(setting_type="USER_INPUT", projection_type="ORTHOGONAL", up=V(0, 0, 1),
                                    eye=V(0.05, 0.11, 0.09), center=car_c, front_plane_frustum_height=0.17)
    top = s.UserInputCameraSettings(setting_type="USER_INPUT", projection_type="ORTHOGONAL", up=V(0, 1, 0),
                                    eye=V(0.13, 0.05, 0.2), center=V(0.13, 0.05, 0.0), front_plane_frustum_height=0.17)
    side = s.UserInputCameraSettings(setting_type="USER_INPUT", projection_type="ORTHOGONAL", up=V(0, 0, 1),
                                     eye=V(0.13, 0.15, 0.03), center=V(0.13, 0.0, 0.03), front_plane_frustum_height=0.17)
    p = s.ScalarField(field_name="Pressure", data_type="CELL")
    u = s.ScalarField(field_name="Velocity", component="Magnitude", data_type="CELL")
    ps = [s.ScalarSettings(scalar_field=p, minimum_range=-250, maximum_range=250, color_scheme="NORMAL", number_of_divisions=20)]
    us = [s.ScalarSettings(scalar_field=u, minimum_range=0, maximum_range=26, color_scheme="NORMAL", number_of_divisions=26)]
    return {
        "pressure_iso": (iso, s.ModelSettings(parts=[], scalar_field=p, scalar_settings=ps), None),
        "velocity_top_z15mm": (top, s.ModelSettings(parts=[], scalar_field=u, scalar_settings=us, opacity=1.0),
                                s.Filters(cutting_planes=[s.CuttingPlane(name="z15", center=V(0.13, 0.0, 0.015), normal=V(0, 0, 1),
                                          opacity=1.0, clipping=True, scalar_field=u, vector_grid_spacing=0.01)])),
        "velocity_side_y25mm": (side, s.ModelSettings(parts=[], scalar_field=u, scalar_settings=us),
                                s.Filters(cutting_planes=[s.CuttingPlane(name="y20", center=V(0.13, 0.025, 0.02), normal=V(0, 1, 0),
                                          opacity=1.0, clipping=True, scalar_field=u, vector_grid_spacing=0.01)])),
    }
r_api, rep = s.SimulationRunsApi(api), s.ReportsApi(api)
jobs = []
for name, (sid, rid) in cases.items():
    res = [api.sanitize_for_serialization(x) for x in r_api.get_simulation_run_results(P, sid, rid, limit=100, page=1).embedded]
    sol = [d for d in res if d.get("category") == "SOLUTION"]
    if not sol:
        print(name, "no SOLUTION", [d.get("category") for d in res]); continue
    for vname, (cam, model, filt) in views().items():
        props = s.ScreenshotReportProperties(report_type="SCREENSHOT", model_settings=model, filters=filt, camera_settings=cam,
                    output_settings=s.ScreenshotOutputSettings(name="out", format="PNG", resolution=s.ResolutionInfo(x=1600, y=1000),
                                                               show_legend=True, show_cube=False))
        req = s.ReportRequest(name=f"{name} {vname}", description="sidepod render", result_ids=[sol[0]["resultId"]], report_properties=props)
        r = rep.create_report(P, req); rep.start_report_job(P, r.report_id)
        jobs.append((name, vname, r.report_id))
for name, vname, rid in jobs:
    while True:
        r = rep.get_report(P, rid)
        if r.status in ("FINISHED", "FAILED", "CANCELED"): break
        time.sleep(10)
    if r.status != "FINISHED":
        print(name, vname, r.status, api.sanitize_for_serialization(r.failure_reason)); continue
    data = api.rest_client.GET(r.download.url, headers={"X-API-KEY": api.configuration.api_key["X-API-KEY"]}).data
    fn = f"{OUT}/{name}_{vname}.png"; open(fn, "wb").write(data); print("wrote", fn, len(data))
