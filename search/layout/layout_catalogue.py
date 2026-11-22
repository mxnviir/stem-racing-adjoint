"""Every parameter of the whole-car builder, for the layout search -- written to layout_params.json.

layout_params.json is the file the search reads (layout_genes.py) and the file to edit: each entry
has a `mode`, "evolve" (a CMA gene between lo and hi) or "fixed" (held at `value`). This script
makes the first version (my recommendation, 2026-11-22) and docs/PARAMETERS.md from it; once the
JSON exists, edit the JSON and run `python layout_catalogue.py --md` to refresh the table only.

    python layout_catalogue.py            # write layout_params.json (refuses to overwrite) + the .md
    python layout_catalogue.py --md       # the .md from the existing JSON
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
import repo_paths  # noqa: E402,F401
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JSON = HERE / "layout_params.json"
MD = HERE.parents[1] / "docs" / "PARAMETERS.md"

E, F = "evolve", "fixed"
U = (0.0, 0.08, 0.2, 0.35, 0.5, 0.65, 0.82, 1.0)          # param_body.STATIONS_U


def P(group, name, value, lo, hi, mode, unit, what, rule="", why=""):
    return dict(group=group, name=name, value=value, lo=lo, hi=hi, mode=mode, unit=unit, what=what, rule=rule, why=why)


def catalogue():
    c = []
    # ---- layout
    c += [
        P("layout", "W", 120.3, 120.0, 140.0, E, "mm", "wheelbase, front axle -> rear axle", "T7.3 120.0-140.0",
          "the main layout lever: drag, mass, and where the thrust and COM sit against the axles"),
        P("layout", "rear", 56.0, 36.0, 56.0, E, "mm", "rear axle -> body rear face (the cartridge bore moves with it)",
          "T9.4.2 <= 40 behind Ref B (= 56); below ~35 the rear wing has no body under it (T5.6 keeps 12.5 mm "
          "behind the face clear)", "shorter tail: less foam and wetted area, thrust point moves forward"),
        P("layout", "halo_rear", 148.6, 102.0, 196.0, E, "mm",
          "halo pocket FRONT edge -> body rear face (pocket 50 mm long)",
          "pocket front on/behind the front axle; pocket rear ahead of the rear axle and of the 52 mm bore "
          "(the decoder keeps it inside these for each W and rear)", "moves the halo, the 25 g halo + ballast container, and the loft's peak"),
    ]
    # ---- cargo (T4.2): 60 long, 10 high, 55 -> 10 wide, top at 24 (under the halo), between the axle lines
    c += [
        P("cargo", "cargo_x", 0.5, 0.0, 1.0, E, "0-1",
          "virtual cargo front -> back: 0 = its front on the front axle line, 1 = its back on the rear axle line",
          "T4.2 wholly between the axle lines; may share the ballast container, not the halo pocket (z 14-24 vs 24+: never overlaps)",
          "where the body must keep 55 mm of width at z 14-24: shapes the sidepods' minimum"),
        P("cargo", "cargo_flip", 0.0, 0.0, 1.0, E, "0/1",
          "orientation: below 0.5 wide (55 mm) end forward, above 0.5 wide end rearward", "T4.2 either way",
          "the wide end sets where the body is widest"),
    ]
    # ---- body loft (Part 1 param_body): superellipse sections at 8 stations Ref A (u=0) -> rear face (u=1)
    b0 = (10.0, 13.24, 16.53, 18.0, 17.79, 17.15, 15.91, 14.0)
    zt0 = (20.0, 24.86, 29.80, 32.0, 32.85, 35.41, 40.37, 48.0)
    zb0 = (6.0, 5.60, 5.18, 5.0, 5.80, 8.20, 12.84, 20.0)
    for i, u in enumerate(U):
        c.append(P("body loft", f"st_b{i}", b0[i], 6.0, 24.0, E, "mm", f"half-width at u = {u}",
                   "T8.5.1 <= 15 half-width ahead of Ref A (the nose); T3.4 car width; the block 65 wide",
                   "fuselage plan shape"))
    for i, u in enumerate(U):
        lo = (12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 26.0)[i]
        c.append(P("body loft", f"st_zt{i}", zt0[i], lo, 50.0, E, "mm", f"top height at u = {u}",
                   "T3.5 <= 65; the halo pocket floor (24) and the chamber wall (axis 31 + 9.25 + 3) are forced solid by Part 1 anyway",
                   "the halo-canister loft's top line"))
    for i, u in enumerate(U):
        c.append(P("body loft", f"st_zb{i}", zb0[i], 3.0, 24.0, E, "mm", f"bottom height at u = {u}",
                   "T3.7 >= 1.5 above the track; the 6 mm block slot", "underside rake / floor height"))
    c += [
        P("body loft", "p", 2.6, 2.0, 4.0, F, "-", "section squareness (2 ellipse, larger boxier), all stations", "",
          "one number for every section: fix unless the loft looks wrong"),
        P("body loft", "blend_mm", 3.0, 1.0, 6.0, F, "mm", "fillet where fuselage meets sidepods", "3.175 ball cutter",
          "manufacturing detail"),
    ]
    # ---- sidepods
    c += [
        P("sidepods", "s_b", 28.0, 14.0, 32.5, E, "mm", "sidepod half-width", "T3.4 width; the block 65 wide", ""),
        P("sidepods", "s_zt", 27.0, 14.0, 27.175, E, "mm", "sidepod top", "team: nothing above 27.175 in the sidepods", ""),
        P("sidepods", "s_zb", 12.0, 3.0, 16.0, E, "mm", "sidepod bottom", "T3.7 >= 1.5", ""),
        P("sidepods", "s_x0u", 0.3, 0.0, 0.6, E, "0-1", "sidepod start, as a fraction of Ref A -> rear face", "", ""),
        P("sidepods", "s_lenu", 0.4, 0.15, 0.8, E, "0-1", "sidepod length, same fraction", "", ""),
        P("sidepods", "s_taper", 12.0, 2.0, 25.0, F, "mm", "ease-in/out length at each end", "", "shape detail"),
        P("sidepods", "s_p", 3.0, 2.0, 5.0, F, "-", "sidepod section squareness", "", "shape detail"),
    ]
    # ---- underfloor tunnel (off by default)
    c += [
        P("underfloor tunnel", "ft_h", 0.0, 0.0, 8.0, F, "mm", "tunnel height (0 = no tunnel)", "T3.7; the 6 mm block slot",
          "off: Part 2's adjoint never found it worth it; try later as one evolve gene"),
        P("underfloor tunnel", "ft_w", 8.0, 3.0, 15.0, F, "mm", "tunnel half-width", "", ""),
        P("underfloor tunnel", "ft_x0", 50.0, 40.0, 120.0, F, "mm", "tunnel inlet x", "", ""),
        P("underfloor tunnel", "ft_x1", 170.0, 120.0, 230.0, F, "mm", "tunnel outlet x", "", ""),
        P("underfloor tunnel", "ft_ramp", 25.0, 5.0, 40.0, F, "mm", "ramp length at each end", "", ""),
    ]
    # ---- sculpt modes: smooth bumps/dents (mm), 32 on the fuselage, 24 on the sidepods
    for i in range(32):
        c.append(P("sculpt modes (fuselage)", f"mode{i}", 0.0, -4.0, 4.0, F, "mm",
                   f"bump/dent at u = {(0.06, 0.18, 0.3, 0.42, 0.54, 0.66, 0.78, 0.9)[i // 4]}, "
                   f"{(15, 60, 120, 165)[i % 4]} deg from the top", "", "56 local tweaks: too many for ~110 runs; a fine-tuning stage later"))
    for i in range(24):
        c.append(P("sculpt modes (sidepods)", f"mode{32 + i}", 0.0, -4.0, 4.0, F, "mm",
                   f"bump/dent at sidepod u = {(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)[i // 4]}, {(20, 60, 100, 150)[i % 4]} deg from the top",
                   "", "as above"))
    c += [P("body mass", "skin_mm", 0.0, -1.0, 1.0, F, "mm",
            "uniform skin offset of the drawn body (0 = as drawn); lead fills the car to 48.2 g",
            "T3.6 >= 48.0 g; T1.22 lead only in the container under the halo", "the shape genes already set the foam")]
    # ---- nose cone (Part 4 nose.NoseCone), printed ABS ahead of Ref A
    c += [
        P("nose", "nose_len", 30.0, 20.0, 40.0, E, "mm", "nose tip ahead of Ref A (sets x_front = 16 + this)",
          "T8.2 <= 40 (whole nose assembly)", ""),
        P("nose", "nose_k", 0.5, 0.3, 1.2, E, "-", "section growth along the nose (0.5 elliptic, 1 conical)", "T8.5.1", ""),
        P("nose", "nose_p", 2.5, 2.0, 4.0, F, "-", "nose section squareness", "T8.5.1 half-width <= 15", "shape detail"),
        P("nose", "nose_tip_z", 10.0, 4.0, 20.0, E, "mm", "tip height above the track", "T8.5.1 <= 25; T3.7", ""),
        P("nose", "nose_blend", 1.0, 0.5, 10.0, F, "mm", "root station behind Ref A where it takes the body's section", "", "run_car's choice"),
        P("nose", "nose_root_scale", 1.0, 0.9, 1.0, F, "-", "root section vs the body's", "", ""),
        P("nose", "nose_wall", 1.0, 0.8, 2.0, F, "mm", "printed shell wall", "print minimum", "mass only"),
    ]
    # ---- front wing (Part 4 wings.FrontWing)
    c += [
        P("front wing", "fw_chord", 15.3, 10.0, 17.0, E, "mm", "main element chord", "T8.6.2 15-25 total incl. flap", ""),
        P("front wing", "fw_t_frac", 0.15, 0.13, 0.4, F, "-", "thickness / chord", "T8.6.3 2-6 mm", ""),
        P("front wing", "fw_camber", 0.0, 0.0, 0.08, F, "-", "camber", "", "try later"),
        P("front wing", "fw_aoa", 6.0, -5.0, 15.0, E, "deg", "angle of attack", "T8.5.2 <= 20 high outboard", ""),
        P("front wing", "fw_half_span", 38.5, 25.5, 45.0, E, "mm", "half span", "T8.6.1 >= 50 (or 2 x 25 if split)", ""),
        P("front wing", "fw_z", 8.0, 4.0, 14.0, E, "mm", "chord line height", "T8.7 5 mm clear air to the track; T8.5.2", ""),
        P("front wing", "fw_gap_to_wheel", 5.5, 5.0, 12.0, F, "mm", "gap ahead of the front wheel", "T7.9.1, T8.7", ""),
        P("front wing", "fw_endplate_h", 0.0, 0.0, 15.0, F, "mm", "end plate height (0 = none)", "T8.5.3", "off for now"),
        P("front wing", "fw_endplate_w", 2.0, 1.0, 10.0, F, "mm", "end plate width", "T8.5.3 <= 10", ""),
        P("front wing", "fw_mount_t", 3.0, 2.0, 6.0, F, "mm", "mount thickness", "", "structure"),
        P("front wing", "fw_flap_chord", 8.0, 0.0, 8.0, E, "mm", "flap chord (0 = single element)", "T8.6.2, up to 3 elements", ""),
        P("front wing", "fw_flap_t_frac", 0.29, 0.25, 0.6, F, "-", "flap thickness / chord", "T8.6.3", ""),
        P("front wing", "fw_flap_aoa", 30.0, 0.0, 40.0, E, "deg", "flap angle", "T8.5.2", ""),
        P("front wing", "fw_flap_overlap", 1.0, 0.0, 3.0, F, "mm", "flap overlap", "T8.6.2 elements overlap", ""),
        P("front wing", "fw_flap_gap", 0.5, 0.3, 2.0, F, "mm", "slot gap", "", ""),
    ]
    # ---- rear wing (Part 4 wings.RearWing)
    c += [
        P("rear wing", "rw_chord", 15.3, 15.0, 25.0, E, "mm", "chord", "T9.5.2 15-25", ""),
        P("rear wing", "rw_t_frac", 0.15, 0.13, 0.4, F, "-", "thickness / chord", "T9.5.3 2-6 mm", ""),
        P("rear wing", "rw_camber", 0.0, 0.0, 0.08, F, "-", "camber", "", "try later"),
        P("rear wing", "rw_aoa", 0.0, -5.0, 15.0, E, "deg", "angle of attack", "T9.4.3, T9.6", ""),
        P("rear wing", "rw_half_span", 26.0, 25.5, 45.0, E, "mm", "half span", "T9.5.1 >= 50", ""),
        P("rear wing", "rw_x_le", 3.5, 0.0, 20.0, E, "mm", "leading edge behind Ref B", "T9.4.1 behind Ref B, T9.4.2 <= 40", ""),
        P("rear wing", "rw_clear_air_margin", 0.5, 0.2, 2.0, F, "mm", "margin over the 5 mm clear air", "T9.6", ""),
        P("rear wing", "rw_pylon_t", 2.0, 1.5, 4.0, F, "mm", "pylon thickness", "", "structure"),
        P("rear wing", "rw_pylon_chord", 10.0, 6.0, 20.0, F, "mm", "pylon chord", "", "structure"),
    ]
    # ---- tether guides (T6)
    c += [
        P("tether guides", "tether_front", 5.0, 0.0, 10.0, F, "mm", "front guide ahead of the front axle", "T6.1 within 10",
          "aero-tiny; affects the guide-friction lever only"),
        P("tether guides", "tether_rear", 5.0, 0.0, 10.0, F, "mm", "rear guide behind the rear axle", "T6.1 within 10", ""),
    ]
    # ---- fixed by the build (listed so nothing is hidden)
    c += [
        P("fixed by the build", "chamber_z", 31.0, 30.0, 40.0, F, "mm", "cartridge axis height = thrust line",
          "T5.2 30-40", "a Part 1 constant (CHAMBER_AXIS_Z_MM): making it a gene needs a Part 1 change; ask if wanted"),
        P("fixed by the build", "wheels", "team_stl", None, None, F, "", "the team's measured wheels (front 13.25, rear 17.25 wide)",
          "T7.4, T7.5", "printed parts you already have"),
        P("fixed by the build", "wheel_inner_y", "Part 1", None, None, F, "mm", "wheel track (inner faces)", "T7.2 gaps >= 38 / 30, T3.4",
          "a Part 1 constant used by every mask"),
        P("fixed by the build", "supports", "none", None, None, F, "", "wheel supports", "T7.12", "user: added later"),
    ]
    return c


def write_md(params):
    groups = {}
    for p in params:
        groups.setdefault(p["group"], []).append(p)
    n_e = sum(p["mode"] == E for p in params)
    lines = ["# Layout search: every parameter of the car", "",
             f"{len(params)} parameters, {n_e} evolved, {len(params) - n_e} fixed. The search reads "
             "`layout_params.json`; change a `mode` there (`evolve` / `fixed`), a `value` (used when fixed, "
             "and the start when evolved) or a range, then run `python layout_catalogue.py --md`.", "",
             "x is measured from the nose tip, z from the track, mm. Ref A = front axle - 16, Ref B = rear axle + 16.", ""]
    for g, ps in groups.items():
        lines += [f"## {g} ({sum(p['mode'] == E for p in ps)} of {len(ps)} evolved)", "",
                  "| name | mode | value | range | what | rule | why |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for p in ps:
            rng = "" if p["lo"] is None else f"{p['lo']} - {p['hi']} {p['unit']}"
            lines.append(f"| `{p['name']}` | **{p['mode']}** | {p['value']} | {rng} | {p['what']} | {p['rule']} | {p['why']} |")
        lines.append("")
    MD.write_text("\n".join(lines))


if __name__ == "__main__":
    if "--md" in sys.argv:
        write_md(json.loads(JSON.read_text())["params"])
    else:
        if JSON.exists():
            sys.exit(f"{JSON} exists: edit it, or delete it to start again")
        ps = catalogue()
        JSON.write_text(json.dumps({"_comment": __doc__.strip().splitlines()[0], "params": ps}, indent=1))
        write_md(ps)
    print(MD.read_text().splitlines()[2])
