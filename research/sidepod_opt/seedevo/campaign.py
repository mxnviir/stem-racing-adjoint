"""The seed-evolution campaign as batches of CFD jobs (one batch = one Actions workflow run).

Design record: the field (float16, the region's bounding box, ~0.1-0.3 MB compressed) is the design; a runner
rebuilds the car from it (`build`). Everything the search knows is in <dir>/state.json and <dir>/fields/.

    python -m seedevo.campaign init  <dir> <seed.npz|seed.step ...> [--n-explore 16 --n-control 4 --score steady]
    python -m seedevo.campaign build <dir> <id> <out folder>          # on a runner: field -> legal car folder
    python -m seedevo.campaign ingest <dir> <results folder>          # results of a batch (json per case)
    python -m seedevo.campaign next  <dir>                            # update the map, write the next batch request
    python -m seedevo.campaign show  <dir>

Rules (the bench-tested configuration, SEED_EVOLUTION_PLAN.md amendment B, without morph-scored children, which
the bench showed made no consistent difference):
  * census: every seed scored on frame 0;
  * each batch: n_explore children of map members (parents: tournament of 3; crossover share 0.5; all nine
    operators, each retried until legal), n_control children of census seeds only (test T4), plus the re-runs that
    open duels need;
  * a child that looks better than its niche's holder after one run duels: both brought to 2 runs on shifted
    meshing frames (k x 0.37 mm), the lower mean holds the niche; an empty niche is taken at once;
  * a failed or unconverged run is recorded and gives no score.
The end polish (trust check + adjoint or gradient-free refinement on each finalist's own mesh) is a separate stage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / "part2-simulation"))


# ------------------------------------------------------------------ field storage
def save_field(sp, f, path):
    lo, hi = np.maximum(sp.region_lo - 3, 0), np.minimum(sp.region_hi + 3, f.shape)
    np.savez_compressed(path, f=np.clip(f[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]], -20, 20).astype(np.float32), lo=lo, hi=hi)
    # float32: a float16 field moved surface voxels on reload and one stored child failed the thin-foam rule
    # when a runner rebuilt it (POC batch 1, design 5)


def load_field(sp, path, base):
    z = np.load(path)
    f = base.copy()
    lo, hi = z["lo"], z["hi"]
    f[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] = z["f"].astype(np.float64)
    return f


class Store:
    def __init__(self, d, space):
        self.d, self.sp = Path(d), space
        (self.d / "fields").mkdir(parents=True, exist_ok=True)
        self.st = json.loads((self.d / "state.json").read_text()) if (self.d / "state.json").exists() else None
        if self.st:
            compute_offsets(self.st, self.st.get("score", "steady"))
        if not hasattr(space, "region_lo"):
            w = np.argwhere(space.region)
            space.region_lo, space.region_hi = w.min(0), w.max(0) + 1
        self._base = None

    @property
    def base(self):                                       # outside the box every design equals the census's first seed
        if self._base is None:
            self._base = np.load(self.d / "base_field.npz")["f"].astype(np.float64)
        return self._base

    def field(self, i):
        return load_field(self.sp, self.d / "fields" / f"d{int(i):04d}.npz", self.base)

    def save(self):
        (self.d / "state.json").write_text(json.dumps(self.st, indent=1, default=float))


SETUP = None          # the campaign's current CFD setup (set by Store); runs of another setup need an offset
OFFSETS = {}          # setup json -> mN added to bring it to the current setup (from the reference design)


def setup_id(su):
    return json.dumps(su or {}, sort_keys=True)


def mean_score(rec, key):
    """Mean of the design's converged runs on the current setup; runs of another setup count only when the reference
    design brought that setup over (the evolution branch's timed_rows): value + offset."""
    v = []
    for r in rec["runs"]:
        if r.get(key) is None or not r.get("converged", True):
            continue
        sid = setup_id(r.get("setup"))
        if SETUP is None or r.get("setup") is None or sid == SETUP:
            v.append(r[key])
        elif sid in OFFSETS:
            v.append(r[key] + OFFSETS[sid])
    return (float(np.mean(v)), len(v)) if v else (np.inf, 0)


def compute_offsets(st, key):
    """Offsets from the reference design (the census's first seed) timed on both setups."""
    global SETUP, OFFSETS
    SETUP = setup_id(st.get("setup")) if st.get("setup") else None
    OFFSETS = {}
    ref = st["designs"].get(str(st.get("reference", st["seeds"][0])))
    if ref is None or SETUP is None:
        return OFFSETS
    by = {}
    for r in ref["runs"]:
        if r.get(key) is not None and r.get("converged", True):
            by.setdefault(setup_id(r.get("setup")), []).append(r[key])
    if SETUP in by:
        for sid, v in by.items():
            if sid != SETUP:
                OFFSETS[sid] = float(np.mean(by[SETUP]) - np.mean(v))
    return OFFSETS


# ------------------------------------------------------------------ commands
def cmd_init(st_dir, seeds, space, n_explore=16, n_control=4, score="steady", rng_seed=1, max_gen=None):
    S = Store(st_dir, space)
    designs, fields, hashes = {}, {}, []
    for i, (name, f) in enumerate(seeds.items()):
        b = space.build(f)
        if not b["ok"]:
            print(f"seed {name}: illegal after the rules, skipped ({b.get('info', {}).get('check')})"); continue
        if not fields:
            np.savez_compressed(S.d / "base_field.npz", f=b["f"].astype(np.float32))
            S._base = b["f"].astype(np.float64)
        save_field(space, b["f"], S.d / "fields" / f"d{i:04d}.npz")
        desc = space.describe(b["B"])
        designs[str(i)] = {"name": name, "kind": "seed", "op": "", "parents": [], "desc": list(desc),
                           "niche": list(space.niche(desc)), "runs": [], "gen": 0, "changed_mm3": b["changed_mm3"]}
        fields[i] = b["f"]
        hashes.append(shape_hash(b["B"]))
    S.st = {"gen": 0, "hashes": sorted(set(hashes)), "next_id": max(int(k) for k in designs) + 1, "designs": designs, "archive": {}, "duels": [],
            "seeds": [k for k in designs], "score": score, "n_explore": n_explore, "n_control": n_control,
            "rng": rng_seed, "batches": [], "max_gen": max_gen}
    req = {"gen": 0, "cases": [{"id": int(k), "k": 0} for k in designs]}
    S.st["batches"].append(req); S.save()
    (S.d / "request.json").write_text(json.dumps(req, indent=1))
    print(json.dumps({"seeds": len(designs), "request": len(req["cases"])}))
    return S


def cmd_ingest(st_dir, space, results):
    """results: list of {"id", "k", "steady", "prod", "converged", ...} (mN, half car); or a folder of *.json."""
    S = Store(st_dir, space)
    if isinstance(results, (str, Path)):
        results = [json.loads(p.read_text()) for p in sorted(Path(results).rglob("case_*.json"))]
    n = 0
    for r in results:
        d = S.st["designs"].get(str(r["id"]))
        if d is None or any(x["k"] == r["k"] for x in d["runs"]):
            continue
        if r.get("converged") and r.get(S.st["score"]) is None:
            raise SystemExit(f"case {r['id']} k{r['k']} (mode {r.get('mode')}) has no '{S.st['score']}' drag, the score this "
                             f"campaign ranks on: run the batch in mode {S.st['score']}")
        d["runs"].append({k: r.get(k) for k in ("k", "steady", "prod", "converged", "layer_cov_pct", "error", "setup")})
        if r.get("setup") and not S.st.get("setup"):
            S.st["setup"] = r["setup"]                     # the first result fixes the campaign's setup
        n += 1
    S.save()
    print(json.dumps({"ingested": n}))
    return S


def _update_map(S):
    st, key = S.st, S.st["score"]
    D = st["designs"]
    log = []
    for c in list(st["duels"]):                            # open duels whose re-runs are in
        ch, inc = D[c["child"]], D[c["inc"]]
        (mc, nc), (mi, ni) = mean_score(ch, key), mean_score(inc, key)
        if nc >= 2 and ni >= 2 or not np.isfinite(mc):
            st["duels"].remove(c)
            nk = ",".join(map(str, ch["niche"]))
            if np.isfinite(mc) and mc < mi and st["archive"].get(nk) == c["inc"]:
                st["archive"][nk] = c["child"]; log.append(("replaced", c["child"], c["inc"], mc, mi))
            else:
                log.append(("rejected", c["child"], c["inc"], mc, mi))
    busy = {c["child"] for c in st["duels"]} | {c["inc"] for c in st["duels"]}
    for i, d in D.items():                                 # newly scored designs try for their niche
        if d.get("placed") or d["kind"] == "control" or not d["runs"]:
            continue
        m, n = mean_score(d, key)
        d["placed"] = True
        if not np.isfinite(m):
            continue
        nk = ",".join(map(str, d["niche"]))
        inc = st["archive"].get(nk)
        if inc is None:
            st["archive"][nk] = i; log.append(("new", i, None, m, None))
        elif inc in busy or i in busy:
            continue
        else:
            mi, ni = mean_score(D[inc], key)
            if m < mi:
                st["duels"].append({"child": i, "inc": inc}); busy |= {i, inc}; log.append(("duel", i, inc, m, mi))
    return log


_WSP = None


def shape_hash(B):
    import hashlib
    return hashlib.sha1(np.packbits(np.asarray(B, bool)).tobytes()).hexdigest()[:16]


def _winit():
    global _WSP
    from .space import RealSpace
    _WSP = RealSpace()


def _wbuild(f):
    b = _WSP.build(f)
    return {"ok": b["ok"], "f": b["f"].astype(np.float32), "B": np.packbits(b["B"]), "changed_mm3": b["changed_mm3"]}


def cmd_next(st_dir, space, n_explore=None, n_control=None, workers=1):
    from . import operators as OP
    S = Store(st_dir, space)
    st = S.st
    compute_offsets(st, st["score"])
    log = _update_map(S)
    if st.get("max_gen") is not None and st["gen"] >= st["max_gen"]:
        S.save(); (S.d / "STOP").write_text(f"max_gen {st['max_gen']} reached\n")
        print(json.dumps({"stopped": True, "gen": st["gen"], "max_gen": st["max_gen"], "niches": len(st["archive"]), "log": log}, default=str))
        return S
    rng = np.random.default_rng(st["rng"] * 1000 + st["gen"] + 1)
    key = st["score"]
    D = st["designs"]
    cases = []
    for c in st["duels"]:                                  # re-runs the duels need
        for i in (c["child"], c["inc"]):
            if mean_score(D[i], key)[1] < 2 and not any(x["id"] == int(i) for x in cases):
                cases.append({"id": int(i), "k": len(D[i]["runs"])})
    elites = [i for i in st["archive"].values()]
    seeds = [i for i in st["seeds"] if mean_score(D[i], key)[1] > 0]

    # every_seed_once: in the first bred batch each scored seed is the first parent of at least one explore child
    # (with many seeds in few niches the archive would otherwise keep only one seed per niche as a parent)
    first = []
    if st.get("every_seed_once") and st["gen"] == 0:
        first = [i for i in seeds]; rng.shuffle(first)

    def pick(pool):
        idx = rng.choice(len(pool), min(3, len(pool)), replace=False)
        return min((pool[j] for j in idx), key=lambda i: mean_score(D[i], key)[0])

    made = 0
    seen = set(st.get("hashes", []))
    pool_exec = None
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        pool_exec = ProcessPoolExecutor(workers, initializer=_winit)
    shape = space.region.shape

    def build_many(fields):
        if pool_exec is None:
            out = []
            for f in fields:
                b = space.build(f); out.append({"ok": b["ok"], "f": b["f"], "B": b["B"], "changed_mm3": b["changed_mm3"]})
            return out
        res = list(pool_exec.map(_wbuild, fields))
        for r in res:
            r["B"] = np.unpackbits(r["B"])[: int(np.prod(shape))].reshape(shape).astype(bool)
            r["f"] = r["f"].astype(np.float64)
        return res

    def propose(pool, tour):
        a = pick(pool) if tour else pool[rng.integers(len(pool))]
        others = [p for p in pool if D[p]["niche"] != D[a]["niche"]] or [p for p in pool if p != a]
        use_x = bool(others) and rng.random() < 0.5
        name = str(rng.choice([o for o in OP.OPS if (o in OP.CROSSOVER) == use_x]))
        b = (pick(others) if tour else others[rng.integers(len(others))]) if use_x else None
        f, meta = OP.OPS[name](space, rng, S.field(a), S.field(b) if b is not None else None, None)
        return None if "skip" in meta else (a, b, name, meta, f)

    screen_info = None
    scored = [i for i in D if np.isfinite(mean_score(D[i], key)[0])]
    for kind, n, pool, tour in (("explore", n_explore or st["n_explore"], elites, True),
                                ("control", n_control or st["n_control"], seeds, False)):
        got, tries = 0, 0
        ranked = None
        if kind == "explore" and st.get("screen", True) and len(scored) >= st.get("screen_min", 12) and n > 0 and not first:
            # model-screened batch (test TS): a pool of screen_pool x n unbuilt candidates, ranked by expected
            # improvement with the kriging believer on a GP of every scored design; built in rank order
            from .screen import Screen, block_occupancy
            cands = [c for c in (propose(pool, tour) for _ in range(st.get("screen_pool", 4) * n)) if c is not None]
            if cands:
                vol = lambda f: float(((f > 0) & space.region).sum()) * space.h ** 3 / 1e3
                Fs = [S.field(i) for i in scored]
                Bs = np.array([block_occupancy(space, f) for f in Fs]); Bc = np.array([block_occupancy(space, c[4]) for c in cands])
                sc = Screen(seed=int(rng.integers(1 << 30)))
                sc.fit_basis(np.vstack([Bs, Bc]))
                order = sc.pick(sc.feats(Bs, np.array([[vol(f)] for f in Fs])), np.array([mean_score(D[i], key)[0] for i in scored]),
                                sc.feats(Bc, np.array([[vol(c[4])] for c in cands])), min(len(cands), 2 * n))
                ranked = [cands[k] for k in order]
                screen_info = {"pool": len(cands), "ranked": len(ranked), "model_noise": sc.last["noise"]}
        while got < n and tries < 8 * n:
            if ranked is not None and not ranked:
                ranked = None                              # the ranked pool is used up: breed the rest unscreened
            props = []
            for _ in range(max(1, min(workers, n - got)) if pool_exec else 1):
                if ranked is not None:
                    if ranked:
                        props.append(ranked.pop(0))
                    tries += 1
                    continue
                a = first.pop() if (tour and first) else pick(pool) if tour else pool[rng.integers(len(pool))]
                others = [p for p in pool if D[p]["niche"] != D[a]["niche"]] or [p for p in pool if p != a]
                use_x = bool(others) and rng.random() < 0.5
                name = str(rng.choice([o for o in OP.OPS if (o in OP.CROSSOVER) == use_x]))
                b = (pick(others) if tour else others[rng.integers(len(others))]) if use_x else None
                f, meta = OP.OPS[name](space, rng, S.field(a), S.field(b) if b is not None else None, None)
                tries += 1
                if "skip" not in meta:
                    props.append((a, b, name, meta, f))
            if not props:
                continue
            built = build_many([p[4] for p in props])
            for (a, b, name, meta, f), bl in zip(props, built):
                if got >= n or not bl["ok"]:
                    continue
                h = shape_hash(bl["B"])
                if h in seen:                              # a copy of a parent or of any design already made: no CFD
                    continue
                fp = S.d / "fields" / f"d{int(st['next_id']):04d}.npz"
                save_field(space, bl["f"], fp)
                rb = space.build(load_field(space, fp, S.base))      # what the runner will build from storage
                if not rb["ok"]:
                    fp.unlink(); continue
                h = shape_hash(rb["B"])                            # the build is not bit-idempotent: keep what the runner gets
                if h in seen:
                    fp.unlink(); continue
                bl["B"] = rb["B"]
                seen.add(h)
                i = str(st["next_id"]); st["next_id"] += 1
                desc = space.describe(bl["B"])
                D[i] = {"name": f"g{st['gen'] + 1}_{kind}_{i}", "kind": kind, "op": name,
                        "parents": [a] + ([b] if b is not None else []), "desc": list(desc), "niche": list(space.niche(desc)),
                        "runs": [], "gen": st["gen"] + 1, "changed_mm3": bl["changed_mm3"],
                        "meta": {k: v for k, v in meta.items() if isinstance(v, (int, float, str, bool))}}
                cases.append({"id": int(i), "k": 0}); made += 1; got += 1
    if pool_exec is not None:
        pool_exec.shutdown()
    st["hashes"] = sorted(seen)
    if screen_info:
        st.setdefault("screen_log", []).append(dict(screen_info, gen=st["gen"] + 1))
    st["gen"] += 1
    req = {"gen": st["gen"], "cases": cases}
    st["batches"].append({"gen": st["gen"], "n": len(cases), "log": log})
    S.save()
    (S.d / "request.json").write_text(json.dumps(req, indent=1))
    print(json.dumps({"gen": st["gen"], "cases": len(cases), "new_children": made, "duels_open": len(st["duels"]),
                      "niches": len(st["archive"]), "log": [list(map(str, x[:3])) for x in log]}))
    return req


def cmd_build(st_dir, space, i, out):
    """On a runner: the design's field -> its legal car folder (the same builder as everywhere)."""
    import shape_loop as SL
    S = Store(st_dir, space)
    b = SL.build_design(space.car, S.field(i))
    if not b["check"]["ok"]:
        raise SystemExit(f"design {i} is not legal on this machine: {b['check']}")
    SL.export_design(space.car, b, Path(out), f"d{int(i):04d}")
    print(json.dumps({"id": int(i), "pod_cm3": float((b["voxels"] & space.car.region).sum() * 1e-3), "mass": b["mass"]}, default=float))


def cmd_show(st_dir, space):
    S = Store(st_dir, space)
    st, key = S.st, S.st["score"]
    print(f"generation {st['gen']}, designs {len(st['designs'])}, niches {len(st['archive'])}, open duels {len(st['duels'])}")
    for nk, i in sorted(st["archive"].items(), key=lambda kv: mean_score(st["designs"][kv[1]], key)[0]):
        d = st["designs"][i]; m, n = mean_score(d, key)
        print(f"  niche {nk:6s} d{int(i):04d} {d['kind']:8s} {d['op']:8s} {key} {m:9.3f} mN ({n} runs)  pod {d['desc'][0]:.1f} cm3, openings {d['desc'][1]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd"); ap.add_argument("dir"); ap.add_argument("args", nargs="*")
    ap.add_argument("--n-explore", type=int, default=16); ap.add_argument("--n-control", type=int, default=4)
    ap.add_argument("--score", default="steady"); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-gen", type=int, default=None)
    a = ap.parse_args()
    from .space import RealSpace
    sp = RealSpace()
    if a.cmd == "init":
        from . import ingest
        seeds = {}
        for p in a.args:
            p = Path(p)
            if p.suffix == ".npz":
                seeds[p.stem] = np.load(p)["f"].astype(np.float64)
            else:
                seeds[p.stem] = ingest.field_from_step(sp.car, p)[0]
        cmd_init(a.dir, seeds, sp, a.n_explore, a.n_control, a.score, max_gen=a.max_gen)
    elif a.cmd == "build":
        cmd_build(a.dir, sp, a.args[0], a.args[1])
    elif a.cmd == "ingest":
        cmd_ingest(a.dir, sp, Path(a.args[0]))
    elif a.cmd == "next":
        cmd_next(a.dir, sp, workers=a.workers)
    elif a.cmd == "show":
        cmd_show(a.dir, sp)


if __name__ == "__main__":
    sys.exit(main())
