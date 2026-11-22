"""Race time of a car: Part 2's race model with THIS car's layout and exact mass.

Inputs  D20, L20 (N, whole car, from any evaluator) and Car.mass(B) (foam, lead, the empty
        cartridge shell, COM). Same parameter vector and calibration as Part 2's stopwatch:
        measured thrust sheet, TIME_COEFFICIENT, default rolling mu and wheel MOI.
Output  race time (s) and its slopes (dT/dD20, dT/dmass, dT/dCOM ...), used to turn force and
        mass sensitivities into race-time sensitivities (the adjoint path).
The model is jitted with the sheet as a closure constant: no re-trace per call (Part 2 notes a
JIT-mapping leak that kills a process after ~20 un-jitted calls) and ~40x faster.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
import repo_paths  # noqa: E402,F401
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import physics_contract as pc  # noqa: E402
import race_objective as R  # noqa: E402
from pitch_balance import CarGeometry  # noqa: E402

THRUST_CSV = HERE.parents[1] / "car/race/thrust_measured_beta.csv"


class RaceModel:
    def __init__(self, spec):
        import jax
        import jax.numpy as jnp
        s = spec
        nose = lambda x: (s.x_nose_mm - x) / 1e3
        x_thrust = s.tail_x - s.cartridge_out_mm
        geo = CarGeometry(x_front_axle_m=nose(s.x_front_axle), wheelbase_m=(s.x_front_axle - s.x_rear_axle) / 1e3,
                          x_thrust_m=nose(x_thrust), z_thrust_m=s.thrust_z / 1e3,
                          x_guide_front_m=nose(s.x_front_axle + 5), x_guide_rear_m=nose(s.x_rear_axle - 5),
                          z_guide_m=0.006)
        model = R.build_smooth_sheet_model(str(THRUST_CSV))._replace(
            geometry=geo, gas_xz_m=(nose(x_thrust) - R.CARTRIDGE_LENGTH_M / 2, s.thrust_z / 1e3))
        self.model = model
        self._vg = jax.jit(lambda p: jax.value_and_grad(R.race_time_seconds)(p, model))
        self._jnp = jnp

    def params(self, D20, L20, mass):
        return np.array([D20, mass["race_mass_g"] / 1e3, pc.DEFAULT_ROLLING_MU, pc.DEFAULT_WHEEL_MOI_KG_M2,
                         pc.TIME_COEFFICIENT, mass["com_z_mm"] / 1e3, L20, mass["com_x_car_mm"] / 1e3])

    def __call__(self, D20, L20, mass):
        T, g = self._vg(self._jnp.asarray(self.params(D20, L20, mass), dtype=self._jnp.float64))
        return float(T), {n: float(g[i]) for i, n in enumerate(R.PARAM_NAMES)}


def mass_cell_gradient(car, m, slopes):
    """dT (s) per mm^3 of foam added at each cell, through mass, lead swap and COM (exact).
    m: car.mass(body mesh) of the car the gradient is taken at."""
    s = car.s
    rho = 1e-3 * 0.163                                         # g per mm^3
    tot = m["race_mass_g"]
    lead_active = m["lead_g"] > 0
    dm = 0.0 if lead_active else rho                           # lead absorbs foam while there is lead
    # COM shift from +rho g at the cell and -rho g of lead at the container (if active)
    xc, zc = s.x_nose_mm - car.X, car.Z
    cx, cz = m["com_x_car_mm"], m["com_z_mm"]
    lx, lz = s.x_nose_mm - s.lead_xz[0], s.lead_xz[1]
    dcx = (rho * (xc - cx) - (rho * (lx - cx) if lead_active else 0.0)) / tot
    dcz = (rho * (zc - cz) - (rho * (lz - cz) if lead_active else 0.0)) / tot
    return (slopes["car_weight_kg"] * dm / 1e3 + slopes["com_x_m"] * dcx / 1e3 + slopes["com_height_m"] * dcz / 1e3)
