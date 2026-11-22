"""Genes of the layout search: the car's layout, body loft, nose cone and wings as one vector.

Every gene is a number in [0, 1] (CMA works on that cube); `decode` turns a vector into the
parameters Part 1 / Part 4 build from. The three LAYOUT genes are decoded so that every vector
is a legal layout (the analytic limits below); `legal_layouts` lists every legal layout on a
1 mm grid, which is the space the search moves in.

Layout, all mm, x from the nose tip (car frame of Parts 1-5):
  W          wheelbase, front axle -> rear axle                      T7.3: 120.0-140.0
  rear       rear axle -> body rear face                             see REAR_MM
  halo_rear  halo pocket FRONT edge -> body rear face               see halo_rear_range
  x_front    = 16 + nose length (the nose tip is x = 0, Ref A is x_front - 16)

  d_halo (Part 1's halo parameter, Ref A -> pocket front) = W + rear + 16 - halo_rear.
  Halo limits (part1-simulation/geometry_contract.py, project owner 2026-07-24):
    pocket front on or behind the front axle   d_halo >= 16          -> halo_rear <= W + rear
    pocket rear (front + 50) ahead of the rear axle   d_halo < W - 34   -> halo_rear > rear + 50
    pocket rear ahead of the cartridge bore (rear face - 52)  d_halo < W + rear - 86 -> halo_rear > 102
  Rear limits:
    rear <= 56   T9.4.2: nothing more than 40 mm behind Ref B (= rear axle + 16)
    rear >= 36   the rear wing sits on the body just behind Ref B, and T5.6 wants nothing within
                 12.5 mm behind the rear face (the shortest cartridge sticks out 12.5 mm); below
                 ~35 mm the default wing has no body under it (worked out from wings.py / legality.py)
    16 + W + rear <= 223   T1.14: Ref A to the rear face fits the 223 mm block (never binds: 140+56+16=212)
"""
from __future__ import annotations

import numpy as np

W_MM = (120.0, 140.0)
REAR_MM = (36.0, 56.0)
NOSE_LEN_MM = (20.0, 40.0)        # T8.2 <= 40 from Ref A; Part 1's x_front floor of 36 = 16 + 20
BLOCK_MM = 223.0


def halo_rear_range(W, rear):
    """(lo, hi]: legal halo pocket front -> rear face distances for this W and rear."""
    return max(rear + 50.0, 102.0), W + rear


def layout_legal(W, rear, halo_rear) -> bool:
    lo, hi = halo_rear_range(W, rear)
    return (W_MM[0] <= W <= W_MM[1] and REAR_MM[0] <= rear <= REAR_MM[1]
            and lo < halo_rear <= hi and 16.0 + W + rear <= BLOCK_MM)


def legal_layouts(step=1.0):
    """Every legal (W, rear, halo_rear) on a `step` mm grid."""
    out = []
    for W in np.arange(W_MM[0], W_MM[1] + 1e-9, step):
        for r in np.arange(REAR_MM[0], REAR_MM[1] + 1e-9, step):
            lo, hi = halo_rear_range(W, r)
            for h in np.arange(np.floor(lo / step) * step + step, hi + 1e-9, step):
                if layout_legal(W, r, h):
                    out.append((float(W), float(r), float(h)))
    return out


# (name, lo, hi, team/default value) -- the default is where CMA starts (the team-like car)
# body: param_body.BodyParams, eight stations from Ref A (u = 0) to the rear face (u = 1)
STATION_B = [(f"st_b{i}", 6.0, 24.0, v) for i, v in enumerate(
    (10.0, 13.24, 16.53, 18.0, 17.79, 17.15, 15.91, 14.0))]
STATION_ZT = [(f"st_zt{i}", lo, 50.0, v) for i, (lo, v) in enumerate(zip(
    (12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 26.0),
    (20.0, 24.86, 29.80, 32.0, 32.85, 35.41, 40.37, 48.0)))]
STATION_ZB = [(f"st_zb{i}", 3.0, 24.0, v) for i, v in enumerate(
    (6.0, 5.60, 5.18, 5.0, 5.80, 8.20, 12.84, 20.0))]
