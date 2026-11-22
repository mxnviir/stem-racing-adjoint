"""The CMA bookkeeping the sidepod campaign relies on: a generation handed out in batches smaller than
the population, an illegal car told as None, the method pickled between ticks (as campaign.py does),
and the live run's saved state still loading (its class must keep its module and name)."""
import pickle
import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
import repo_paths  # noqa: E402,F401

import numpy as np  # noqa: E402

import methods as MT  # noqa: E402


class Rep:
    def x0(self, s):
        return np.zeros(6)


def f(x):
    return float(((np.asarray(x) - 1.0) ** 2).sum())


def test_cma_batches_pickles_and_illegal():
    m = MT.make("cma", Rep(), "o", np.random.default_rng(0), popsize=8, sigma=0.5)
    gens = 0
    for it in range(120):
        xs = m.ask(3)
        assert xs, "empty ask"
        g0 = m.es.countiter
        m.tell(xs, [None if k == 0 and it % 5 == 0 else f(x) for k, x in enumerate(xs)])
        m = pickle.loads(pickle.dumps(m))
        gens += m.es.countiter > g0
    assert gens >= 30, gens
    assert min(m.Y) < 0.5 * f(np.zeros(6)), min(m.Y)


def test_saved_sidepod_states_load():
    """The CMA states saved by the sidepod run (search/sidepod/results/cma) unpickle with this code."""
    states = sorted((_pl.Path(__file__).resolve().parent / "results" / "cma").glob("*.pkl"))
    assert states, "no saved CMA state in results/cma"
    for p in states:
        m = pickle.loads(p.read_bytes())
        assert isinstance(m, MT.CMA), (p.name, type(m))


if __name__ == "__main__":
    test_cma_batches_pickles_and_illegal()
    test_saved_sidepod_states_load()
    print("test_methods: OK")
