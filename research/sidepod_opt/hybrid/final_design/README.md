# The loop's final sidepod (2026-11-25, generation 6; steady model -9.94 mN vs the team pod)
`car_half.stl`: the half car, the base STL (`gate/original_rm`) plus the six accepted chained moves (smoothed normals,
1.5 mm ground clearance), rebuilt with `hybrid/chain_solve.py` (`CHAIN_DRY=1`) from `loop_state.json` "final".
- Moved 9042 vertices; peak 1.34 mm out, 2.04 mm in; area-RMS 0.42 mm over the moved surface; volume +142 mm^3.
- Where (car frame x from the nose; area-weighted mean normal move): the front third's upper surface (z > 20 mm) is
  pulled in by 0.33 mm on average (up to 2.0 mm: the pod's front top edge is cut back); the middle third's lower side
  moves out 0.21 mm; elsewhere the mean is within +-0.1 mm, with local +-1 mm features.
- Forces (half car, steady model, last 404 iterations): drag 190.73 -> 180.79 mN; vertical force (lift) 76.97 -> 66.49 mN.
  Production scheme (generation-3 design, 2000 iterations): drag 181.81 -> 175.49 mN, lift 83.86 -> 82.10 mN.
- Not legalised: milling, ceiling and mass rules are off in this stage.
