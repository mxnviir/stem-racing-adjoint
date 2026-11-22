"""Mocked SimScale: the evaluator's import -> mesh -> run state machine, restart-safety and force read.

Not a test of SimScale itself (no network to it here): a fake SDK with the same call names and
signatures as simscale_sdk (checked against the SDK source), advancing one status per poll.
    python test_simscale.py
"""
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
import repo_paths  # noqa: E402,F401
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent
import evaluators as EV  # noqa: E402

FORCE_CSV = "time,Total force x,Total force y,Total force z\n" + "\n".join(
    f"{i},{0.2 + (0.1 if i < 70 else 0.0)},0.0,{-0.05}" for i in range(100))


class World:
    """Server state shared by every fake API object."""
    def __init__(self, fail_import_for=()):
        self.n = 0
        self.polls = {}
        self.fail_import_for = set(fail_import_for)
        self.names = {}            # import id -> geometry name
        self.created_sims = []
        self.started_runs = []

    def nid(self, p):
        self.n += 1
        return f"{p}{self.n}"

    def status(self, key, fail=False):
        k = self.polls[key] = self.polls.get(key, 0) + 1
        return "FAILED" if fail and k >= 2 else ("FINISHED" if k >= 2 else "RUNNING")


def fake_sdk(W: World):
    class ApiException(Exception):
        def __init__(self, status):
            self.status = status

    class StorageApi:
        def __init__(self, api): pass
        def create_storage(self): return NS(url="https://up/1", storage_id=W.nid("st"))

    class GeometryImportsApi:
        def __init__(self, api): pass
        def import_geometry(self, project_id, req):
            gi = W.nid("gi"); W.names[gi] = req.name
            return NS(geometry_import_id=gi)
        def get_geometry_import(self, project_id, gi):
            st = W.status(gi, fail=W.names[gi] in W.fail_import_for)
            return NS(status=st, geometry_id=f"g_{gi}", failure_reasons="bad facets")

    class GeometriesApi:
        def __init__(self, api): pass
        def get_geometry_mappings(self, project_id, geometry_id, _class, bodies, page, limit):
            return NS(embedded=[NS(name=f"{geometry_id}:{bodies[0]}:face{i}") for i in range(3)])

    class SimulationsApi:
        def __init__(self, api): pass
        def get_simulation(self, project_id, sid):
            if sid == "TEMPLATE":
                return NS(geometry_id="gT", as_json={"geometryId": "gT", "simulationId": "TEMPLATE",
                          "model": {"bc": [{"name": "wheels", "entities": ["gT:wheelF:face0", "gT:wheelR:face1"]},
                                           {"name": "car", "entities": ["gT:car:face2"]}]}})
            return NS(mesh_id=None, sid=sid)
        def create_simulation(self, project_id, spec):
            W.created_sims.append(spec); return NS(simulation_id=W.nid("sim"))
        def update_simulation(self, project_id, sid, spec): pass
        def check_simulation_setup(self, project_id, sid): return NS(entries=[NS(severity="WARNING")])
        def estimate_simulation_setup(self, project_id, sid): return NS(compute_resource=NS(value=12.0))

    class MeshOperationsApi:
        def __init__(self, api): pass
        def get_mesh_operation(self, project_id, mo):
            if mo == "MESH_T":
                return NS(model={"type": "SIMMETRIX"})
            return NS(status=W.status(mo), mesh_id=f"mesh_{mo}")
        def create_mesh_operation(self, project_id, m):
            assert m.model == {"type": "SIMMETRIX"} and m.geometry_id.startswith("g_")
            return NS(mesh_operation_id=W.nid("mo"))
        def check_mesh_operation_setup(self, project_id, mo, simulation_id): return NS(entries=[])
        def start_mesh_operation(self, project_id, mo, simulation_id): pass

    class SimulationRunsApi:
        def __init__(self, api): pass
        def create_simulation_run(self, project_id, sid, run): return NS(run_id=W.nid("run"))
        def start_simulation_run(self, project_id, sid, rid): W.started_runs.append(rid)
        def get_simulation_run(self, project_id, sid, rid): return NS(status=W.status(rid))
        def get_simulation_run_results(self, project_id, sid, rid, category, name):
            assert category == "FORCE_PLOT"
            return NS(embedded=[NS(download=NS(url="https://res/forces.csv"))])

    def mk(cls_name):
        return lambda **kw: NS(**kw)

    return NS(ApiException=ApiException, StorageApi=StorageApi, GeometryImportsApi=GeometryImportsApi,
              GeometriesApi=GeometriesApi, SimulationsApi=SimulationsApi, MeshOperationsApi=MeshOperationsApi,
              SimulationRunsApi=SimulationRunsApi, GeometryImportRequest=mk("r"), GeometryImportRequestLocation=lambda s: s,
              GeometryImportRequestOptions=mk("o"), MeshOperation=mk("m"), SimulationRun=mk("run"))


