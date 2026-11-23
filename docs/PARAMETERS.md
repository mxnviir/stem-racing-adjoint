# Layout search: every parameter of the car

156 parameters, 10 evolved in stage 1 (the layout search), 33 in stage 2 (`shape`: the shape search, with the body's lattice), 113 fixed. The searches read `layout_params.json`; change a `mode` there (`evolve` / `shape` / `fixed`), a `value` (used when fixed, and the start when evolved) or a range, then run `python layout_catalogue.py --md`.

x is measured from the nose tip, z from the track, mm. Ref A = front axle - 16, Ref B = rear axle + 16.

## layout (3 of 3 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `W` | **evolve** | 138.0 | 120.0 - 140.0 mm | wheelbase, front axle -> rear axle | T7.3 120.0-140.0 | team car: 138.0 (measured on the team's CAD, 2026-11-22). the main layout lever: drag, mass, and where the thrust and COM sit against the axles |
| `rear` | **evolve** | 63.75 | 36.0 - 87.0 mm | rear axle -> body rear face (the cartridge bore moves with it); the gene is the fraction of 36 .. 207 - W | the 223 mm block: 16 + W + rear <= 223, so rear <= 207 - W (67 at W 140, 87 at W 120). T9.4.2's 40 mm behind Ref B is the rear wing and its support only (team, 2026-11-22). Below ~35 the rear wing has no body under it. | team car: 63.75. shorter tail: less foam and wetted area, thrust point moves forward |
| `halo_rear` | **evolve** | 194.6 | 102.0 - 227.0 mm | halo pocket FRONT edge -> body rear face (pocket 50 mm long) | pocket front on/behind the front axle; pocket rear ahead of the rear axle and of the 52 mm bore (the decoder keeps it inside these for each W and rear) | team car: 194.6 (pocket front 7 mm behind the front axle). moves the halo, the 25 g halo + ballast container, and the loft's peak |

## cargo (2 of 2 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `cargo_x` | **evolve** | 0.5 | 0.0 - 1.0 0-1 | virtual cargo front -> back: 0 = its front on the front axle line, 1 = its back on the rear axle line | T4.2 wholly between the axle lines; may share the ballast container, not the halo pocket (z 14-24 vs 24+: never overlaps) | where the body must keep 55 mm of width at z 14-24: shapes the sidepods' minimum |
| `cargo_flip` | **evolve** | 0.0 | 0.0 - 1.0 0/1 | orientation: below 0.5 wide (55 mm) end forward, above 0.5 wide end rearward | T4.2 either way | the wide end sets where the body is widest |

## body loft (0 of 26 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `st_b0` | **fixed** | 11.0 | 6.0 - 24.0 mm | half-width at u = 0.0 | T8.5.1 <= 15 half-width ahead of Ref A (the nose); T3.4 car width; the block 65 wide | set so the body front meets the nose (T8.5.1 caps the nose at 25 mm): the 7 mm step at the joint becomes ~3 mm; shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_b1` | **fixed** | 13.24 | 6.0 - 24.0 mm | half-width at u = 0.08 | T8.5.1 <= 15 half-width ahead of Ref A (the nose); T3.4 car width; the block 65 wide | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_b2` | **fixed** | 16.53 | 6.0 - 24.0 mm | half-width at u = 0.2 | T8.5.1 <= 15 half-width ahead of Ref A (the nose); T3.4 car width; the block 65 wide | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_b3` | **fixed** | 18.0 | 6.0 - 24.0 mm | half-width at u = 0.35 | T8.5.1 <= 15 half-width ahead of Ref A (the nose); T3.4 car width; the block 65 wide | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_b4` | **fixed** | 17.79 | 6.0 - 24.0 mm | half-width at u = 0.5 | T8.5.1 <= 15 half-width ahead of Ref A (the nose); T3.4 car width; the block 65 wide | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_b5` | **fixed** | 17.15 | 6.0 - 24.0 mm | half-width at u = 0.65 | T8.5.1 <= 15 half-width ahead of Ref A (the nose); T3.4 car width; the block 65 wide | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_b6` | **fixed** | 15.91 | 6.0 - 24.0 mm | half-width at u = 0.82 | T8.5.1 <= 15 half-width ahead of Ref A (the nose); T3.4 car width; the block 65 wide | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_b7` | **fixed** | 14.0 | 6.0 - 24.0 mm | half-width at u = 1.0 | T8.5.1 <= 15 half-width ahead of Ref A (the nose); T3.4 car width; the block 65 wide | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zt0` | **fixed** | 24.5 | 12.0 - 50.0 mm | top height at u = 0.0 | T3.5 <= 65; the halo pocket floor (24) and the chamber wall (axis 31 + 9.25 + 3) are forced solid by Part 1 anyway | set so the body front meets the nose (T8.5.1 caps the nose at 25 mm): the 7 mm step at the joint becomes ~3 mm; shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zt1` | **fixed** | 27.2 | 14.0 - 50.0 mm | top height at u = 0.08 | T3.5 <= 65; the halo pocket floor (24) and the chamber wall (axis 31 + 9.25 + 3) are forced solid by Part 1 anyway | set so the body front meets the nose (T8.5.1 caps the nose at 25 mm): the 7 mm step at the joint becomes ~3 mm; shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zt2` | **fixed** | 29.8 | 16.0 - 50.0 mm | top height at u = 0.2 | T3.5 <= 65; the halo pocket floor (24) and the chamber wall (axis 31 + 9.25 + 3) are forced solid by Part 1 anyway | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zt3` | **fixed** | 32.0 | 18.0 - 50.0 mm | top height at u = 0.35 | T3.5 <= 65; the halo pocket floor (24) and the chamber wall (axis 31 + 9.25 + 3) are forced solid by Part 1 anyway | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zt4` | **fixed** | 32.85 | 20.0 - 50.0 mm | top height at u = 0.5 | T3.5 <= 65; the halo pocket floor (24) and the chamber wall (axis 31 + 9.25 + 3) are forced solid by Part 1 anyway | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zt5` | **fixed** | 35.41 | 22.0 - 50.0 mm | top height at u = 0.65 | T3.5 <= 65; the halo pocket floor (24) and the chamber wall (axis 31 + 9.25 + 3) are forced solid by Part 1 anyway | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zt6` | **fixed** | 40.37 | 24.0 - 50.0 mm | top height at u = 0.82 | T3.5 <= 65; the halo pocket floor (24) and the chamber wall (axis 31 + 9.25 + 3) are forced solid by Part 1 anyway | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zt7` | **fixed** | 48.0 | 26.0 - 50.0 mm | top height at u = 1.0 | T3.5 <= 65; the halo pocket floor (24) and the chamber wall (axis 31 + 9.25 + 3) are forced solid by Part 1 anyway | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zb0` | **fixed** | 3.5 | 3.0 - 24.0 mm | bottom height at u = 0.0 | T3.7 >= 1.5 above the track; the 6 mm block slot | set so the body front meets the nose (T8.5.1 caps the nose at 25 mm): the 7 mm step at the joint becomes ~3 mm; shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zb1` | **fixed** | 3.5 | 3.0 - 24.0 mm | bottom height at u = 0.08 | T3.7 >= 1.5 above the track; the 6 mm block slot | set so the body front meets the nose (T8.5.1 caps the nose at 25 mm): the 7 mm step at the joint becomes ~3 mm; shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zb2` | **fixed** | 5.18 | 3.0 - 24.0 mm | bottom height at u = 0.2 | T3.7 >= 1.5 above the track; the 6 mm block slot | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zb3` | **fixed** | 5.0 | 3.0 - 24.0 mm | bottom height at u = 0.35 | T3.7 >= 1.5 above the track; the 6 mm block slot | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zb4` | **fixed** | 5.8 | 3.0 - 24.0 mm | bottom height at u = 0.5 | T3.7 >= 1.5 above the track; the 6 mm block slot | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zb5` | **fixed** | 8.2 | 3.0 - 24.0 mm | bottom height at u = 0.65 | T3.7 >= 1.5 above the track; the 6 mm block slot | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zb6` | **fixed** | 12.84 | 3.0 - 24.0 mm | bottom height at u = 0.82 | T3.7 >= 1.5 above the track; the 6 mm block slot | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `st_zb7` | **fixed** | 20.0 | 3.0 - 24.0 mm | bottom height at u = 1.0 | T3.7 >= 1.5 above the track; the 6 mm block slot | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `p` | **fixed** | 2.6 | 2.0 - 4.0 - | section squareness (2 ellipse, larger boxier), all stations |  | one number for every section: fix unless the loft looks wrong |
| `blend_mm` | **fixed** | 3.0 | 1.0 - 6.0 mm | fillet where fuselage meets sidepods | 3.175 ball cutter | manufacturing detail |

## sidepods (0 of 7 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `s_b` | **fixed** | 28.0 | 14.0 - 32.5 mm | sidepod half-width | T3.4 width; the block 65 wide | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `s_zt` | **fixed** | 27.0 | 14.0 - 27.175 mm | sidepod top | team: nothing above 27.175 in the sidepods | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `s_zb` | **fixed** | 12.0 | 3.0 - 16.0 mm | sidepod bottom | T3.7 >= 1.5 | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `s_x0u` | **fixed** | 0.3 | 0.0 - 0.6 0-1 | sidepod start, as a fraction of Ref A -> rear face |  | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `s_lenu` | **fixed** | 0.4 | 0.15 - 0.8 0-1 | sidepod length, same fraction |  | shape, not layout: held while the layout is searched; the free-form stage on the best layout reshapes the body |
| `s_taper` | **fixed** | 12.0 | 2.0 - 25.0 mm | ease-in/out length at each end |  | shape detail |
| `s_p` | **fixed** | 3.0 | 2.0 - 5.0 - | sidepod section squareness |  | shape detail |

## underfloor tunnel (0 of 5 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `ft_h` | **fixed** | 0.0 | 0.0 - 8.0 mm | tunnel height (0 = no tunnel) | T3.7; the 6 mm block slot | off: Part 2's adjoint never found it worth it; try later as one evolve gene |
| `ft_w` | **fixed** | 8.0 | 3.0 - 15.0 mm | tunnel half-width |  |  |
| `ft_x0` | **fixed** | 50.0 | 40.0 - 120.0 mm | tunnel inlet x |  |  |
| `ft_x1` | **fixed** | 170.0 | 120.0 - 230.0 mm | tunnel outlet x |  |  |
| `ft_ramp` | **fixed** | 25.0 | 5.0 - 40.0 mm | ramp length at each end |  |  |

## sculpt modes (fuselage) (0 of 32 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `mode0` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.06, 15 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode1` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.06, 60 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode2` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.06, 120 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode3` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.06, 165 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode4` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.18, 15 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode5` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.18, 60 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode6` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.18, 120 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode7` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.18, 165 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode8` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.3, 15 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode9` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.3, 60 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode10` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.3, 120 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode11` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.3, 165 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode12` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.42, 15 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode13` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.42, 60 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode14` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.42, 120 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode15` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.42, 165 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode16` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.54, 15 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode17` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.54, 60 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode18` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.54, 120 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode19` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.54, 165 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode20` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.66, 15 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode21` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.66, 60 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode22` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.66, 120 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode23` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.66, 165 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode24` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.78, 15 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode25` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.78, 60 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode26` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.78, 120 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode27` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.78, 165 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode28` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.9, 15 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode29` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.9, 60 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode30` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.9, 120 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |
| `mode31` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at u = 0.9, 165 deg from the top |  | 56 local tweaks: too many for ~110 runs; a fine-tuning stage later |

## sculpt modes (sidepods) (0 of 24 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `mode32` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.0, 20 deg from the top |  | as above |
| `mode33` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.0, 60 deg from the top |  | as above |
| `mode34` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.0, 100 deg from the top |  | as above |
| `mode35` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.0, 150 deg from the top |  | as above |
| `mode36` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.2, 20 deg from the top |  | as above |
| `mode37` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.2, 60 deg from the top |  | as above |
| `mode38` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.2, 100 deg from the top |  | as above |
| `mode39` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.2, 150 deg from the top |  | as above |
| `mode40` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.4, 20 deg from the top |  | as above |
| `mode41` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.4, 60 deg from the top |  | as above |
| `mode42` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.4, 100 deg from the top |  | as above |
| `mode43` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.4, 150 deg from the top |  | as above |
| `mode44` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.6, 20 deg from the top |  | as above |
| `mode45` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.6, 60 deg from the top |  | as above |
| `mode46` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.6, 100 deg from the top |  | as above |
| `mode47` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.6, 150 deg from the top |  | as above |
| `mode48` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.8, 20 deg from the top |  | as above |
| `mode49` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.8, 60 deg from the top |  | as above |
| `mode50` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.8, 100 deg from the top |  | as above |
| `mode51` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 0.8, 150 deg from the top |  | as above |
| `mode52` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 1.0, 20 deg from the top |  | as above |
| `mode53` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 1.0, 60 deg from the top |  | as above |
| `mode54` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 1.0, 100 deg from the top |  | as above |
| `mode55` | **fixed** | 0.0 | -4.0 - 4.0 mm | bump/dent at sidepod u = 1.0, 150 deg from the top |  | as above |

## body mass (0 of 1 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `skin_mm` | **fixed** | 0.0 | -1.0 - 1.0 mm | uniform skin offset of the drawn body (0 = as drawn); lead fills the car to 48.2 g | T3.6 >= 48.0 g; T1.22 lead only in the container under the halo | the shape genes already set the foam |

## nose (3 of 7 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `nose_len` | **evolve** | 39.4 | 20.0 - 40.0 mm | nose tip ahead of Ref A (sets x_front = 16 + this) | T8.2 <= 40 (whole nose assembly) | team car: 39.4.  |
| `nose_k` | **evolve** | 0.5 | 0.3 - 1.2 - | section growth along the nose (0.5 elliptic, 1 conical) | T8.5.1 |  |
| `nose_p` | **fixed** | 2.5 | 2.0 - 4.0 - | nose section squareness | T8.5.1 half-width <= 15 | shape detail |
| `nose_tip_z` | **evolve** | 10.0 | 4.0 - 20.0 mm | tip height above the track | T8.5.1 <= 25; T3.7 |  |
| `nose_blend` | **fixed** | 1.0 | 0.5 - 10.0 mm | root station behind Ref A where it takes the body's section |  | run_car's choice |
| `nose_root_scale` | **fixed** | 1.0 | 0.9 - 1.0 - | root section vs the body's |  |  |
| `nose_wall` | **fixed** | 1.0 | 0.8 - 2.0 mm | printed shell wall | print minimum | mass only |

## front wing (16 of 16 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `fw_z` | **evolve** | 8.0 | 6.5 - 18.0 mm | chord line height at the root | T8.7 5 mm clear of the track; T8.5.2 <= 20 high beyond 15 mm out (front_wing_engine) | user 2026-11-22: front wing height is a parameter (wheel wake, ground effect) |
| `fw_pieces` | **shape** | 0.5 | 0.0 - 1.0 0-1 | below 0.5 one wing across the centre line, above it a left and a right wing | T8.6.1: 1 x 50 or 2 x 25 where another part passes through | user 2026-11-23: one piece or two, the search decides (starts at the middle) |
| `fw_chord` | **shape** | 15.3 | 15.3 - 25.0 mm | chord (a flat NACA 0015, user 2026-11-22) | T8.6.2 15-25; T8.6.3 thickness 2-6 (15 %) |  |
| `fw_te_gap` | **shape** | 6.0 | 5.3 - 20.0 mm | trailing edge ahead of Ref A | T8.7 5 mm to the body and the wheels; T8.2 the whole wing within 40 mm of Ref A |  |
| `fw_tip_y` | **shape** | 36.5 | 26.0 - 42.0 mm | tip, from the centre line (pushed out until each segment is 25 mm) | T8.6.1; T3.4 car width |  |
| `fw_root_y` | **shape** | 8.0 | 0.5 - 15.0 mm | two pieces: where each half starts (in the nose's side, or over/under it on a pylon) | T8.5.1 support band 15 mm |  |
| `fwsup0_width` | **shape** | 6.0 | 0.0 - 12.0 mm | support 0: width where it leaves the wing; under the print wall it is not there | print wall | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `fwsup0_y` | **shape** | 0.5 | 0.0 - 1.0 - | support 0: where on the span (0 the centre or a half's root, 1 the furthest out allowed) | T8.5.1 15 mm; T8.6.1 25 mm beyond | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `fwsup0_chord` | **shape** | 0.6 | 0.2 - 1.0 - | support 0: share of the chord it leaves from |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `fwsup0_foot` | **shape** | 1.2 | 0.4 - 2.0 - | support 0: its foot's size, times the patch's (flared > 1) |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `fwsup0_waist` | **shape** | 0.3 | 0.0 - 0.6 - | support 0: pinched half way by this share |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `fwsup1_width` | **shape** | 6.0 | 0.0 - 12.0 mm | support 1: width where it leaves the wing; under the print wall it is not there | print wall | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `fwsup1_y` | **shape** | 0.5 | 0.0 - 1.0 - | support 1: where on the span (0 the centre or a half's root, 1 the furthest out allowed) | T8.5.1 15 mm; T8.6.1 25 mm beyond | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `fwsup1_chord` | **shape** | 0.6 | 0.2 - 1.0 - | support 1: share of the chord it leaves from |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `fwsup1_foot` | **shape** | 1.2 | 0.4 - 2.0 - | support 1: its foot's size, times the patch's (flared > 1) |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `fwsup1_waist` | **shape** | 0.3 | 0.0 - 0.6 - | support 1: pinched half way by this share |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |

## rear wing (15 of 21 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `rw_chord` | **shape** | 15.3 | 15.3 - 25.0 mm | chord | T9.5.2 15-25 | user 2026-11-23: the rear wing and its supports designed by the search (rear_wing_engine.py); starts at the flat NACA 0015 at minimum size (user 2026-11-22's low-drag choice) |
| `rw_t_frac` | **fixed** | 0.15 | 0.13 - 0.4 - | thickness / chord | T9.5.3 2-6 mm | user 2026-11-22: a flat NACA 0015 at the minimum legal size is the low-drag, low-lift wing; nothing here is searched |
| `rw_camber` | **fixed** | 0.0 | 0.0 - 0.0 - | camber (fraction of chord): + lifts, - presses down |  | user 2026-11-23: every wing straight -- no tilt, no angling |
| `rw_aoa` | **fixed** | 0.0 | 0.0 - 0.0 deg | angle of attack, nose up (+) | T9.4.3, T9.6 | user 2026-11-23: every wing straight -- no tilt, no angling |
| `rw_half_span` | **shape** | 25.5 | 25.5 - 42.0 mm | half span | T9.5.1 >= 50; T3.4 85 wide | user 2026-11-23: the rear wing and its supports designed by the search (rear_wing_engine.py); starts at the flat NACA 0015 at minimum size (user 2026-11-22's low-drag choice) |
| `rw_x_le` | **evolve** | 3.5 | 0.0 - 20.0 mm | leading edge behind Ref B | T9.4.1 behind Ref B; T9.4.2 <= 40 behind Ref B; T5.6 nothing round the cartridge behind the rear face (the gates check each car) | user 2026-11-22: rear wing position is a parameter |
| `rw_clear_air_margin` | **fixed** | 0.5 | 0.2 - 2.0 mm | margin over the 5 mm clear air | T9.6 | user 2026-11-22: a flat NACA 0015 at the minimum legal size is the low-drag, low-lift wing; nothing here is searched |
| `rw_pylon_t` | **fixed** | 2.0 | 1.5 - 4.0 mm | pylon thickness |  | user 2026-11-22: a flat NACA 0015 at the minimum legal size is the low-drag, low-lift wing; nothing here is searched |
| `rw_pylon_chord` | **fixed** | 10.0 | 6.0 - 20.0 mm | pylon chord |  | user 2026-11-22: a flat NACA 0015 at the minimum legal size is the low-drag, low-lift wing; nothing here is searched |
| `rw_t` | **shape** | 2.3 | 2.3 - 6.0 mm | wing thickness | T9.5.3 2-6 | user 2026-11-23: the rear wing and its supports designed by the search (rear_wing_engine.py); starts at the flat NACA 0015 at minimum size (user 2026-11-22's low-drag choice) |
| `rw_lift` | **shape** | 0.0 | 0.0 - 15.0 mm | height above the lowest T9.6 / T9.7 allow | T9.4.3 65 mm | user 2026-11-23: the rear wing and its supports designed by the search (rear_wing_engine.py); starts at the flat NACA 0015 at minimum size (user 2026-11-22's low-drag choice) |
| `rwsup0_width` | **shape** | 6.0 | 0.0 - 12.0 mm | support 0: width where it leaves the wing; under the print wall it is not there | print wall | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `rwsup0_y` | **shape** | 0.5 | 0.0 - 1.0 - | support 0: where on the span (0 just off the centre line, 1 the tip; never on it: team rule) | team: off the centre line | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `rwsup0_chord` | **shape** | 0.6 | 0.2 - 1.0 - | support 0: share of the chord it leaves from |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `rwsup0_foot` | **shape** | 1.2 | 0.4 - 2.0 - | support 0: its foot's size, times the patch's (flared > 1) |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `rwsup0_waist` | **shape** | 0.3 | 0.0 - 0.6 - | support 0: pinched half way by this share |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `rwsup1_width` | **shape** | 6.0 | 0.0 - 12.0 mm | support 1: width where it leaves the wing; under the print wall it is not there | print wall | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `rwsup1_y` | **shape** | 0.5 | 0.0 - 1.0 - | support 1: where on the span (0 just off the centre line, 1 the tip; never on it: team rule) | team: off the centre line | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `rwsup1_chord` | **shape** | 0.6 | 0.2 - 1.0 - | support 1: share of the chord it leaves from |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `rwsup1_foot` | **shape** | 1.2 | 0.4 - 2.0 - | support 1: its foot's size, times the patch's (flared > 1) |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |
| `rwsup1_waist` | **shape** | 0.3 | 0.0 - 0.6 - | support 1: pinched half way by this share |  | user 2026-11-23: supports grown like the halo's loft (wing_loft.py), no presets: every number starts at the middle of its range |

## tether guides (0 of 2 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `tether_front` | **fixed** | 5.0 | 0.0 - 10.0 mm | front guide ahead of the front axle | T6.1 within 10 | aero-tiny; affects the guide-friction lever only |
| `tether_rear` | **fixed** | 5.0 | 0.0 - 10.0 mm | rear guide behind the rear axle | T6.1 within 10 |  |

## fixed by the build (0 of 3 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `chamber_z` | **fixed** | 31.0 | 30.0 - 40.0 mm | cartridge axis height = thrust line | T5.2 30-40 | a Part 1 constant (CHAMBER_AXIS_Z_MM): making it a gene needs a Part 1 change; ask if wanted |
| `wheels` | **fixed** | team_stl |  | the team's measured wheels (front 13.25, rear 17.25 wide) | T7.4, T7.5 | printed parts you already have |
| `wheel_inner_y` | **fixed** | Part 1 |  | wheel track (inner faces) | T7.2 gaps >= 38 / 30, T3.4 | a Part 1 constant used by every mask |

## wheel supports (4 of 7 evolved)

| name | mode | value | range | what | rule | why |
| --- | --- | --- | --- | --- | --- | --- |
| `sup_chord` | **shape** | 12.0 | 8.0 - 18.0 mm | plate chord (x) where it leaves the body; the saddle's is at least this | T7.12.1 inside the wheels' cylinder (the engine narrows a saddle that would not fit) | what the air sees of the support: evolved in stage 2 with the body's shape |
| `sup_t` | **shape** | 2.0 | 1.2 - 4.0 mm | plate thickness (z), at least what the loads need | loads: 3 N radial, 1.2 N side, 20 MPa, 0.15 mm sag (support_engine.py); flush with the underside (gate) | thicker is stiffer and blunter; the engine grows it until the loads pass |
| `sup_taper` | **shape** | 1.0 | 0.6 - 1.4 - | plate chord at the disc / at the body |  |  |
| `sup_fillet` | **shape** | 2.5 | 1.0 - 4.0 mm | radius of the concave fillet where the arm grows into the disc |  |  |
| `sup_saddle_h` | **fixed** | 3.0 | 1.05 - 6.0 mm | saddle depth over the underside (the slot milled from below), at least what the loads need | 3 mm foam over the slot or none; cut from below by the 3.175 mm ball | inside the body: the air never sees it, so it is sized, not searched |
| `sup_disc_r` | **fixed** | 12.0 | 8.0 - 12.2 mm | disc radius (beam_support's disc) | inside the rim (13.72) less 0.5; T3.7 | inside the wheel: not seen by the CFD |
| `sup_disc_recess` | **fixed** | 1.0 | 0.0 - 2.0 mm | disc's outer face inside the wheel's inner face |  |  |