GENES = (
    [("W", *W_MM, 120.3), ("rear", *REAR_MM, 56.0), ("halo_t", 0.0, 1.0, 0.603)]
    + STATION_B + STATION_ZT + STATION_ZB
    + [("p", 2.0, 4.0, 2.6),
       ("s_b", 14.0, 32.5, 28.0), ("s_zt", 14.0, 27.175, 27.0), ("s_zb", 3.0, 16.0, 12.0),
       ("s_x0u", 0.0, 0.6, 0.3), ("s_lenu", 0.15, 0.8, 0.4), ("s_taper", 2.0, 25.0, 12.0), ("s_p", 2.0, 5.0, 3.0),
       # nose cone (part4 nose.NoseCone)
       ("nose_len", *NOSE_LEN_MM, 30.0), ("nose_k", 0.3, 1.2, 0.5), ("nose_p", 2.0, 4.0, 2.5),
       ("nose_tip_z", 4.0, 20.0, 10.0),
       # front wing (part4 wings.FrontWing), T8.6.2 chord 15-25 incl. the flap
       ("fw_chord", 10.0, 17.0, 15.3), ("fw_aoa", -5.0, 15.0, 6.0), ("fw_z", 4.0, 14.0, 8.0),
       ("fw_half_span", 25.5, 45.0, 38.5), ("fw_flap_chord", 0.0, 8.0, 8.0), ("fw_flap_aoa", 0.0, 40.0, 30.0),
       # rear wing (part4 wings.RearWing)
       ("rw_chord", 15.0, 25.0, 15.3), ("rw_aoa", -5.0, 15.0, 0.0), ("rw_half_span", 25.5, 45.0, 26.0),
       ("rw_x_le", 0.0, 20.0, 3.5)]
)
NAMES = [g[0] for g in GENES]
LO = np.array([g[1] for g in GENES]); HI = np.array([g[2] for g in GENES])
DIM = len(GENES)


def x_default():
    """The start of the search in [0, 1]^DIM: the team-like car (Part 1's default body)."""
    return np.clip((np.array([g[3] for g in GENES]) - LO) / (HI - LO), 0.0, 1.0)


def decode(x) -> dict:
    """[0, 1]^DIM (clipped) -> layout + Part 1 / Part 4 parameters. Always a legal layout."""
    x = np.clip(np.asarray(x, float), 0.0, 1.0)
    v = dict(zip(NAMES, LO + x * (HI - LO)))
    W, rear = round(v["W"], 1), round(v["rear"], 1)
    lo, hi = halo_rear_range(W, rear)
    halo_rear = round(lo + 0.5 + v["halo_t"] * (hi - lo - 0.5), 1)   # strictly above lo
    nose_len = round(v["nose_len"], 1)
    x_front = 16.0 + nose_len
    d_halo = W + rear + 16.0 - halo_rear
    s_x0u = v["s_x0u"]; s_x1u = min(1.0, s_x0u + v["s_lenu"])
    body = dict(
        st_b=tuple(v[f"st_b{i}"] for i in range(8)),
        st_zt=tuple(max(v[f"st_zt{i}"], v[f"st_zb{i}"] + 6.0) for i in range(8)),   # top stays above bottom
        st_zb=tuple(v[f"st_zb{i}"] for i in range(8)),
        p=v["p"], s_b=v["s_b"], s_zt=max(v["s_zt"], v["s_zb"] + 6.0), s_zb=v["s_zb"],
        s_taper=v["s_taper"], s_p=v["s_p"])
    nose = dict(length_mm=nose_len, k=v["nose_k"], p=v["nose_p"], tip_z_mm=v["nose_tip_z"])
    fwing = dict(chord_mm=v["fw_chord"], aoa_deg=v["fw_aoa"], z_chord_mm=v["fw_z"],
                 half_span_mm=v["fw_half_span"], flap_chord_mm=v["fw_flap_chord"], flap_aoa_deg=v["fw_flap_aoa"])
    rwing = dict(chord_mm=v["rw_chord"], aoa_deg=v["rw_aoa"], half_span_mm=v["rw_half_span"],
                 x_le_after_ref_b_mm=v["rw_x_le"])
    return dict(W=W, rear=rear, halo_rear=halo_rear, x_front=x_front, d_halo=round(d_halo, 2),
                s_x0u=s_x0u, s_x1u=s_x1u, body=body, nose=nose, fwing=fwing, rwing=rwing,
                legal_layout=layout_legal(W, rear, halo_rear))


def body_params(d):
    """BodyParams dict for Part 1: the sidepod's x span from its u fractions of Ref A -> rear face."""
    ref_a, rear_face = d["x_front"] - 16.0, d["x_front"] + d["W"] + d["rear"]
    L = rear_face - ref_a
    b = dict(d["body"]); b["s_x0"] = ref_a + d["s_x0u"] * L; b["s_x1"] = ref_a + d["s_x1u"] * L
    return b


if __name__ == "__main__":
    L = legal_layouts(1.0)
    print(f"{DIM} genes; {len(L)} legal layouts on a 1 mm grid "
          f"(W {W_MM}, rear {REAR_MM}); on a 2 mm grid {len(legal_layouts(2.0))}")
    d = decode(x_default()); print({k: d[k] for k in ("W", "rear", "halo_rear", "x_front", "d_halo", "legal_layout")})
    rng = np.random.default_rng(0)
    assert all(decode(rng.random(DIM))["legal_layout"] for _ in range(2000)), "decode left the legal set"
    print("2000 random vectors: all legal layouts")