class FakeClient:
    configuration = NS(api_key={"X-API-KEY": "test"})

    def __init__(self):
        self.rest_client = NS(PUT=lambda **kw: None, GET=lambda url, headers: NS(data=FORCE_CSV.encode()))

    def sanitize_for_serialization(self, o): return json.loads(json.dumps(o.as_json))
    def _ApiClient__deserialize(self, d, cls): return d


def main():
    car = HERE / "gate" / "original"
    assert (car / "car_half.stl").exists(), "needs gate/original (python gate.py base makes it)"
    W = World(fail_import_for={"bad"})
    with tempfile.TemporaryDirectory() as td:
        st = Path(td) / "inflight.json"
        mk = lambda: EV.SimScaleEvaluator("123", "TEMPLATE", "MESH_T", st, speed_mps=20.0, symmetric_half=True,
                                         max_cost=50.0, sdk=fake_sdk(W), api_client=FakeClient())
        ev = mk()
        ev.submit([{"id": "good", "folder": str(car)}, {"id": "bad", "folder": str(car)}])
        assert set(json.loads(st.read_text())) == {"good", "bad"}
        got = {}
        for tick in range(12):
            ev = mk() if tick == 3 else ev          # a cron restart in the middle of the batch
            got.update(ev.collect())
            if len(got) == 2:
                break
        assert set(got) == {"good", "bad"}, got
        assert not got["bad"]["ok"] and "import FAILED" in got["bad"]["info"]["simscale"]
        g = got["good"]
        assert g["ok"] and abs(g["D20_N"] - 2 * 0.2) < 1e-12 and abs(g["L20_N"] - 2 * -0.05) < 1e-12, g
        assert g["info"]["cost_estimate"] == 12.0
        spec = W.created_sims[0]
        ents = spec["model"]["bc"]
        assert all(e.startswith("g_") for b in ents for e in b["entities"]), ents
        assert {e.split(":")[1] for e in ents[0]["entities"]} == {"wheelF", "wheelR"}
        assert {e.split(":")[1] for e in ents[1]["entities"]} == {"car"}
        assert "simulationId" not in spec
        assert json.loads(st.read_text()) == {}
        # cost guard: an estimate above max_cost never starts a run
        W2 = World()
        ev = EV.SimScaleEvaluator("123", "TEMPLATE", "MESH_T", Path(td) / "i2.json", max_cost=5.0, sdk=fake_sdk(W2),
                                  api_client=FakeClient())
        ev.submit([{"id": "pricey", "folder": str(car)}])
        out = {}
        for _ in range(8):
            out.update(ev.collect())
        assert not out["pricey"]["ok"] and "too expensive" in out["pricey"]["info"]["simscale"] and not W2.started_runs
    print("test_simscale: OK (state machine, restart, remap, force read, cost guard)")


if __name__ == "__main__":
    main()
