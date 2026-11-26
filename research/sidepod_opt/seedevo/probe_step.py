"""A probe move of ANY design, built exactly like the hybrid loop's moves (esi/make_step.py: smoothed field on the
design's own STL vertices, region taper, mean removed, 95th-percentile scaling, clip, peak = amp; smoothed normals
and ground clearance from STEP_NORMAL_SIGMA_MM / STEP_ZMIN_MM), for the real-CFD trust check (test TR).

    python -m seedevo.probe_step <design car folder> <name> <field> <amp_mm>
      field: zero | dafnpz:<npz> (downhill along a DAFoam gradient) | dafopp:<npz> (uphill) | rnd<k>
    -> gate/bump_<name>/ (car folder + morph_field.npz), as gate.py bump expects
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "esi"))


def main(design, name, field, amp):
    import gate
    gate.ORIG = Path(design).resolve()                     # make_step builds the move on THIS design's surface
    import make_step as MS
    down = MS.field_on_vertices
    if field.startswith("dafopp:"):
        MS.field_on_vertices = lambda fld, V, N=None, A=None: -down("dafnpz:" + fld[len("dafopp:"):], V, N, A)
    try:
        MS.main(name, field, amp)
    finally:
        MS.field_on_vertices = down                        # several moves in one process (tr_predict) stay independent


if __name__ == "__main__":
    main(*sys.argv[1:5])
