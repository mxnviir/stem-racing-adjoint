"""Verdicts of T1 and TR (SEED_EVOLUTION_PLAN.md, "Real-CFD gates T1 and TR") from a seedevo_gate results folder.

    python seedevo/gate_verdict.py seedevo/results/gate_<run id> [out.json]

T1: per design and meshing frame, production drag = mean of the five 200-iteration block means of the last 1000
iterations; steady drag = mean of the last 404 iterations of the steady continuation. Pooled mesh-to-mesh sigma per
model over designs with >= 2 frames. Mark L/I1: layer coverage >= 50 % of wall faces on every design (from the
snappy log: added layer cells / (nSurfaceLayers x wall faces); nSurfaceLayers read from the case, else 11).
TR: probe drag = mean of the last 404 iterations, SE = sd of four 101-iteration block means / 2;
margin = max(3 hypot(SE_a, SE_b), 0.15 mN).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(sys.argv[1])
DESIGNS = ["original", "channel", "slots", "window"]


def force_col(path):
    rows = [[float(x) for x in re.sub(r"[()]", " ", l).split()] for l in open(path) if l.strip() and not l.startswith("#")]
    return np.array([r[1] for r in rows]) * 1e3          # half-car total drag, mN (Fx of the forces function object)


def last404(D):
    x = D[-404:]
    b = x.reshape(4, 101).mean(1)
    return float(x.mean()), float(b.std(ddof=1) / 2.0)


def prod_blocks(D):
    x = D[-1000:]
    b = x.reshape(5, 200).mean(1)
    return float(b.mean()), float(b.std(ddof=1) / np.sqrt(5)), b.round(3).tolist()


def coverage(snap):
    try:
        txt = open(snap, errors="replace").read()
    except OSError:
        return None
    try:
        sn = int(re.search(r"Snapped mesh : cells:(\d+)", txt).group(1))
        lc = int(re.findall(r"Layer mesh : cells:(\d+)", txt)[-1])
        wf = int(re.search(r"out of (\d+) faces", txt).group(1))
        nl = 11
        m = re.search(r"nSurfaceLayers\s+(\d+)", txt)
        if m:
            nl = int(m.group(1))
        return round(100.0 * min(1.0, (lc - sn) / nl / wf), 1) if lc > sn else 0.0
    except Exception:
        return None


out = {"T1": {}, "TR": {}}
# ---------------------------------------------------------------- T1
t1 = {}
for d in sorted(ROOT.glob("t1/t1-*")):
    for tagdir in d.iterdir():
        if not tagdir.is_dir():
            continue
        tag = tagdir.name
        des, k = tag.rsplit("_k", 1)
        r = {"design": des, "k": int(k)}
        pj = next(iter(tagdir.glob("prodcheck_*.json")), None)
        if pj:
            j = json.loads(pj.read_text())
            r.update(cells=j.get("n_cells"), yplus=(j.get("y_plus_min"), j.get("y_plus_max")), D20_prod=j["D20_half_N"] * 1e3)
        if (tagdir / "forces_prod.dat").exists():
            Dp = force_col(tagdir / "forces_prod.dat")
            r["prod_mN"], r["prod_se"], r["prod_blocks"] = prod_blocks(Dp)
            b4 = Dp[-800:].reshape(4, 200).mean(1)             # reported, not marked: start-up transient (first 200) left out
            r["prod800_mN"], r["prod800_se"] = float(b4.mean()), float(b4.std(ddof=1) / 2)
        if (tagdir / "forces_steady.dat").exists():
            r["steady_mN"], r["steady_se"] = last404(force_col(tagdir / "forces_steady.dat"))
        sb = tagdir / "steady" / "base.json"
        if sb.exists():
            b = json.loads(sb.read_text())
            r["A1_span_mN"], r["A1_pass"] = b["block_span_last1000_mN"], b["steady_pass"]
        r["layer_cov_pct"] = coverage(tagdir / "snappyHexMesh.log")
        t1[tag] = r
out["T1"]["runs"] = t1


def pooled(key):
    ss, dof = 0.0, 0
    per = {}
    for des in DESIGNS:
        v = [r[key] for r in t1.values() if r["design"] == des and key in r]
        per[des] = {"n": len(v), "mean": float(np.mean(v)) if v else None, "sd": float(np.std(v, ddof=1)) if len(v) > 1 else None,
                    "values": [round(x, 3) for x in v]}
        if len(v) > 1:
            ss += float(np.var(v, ddof=1)) * (len(v) - 1); dof += len(v) - 1
    return (np.sqrt(ss / dof) if dof else None), dof, per


for key, name in (("prod_mN", "production"), ("steady_mN", "steady"), ("prod800_mN", "production_200_to_1000_reported")):
    s, dof, per = pooled(key)
    band = None if s is None else ("single runs score" if s <= 1.0 else "duel (section 5)" if s <= 2.5 else "cannot score")
    out["T1"][name] = {"pooled_sigma_mN": s, "dof": dof, "I2": band, "per_design": per}
cov = {t: r.get("layer_cov_pct") for t, r in t1.items()}
out["T1"]["I1_layers_ge_50pct_every_design"] = bool(cov) and all(c is not None and c >= 50 for c in cov.values())
out["T1"]["layer_cov_pct"] = cov

# ---------------------------------------------------------------- TR
TR = {}
for des in DESIGNS:
    m = {}
    for mv in ("zero", "dn", "up", "r101", "r102"):
        f = ROOT / "probe" / f"probe-{des}-{mv}" / "probe" / f"{des}_{mv}" / "forces" / "forces.dat"
        j = ROOT / "probe" / f"probe-{des}-{mv}" / "probe" / f"{des}_{mv}" / f"bump_{des}_{mv}.json"
        if f.exists() and j.exists() and not json.loads(j.read_text()).get("morph_fallback"):
            m[mv] = last404(force_col(f))
    rec = {k: {"D_mN": v[0], "se": v[1]} for k, v in m.items()}

    def margin(a, b):
        return max(3.0 * np.hypot(m[a][1], m[b][1]), 0.15)
    if all(k in m for k in ("zero", "dn", "up")):
        dz, du = m["dn"][0] - m["zero"][0], m["dn"][0] - m["up"][0]
        rec["dn_minus_zero"], rec["dn_minus_up"] = dz, du
        rec["trusted"] = bool(dz <= -margin("dn", "zero") and du <= -margin("dn", "up"))
        rnd = [m[k][0] for k in ("r101", "r102") if k in m]
        rec["dn_below_both_random"] = bool(len(rnd) == 2 and m["dn"][0] < min(rnd))
        for k in ("up", "r101", "r102"):
            if k in m:
                rec[f"{k}_minus_zero"] = m[k][0] - m["zero"][0]
    else:
        rec["trusted"] = None                                  # undetermined: counted as not trusted
    TR[des] = rec
out["TR"]["designs"] = TR
tr1 = TR.get("original", {}).get("trusted") is True
new = [TR.get(d, {}).get("trusted") is True for d in ("channel", "slots", "window")]
trusted = [d for d in DESIGNS if TR.get(d, {}).get("trusted") is True]
out["TR"]["TR1_team_pod_trusted"] = tr1
out["TR"]["TR2_trusted_on_ge2_of_3_new"] = sum(new) >= 2
out["TR"]["TR3_dn_below_both_random_on_half_of_trusted"] = (bool(trusted) and
                                                            sum(TR[d].get("dn_below_both_random", False) for d in trusted) >= len(trusted) / 2)
print(json.dumps(out, indent=1, default=float))
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=float))
