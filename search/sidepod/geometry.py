"""Design -> legal, milled sidepod -> exact, watertight car for CFD.

Frames
  STEP frame  x forward (nose at +x), y left, z up, mm  -- the team's CAD.
  car frame   x from the nose tip towards the tail, z up from the track, m -- Parts 2/4 and
              OpenFOAM (flow along +x). x_car = (x_nose - x_step) / 1000.

What is exact and what is designed
  * Everything outside the sidepod region is the team's CAD: the STEP body tessellated from its
    B-rep (cadio.tessellate), minus the region solid by an exact Boolean (manifold3d).
  * Wheels are the STEP's own solids (28.24 mm), sunk 0.3 mm into the road as Part 4 does.
  * Only inside the region is the shape designed. A method's field is turned into a body on a
    0.5 mm grid (crop around the region, full width and height), milled with Part 1's rule,
    checked, re-surfaced (marching cubes), clipped to the region solid and unioned with the exact
    CAD. The final mesh must pass cadio.accept (watertight, coherent winding, manifold).
  * Mass and COM come from the final meshes, not voxels.

Checks before a car may be timed (Car.check): one piece; nothing changed outside the region;
no foam in forced air; cargo inside; T3.7 clearance; foam walls >= 3 mm (team milling limit);
no sealed voids. A car that fails is never meshed for CFD.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl  # the repo root, then every code folder (repo_paths.py)
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
import repo_paths  # noqa: E402,F401
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
import cadio as CI  # noqa: E402
import machining as MC  # noqa: E402  (Part 1: the team's milling rule)

FOAM_G_CM3 = 0.163
LEAD_G_CM3 = 11.34
WHEEL_SINK_MM = 0.3                  # Part 4 assembly.SINK_MM
MIN_FOAM_WALL_MM = 3.0               # Part 5 rules_constants.MACHINED_MIN_WALL_MM (team)


SEAM_EPS_MM = 0.05                 # pod/kept-CAD overlap at the region boundary (below any CFD cell)


@dataclass
class CarSpec:
    """Everything about the car that is not the sidepod. Defaults: the trial car STEP."""
    step: str = str(HERE / "cad/trial_car.step")
    body_solid: str = "car_body"
    wheel_solids: tuple = ("wheel_fl", "wheel_rl", "wheel_fr", "wheel_lr")
    x_nose_mm: float = 228.625
    x_front_axle: float = 173.25
    x_rear_axle: float = 35.25
    r_wheel: float = 14.12
    front_inner_y: float = 19.25
    rear_inner_y: float = 16.25
    # region (per side, mirrored)
    region_x: tuple = (49.4, 159.1)
    region_ymax: float = 32.5            # T1.14 block half-width
    region_z: tuple = (1.5, 40.0)        # T3.7 clearance .. deck
    spine_y: float = 13.5                # |y| <= this and z >= spine_z: deck, cockpit, halo (locked, air too)
    spine_z: float = 17.0
    halo_x0: float = 115.0               # T4.4.2: nothing above halo_zmin from here forward
    halo_zmin: float = 27.0
    # design rules (switches; defaults keep the original behaviour)
    cargo: bool = True                   # False: no virtual cargo (not forced, not checked)
    ceiling_mm: float | None = None      # nothing in the region above this height (e.g. 27.0: the team's sidepod top)
    mill_dirs: str = "zy"                # "zy": top, bottom, left, right set-ups; "z": top and bottom only
    cargo_x: tuple = (76.0, 136.0)       # T4.2 wedge, wide end (55 mm) forward
    cargo_z: tuple = (17.0, 27.0)        # ASSUMED: confirm with the team
    # mass (ASSUMED where the STEP is silent; see README)
    floor_g: float = 48.2                # T3.6 48.0 + 0.2 margin; no upper limit
    lead_xz: tuple = (130.0, 21.0)       # T1.22 container under the halo, STEP frame
    lead_cap_cm3: float = 1.39
    other_parts_g: float | None = None   # None: 48.2 g minus the drawn body's foam
    other_parts_xz: tuple | None = None  # None: mid-wheelbase, z 16
    cartridge_shell_g: float = 21.15     # Part 2's car_weight_kg includes it (Appendix vi)
    thrust_z: float = 30.0
    tail_x: float = -28.5
    cartridge_out_mm: float = 13.0
    speed_mps: float = 20.0


class Car:
    def __init__(self, spec: CarSpec = CarSpec(), h: float = 0.5, cache: Path | None = None):
        import trimesh
        self.s, self.h = spec, h
        cache = Path(cache or HERE / "cache")
        cache.mkdir(parents=True, exist_ok=True)
        s = spec
        # ---- exact CAD (cached as STL, mm, STEP frame)
        names = (s.body_solid,) + tuple(s.wheel_solids)
        if not all((cache / f"exact_{n}.stl").exists() for n in names):
            solids = CI.read_step_solids(s.step)
            for n in names:
                sol = CI.outer_solid(solids[n]) if n == s.body_solid else solids[n]
                CI.tessellate(sol).export(cache / f"exact_{n}.stl")
        self.body_mesh = trimesh.load(cache / f"exact_{s.body_solid}.stl")
        self.wheel_meshes = {n: trimesh.load(cache / f"exact_{n}.stl") for n in s.wheel_solids}
        for m in [self.body_mesh, *self.wheel_meshes.values()]:
            CI.accept(m)
        # ---- design grid: crop in x around the region, full width and height
        x0, x1 = s.region_x[0] - 6.0, s.region_x[1] + 6.0
        ym = float(np.ceil(max(abs(self.body_mesh.bounds[:, 1]).max(), s.region_ymax) + 4.0))
        self.xs = np.arange(x0, x1, h) + h / 2
        self.ys = np.arange(-ym, ym, h) + h / 2
        self.zs = np.arange(0.0, float(np.ceil(self.body_mesh.bounds[1, 2] + 4.0)), h) + h / 2
        vp = cache / f"crop_{h:g}mm.npz"
        if vp.exists():
            self.body0 = np.load(vp)["body0"]
        else:
            self.body0 = CI.voxelize(self.body_mesh, self.xs, self.ys, self.zs)
            np.savez_compressed(vp, body0=self.body0)
        X, Y, Z = np.meshgrid(self.xs, self.ys, self.zs, indexing="ij")
        self.X, self.Y, self.Z = X, Y, Z
        AY = np.abs(Y)
        ztop = s.region_z[1] if s.ceiling_mm is None else min(s.region_z[1], s.ceiling_mm)
        box = ((X >= s.region_x[0]) & (X <= s.region_x[1]) & (AY <= s.region_ymax)
               & (Z - h / 2 >= s.region_z[0]) & (Z + h / 2 <= ztop))
        dy = np.clip(AY - s.front_inner_y, 0, None)
        t792 = ((AY >= s.front_inner_y) & (X <= s.x_front_axle)
                & (X >= s.x_front_axle - s.r_wheel - (15.0 + dy / np.tan(np.radians(60)))))
        dy = np.clip(AY - s.rear_inner_y, 0, None)
        t793 = ((AY >= s.rear_inner_y) & (X >= s.x_rear_axle)
                & (X <= s.x_rear_axle + s.r_wheel + 5.0 + dy))
        halo = (X >= s.halo_x0) & (Z > s.halo_zmin)
        self.spine_zone = (AY <= s.spine_y) & (Z >= s.spine_z)
        hw = 5.0 + (X - s.cargo_x[0]) / (s.cargo_x[1] - s.cargo_x[0]) * 22.5
        self.cargo = ((X >= s.cargo_x[0]) & (X <= s.cargo_x[1]) & (AY <= hw)
                      & (Z >= s.cargo_z[0]) & (Z <= s.cargo_z[1]))
        if not s.cargo:
            self.cargo = np.zeros_like(self.cargo)
        self.forced_air = (t792 | t793 | halo) & box & ~self.spine_zone
        self.region = box & ~self.forced_air & ~self.spine_zone
        self.keep = self.body0 & ~self.region
        din = ndimage.distance_transform_edt(self.body0) * h
        dout = ndimage.distance_transform_edt(~self.body0) * h
        self.sdf_original = np.where(self.body0, din, -dout).astype(np.float32)
        # "lean" = cargo only; with no cargo, no pod at all: minus the distance from the kept body,
        # on the same scale as the original's distance field (a large constant would swamp blends)
        self.sdf_lean = (-(ndimage.distance_transform_edt(~(self.cargo if self.cargo.any() else self.keep)) * h)
                         ).astype(np.float32)
        lo = np.array([s.region_x[0], 0.0, s.region_z[0]]); hi = np.array([s.region_x[1], s.region_ymax, s.region_z[1]])
        self.norm = np.stack([(X - (lo[0] + hi[0]) / 2) / ((hi[0] - lo[0]) / 2), AY / hi[1],
                              (Z - (lo[2] + hi[2]) / 2) / ((hi[2] - lo[2]) / 2)], -1).astype(np.float32)
        w = np.argwhere(self.region)
        self.rlo, self.rhi = w.min(0), w.max(0) + 1
        # ---- exact solids for the Booleans
        self.region_M = self._region_manifold()
        self.region_Me = self._region_manifold(SEAM_EPS_MM)      # grown: the pod overlaps the kept CAD
        self.body_M = CI.to_manifold(self.body_mesh)
        self.kept_M = self.body_M - self.region_M
        # ---- mass bookkeeping (body foam from the exact mesh)
        self.foam0_g = self.body_mesh.volume * 1e-3 * FOAM_G_CM3
        self.other_g = s.other_parts_g if s.other_parts_g is not None else s.floor_g - self.foam0_g
        self.other_xz = s.other_parts_xz or (0.5 * (s.x_front_axle + s.x_rear_axle), 16.0)

    @property
    def wheels(self) -> np.ndarray:
        """The four wheels on the design grid (for pictures only)."""
        if not hasattr(self, "_wheels"):
            self._wheels = np.zeros(self.body0.shape, bool)
            for m in self.wheel_meshes.values():
                self._wheels |= CI.voxelize(m, self.xs, self.ys, self.zs)
        return self._wheels

    # ------------------------------------------------------------------ exact region solid
    def _region_manifold(self, eps=0.0):
        """Box minus the T7.9.2 / T7.9.3 wedges, the halo cap and the spine zone, both sides,
        built from exact prisms (STEP frame, mm). Same rules as the voxel masks above.
        eps > 0 grows it by eps on every face (box out, cuts in): the pod is cut with that, so it
        overlaps the kept CAD instead of sharing faces with it (shared faces leave seam slivers)."""
        import manifold3d as mf
        s = self.s
        big = 200.0

        def box(x0, x1, y0, y1, z0, z1):
            return mf.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])

        def prism_xy(poly, z0, z1):                                 # polygon in (x, y), extruded in z
            P = np.asarray(poly, float)
            if np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]) < 0:
                P = P[::-1]                 # manifold3d needs CCW: a CW polygon gives an invalid solid
            cs = mf.CrossSection([P.tolist()])
            if e:
                cs = cs.offset(-e, mf.JoinType.Miter)
            M = mf.Manifold.extrude(cs, z1 - z0).translate([0, 0, z0])
            assert M.status() == mf.Error.NoError and M.volume() > 0, "wedge prism"
            return M
        e = eps
        R = box(s.region_x[0] - e, s.region_x[1] + e, -s.region_ymax - e, s.region_ymax + e, s.region_z[0] - e, s.region_z[1] + e)
        cut = []
        t60 = 1.0 / np.tan(np.radians(60))
        xf = s.x_front_axle - s.r_wheel - 15.0
        for sg in (1, -1):
            yi = sg * s.front_inner_y
            yo = sg * (s.front_inner_y + 60.0)
            poly = [[s.x_front_axle, yi], [xf, yi], [xf - 60.0 * t60, yo], [s.x_front_axle, yo]]
            cut.append(prism_xy(poly, -1, 60))
            yi = sg * s.rear_inner_y
            yo = sg * (s.rear_inner_y + 60.0)
            xr = s.x_rear_axle + s.r_wheel + 5.0
            poly = [[s.x_rear_axle, yi], [s.x_rear_axle, yo], [xr + 60.0, yo], [xr, yi]]
            cut.append(prism_xy(poly, -1, 60))
        cut.append(box(s.halo_x0 + e, big, -big, big, s.halo_zmin + e, big))
        if s.ceiling_mm is not None:                                # exact: no seam allowance above the ceiling
            cut.append(box(-big, big, -big, big, s.ceiling_mm, big))
        cut.append(box(-big, big, -s.spine_y + e, s.spine_y - e, s.spine_z + e, big))
        for c in cut:
            R = R - c
        assert R.status() == mf.Error.NoError and R.volume() > 0, "region solid is empty"
        return R

    # ------------------------------------------------------------------ design -> body (voxels)
    def finish(self, field_mm: np.ndarray) -> np.ndarray:
        f = 0.5 * (field_mm + field_mm[:, ::-1])                  # symmetric car
        return self.keep | (f > 0) & self.region | self.cargo

    def mill(self, B: np.ndarray) -> tuple[np.ndarray, dict]:
        """Part 1's machining rule with this spec's set-ups (mill_dirs)."""
        dirs = {"zy": (("z", 2, True), ("z", 2, False), ("y", 1, True), ("y", 1, False)),
                "z": (("z", 2, True), ("z", 2, False))}[self.s.mill_dirs]
        saved, MC.DIRECTIONS = MC.DIRECTIONS, dirs
        try:
            return self._mill(B)
        finally:
            MC.DIRECTIONS = saved

    def _mill(self, B: np.ndarray) -> tuple[np.ndarray, dict]:
        rep = {"uncut_foam_mm3": 0.0}
        r = MC.TOOL_R_MM / self.h
        for _ in range(3):
            stuck = ~B & ~MC.reachable_air(~B, r) & self.region
            n = int(stuck.sum())
            if not n:
                break
            B = B | stuck
            rep["uncut_foam_mm3"] += n * self.h ** 3
        filled = ndimage.binary_fill_holes(B)
        rep["sealed_voids_mm3"] = float(((filled & ~B) & self.region).sum() * self.h ** 3)
        B = B | (filled & self.region)
        lab, _ = ndimage.label(B)
        keep = np.unique(lab[self.keep & B]); keep = keep[keep > 0]
        loose = B & ~np.isin(lab, keep)
        rep["loose_dropped_mm3"] = float(loose.sum() * self.h ** 3)
        B = (B & ~loose) | self.cargo
        B = np.where(self.region | self.cargo, B, self.body0)
        return B, rep

    def _thin(self, B):
        """Region foam thinner than the team's 3 mm wall: what an opening by a 1.5 mm ball removes,
        ignoring the outermost cell (corners of the voxel staircase)."""
        rr = MIN_FOAM_WALL_MM / 2 / self.h
        k = np.arange(-int(np.ceil(rr)), int(np.ceil(rr)) + 1)
        ball = (k[:, None, None] ** 2 + k[None, :, None] ** 2 + k[None, None, :] ** 2) <= rr * rr
        op = ndimage.binary_opening(B, ball)
        return B & self.region & ~op & (ndimage.distance_transform_edt(~op) > 1.0)

    def min_wall(self, B, rep, max_passes=5):
        """Minimum-feature filter (as in topology optimisation): while the design has thin foam, open
        the region foam by the 3 mm wall ball (removes fins and slivers; the team's own thin CAD edges
        are kept) and mill again (the mill may fill air the cutter can't reach). A design that is
        already clean is not touched. Returns (B, passes); the check still rejects what stays thin."""
        if self.thin_foam_mm3(B) <= 30.0:
            return B, 0
        rr = MIN_FOAM_WALL_MM / 2 / self.h
        k = np.arange(-int(np.ceil(rr)), int(np.ceil(rr)) + 1)
        ball = (k[:, None, None] ** 2 + k[None, :, None] ** 2 + k[None, None, :] ** 2) <= rr * rr
        for n in range(1, max_passes + 1):
            pod = B & self.region
            op = ndimage.binary_opening(pod | (self.body0 & ~self.region), ball, border_value=1) & self.region
            B = np.where(self.region, op | (pod & self._thin0), B) | self.cargo
            B, r2 = self.mill(B)
            for key, v in r2.items():
                rep[key] = rep.get(key, 0.0) + v
            if self.thin_foam_mm3(B) <= 30.0:
                break
        return B, n

    def thin_foam_mm3(self, B):
        """Thin foam the DESIGN made: thin cells that are not already thin on the team's original
        (its own CAD edges are thin at this test: 32 mm3 at 1 mm, 226 mm3 at 0.5 mm)."""
        if not hasattr(self, "_thin0"):
            self._thin0 = self._thin(self.body0)
        return float((self._thin(B) & ~self._thin0).sum() * self.h ** 3)

    def check(self, B: np.ndarray) -> dict:
        lab, n = ndimage.label(B)
        pod = B & self.region
        out = {"pieces": int(n),
               "changed_outside_region_mm3": float(((B ^ self.body0) & ~self.region & ~self.cargo).sum() * self.h ** 3),
               "foam_in_forced_air_mm3": float((B & self.forced_air).sum() * self.h ** 3),
               "cargo_inside": bool(B[self.cargo].all()),
               "track_clearance_mm": float(self.Z[pod].min() - self.h / 2) if pod.any() else None,
               "thin_foam_mm3": self.thin_foam_mm3(B)}
        out["ok"] = (n == 1 and out["changed_outside_region_mm3"] == 0 and out["foam_in_forced_air_mm3"] == 0
                     and out["cargo_inside"] and (out["track_clearance_mm"] is None or out["track_clearance_mm"] >= 1.5)
                     and out["thin_foam_mm3"] <= 30.0)
        return out

    # ------------------------------------------------------------------ voxels -> exact mesh
    def body_mesh_for(self, B: np.ndarray, original: bool = False):
        """The car body as an exact, watertight mesh (STEP frame, mm): the CAD outside the region,
        the designed surface inside it."""
        if original:
            return self.body_mesh.copy()
        # The Boolean with the CAD is exact, but where the designed surface happens to graze a CAD
        # edge it leaves sub-micron slivers that welding (as any STL reader does) turns non-manifold.
        # Such coincidences are chance: retry with a slightly different smoothing (a few um of surface
        # change), first that passes wins.
        err = None
        for sigma in (0.7, 0.72, 0.68, 0.75, 0.65):
            try:
                out = self._pod_union(B, sigma)
                CI.accept(out, name="designed body")
                return out
            except ValueError as e:
                err = e
        raise err

    def _pod_union(self, B, sigma):
        import trimesh
        from skimage import measure
        P = np.pad(B.astype(np.float32), 2)
        P = ndimage.gaussian_filter(P, sigma)
        v, f, _n, _ = measure.marching_cubes(P, 0.5)
        h = self.h
        v = np.c_[self.xs[0] + (v[:, 0] - 2) * h, self.ys[0] + (v[:, 1] - 2) * h, self.zs[0] + (v[:, 2] - 2) * h]
        m = trimesh.Trimesh(v, f, process=True)
        if m.volume < 0:
            m.invert()
        if not m.is_watertight:
            m = CI.repair(m)
        pod_M = CI.to_manifold(m) ^ self.region_Me                  # ^ = intersection in manifold3d
        return CI.clean(CI.from_manifold(self.kept_M + pod_M))     # weld Boolean seams as a reader will

    def mass(self, body_mesh) -> dict:
        s = self.s
        foam = body_mesh.volume * 1e-3 * FOAM_G_CM3
        lead = max(0.0, s.floor_g - self.other_g - foam)
        legal = lead <= s.lead_cap_cm3 * LEAD_G_CM3
        car = foam + self.other_g + lead
        c = body_mesh.center_mass
        mx = foam * c[0] + self.other_g * self.other_xz[0] + lead * s.lead_xz[0]
        mz = foam * c[2] + self.other_g * self.other_xz[1] + lead * s.lead_xz[1]
        cx = s.tail_x - s.cartridge_out_mm + 32.5                   # cartridge centre
        tot = car + s.cartridge_shell_g
        mx = (mx + s.cartridge_shell_g * cx) / tot
        mz = (mz + s.cartridge_shell_g * s.thrust_z) / tot
        return dict(foam_g=float(foam), lead_g=float(lead), car_g=float(car), legal=bool(legal), race_mass_g=float(tot),
                    com_x_car_mm=float(s.x_nose_mm - mx), com_z_mm=float(mz))

    def build(self, field_mm: np.ndarray, original: bool = False) -> dict:
        """Field -> milled voxels -> checks; the exact mesh and mass only for a car that passes."""
        B, rep = self.mill(self.finish(field_mm))
        B, rep["min_wall_passes"] = self.min_wall(B, rep)
        chk = self.check(B)
        out = dict(voxels=B, mill=rep, check=chk, mesh=None, mass=None)
        if chk["ok"]:
            out["mesh"] = self.body_mesh_for(B, original)
            out["mass"] = self.mass(out["mesh"])
        return out

    # ------------------------------------------------------------------ export for CFD
    def to_car_frame(self, m):
        """STEP frame (mm) -> car frame (m): x from the nose tip, flow along +x. A mirror, so the
        winding is flipped back to keep normals outward."""
        t = m.copy()
        T = np.diag([-1e-3, 1e-3, 1e-3, 1.0]); T[0, 3] = self.s.x_nose_mm * 1e-3
        t.apply_transform(T)
        if t.volume < 0:
            t.invert()
        return t

    def export_car_folder(self, body_mesh, out: Path, label: str = "") -> Path:
        """Part 2 stopwatch folder: car_half.stl (solid `car`, m, car frame, y >= 0, closed exactly
        at y = 0 by a Boolean), wheelF/wheelR.stl (exact, sunk 0.3 mm), assembly.json (rotating
        wheels), mass_report.json; body_full.stl (whole body, solid `car`, for SimScale / the CNC)."""
        import manifold3d as mf
        out = Path(out); out.mkdir(parents=True, exist_ok=True)
        s = self.s
        full = self.to_car_frame(CI.clean(body_mesh))           # clean in mm, then scale and mirror
        CI.accept(full, body_mesh.volume * 1e-9, name="body (car frame)")
        # cut at the symmetry plane in mm (float32 inside manifold3d), then to the car frame
        half_mm = CI.from_manifold(CI.to_manifold(body_mesh) ^ mf.Manifold.cube([1000., 500., 500.]).translate([-500., 0., -100.]))
        half = self.to_car_frame(CI.clean(half_mm))
        CI.write_ascii_named(half, out / "car_half.stl", "car", full.volume / 2, 0.002)
        CI.write_ascii_named(full, out / "body_full.stl", "car", body_mesh.volume * 1e-9)
        CI.clean(body_mesh).export(out / "body_mm.stl")         # STEP frame, mm: the SimScale air volume is built from it
        omega = -s.speed_mps / (s.r_wheel / 1e3)
        surfaces = []
        for name, solid in (("wheelF", "wheel_fl"), ("wheelR", "wheel_rl")):      # the +y wheels
            w = self.to_car_frame(self.wheel_meshes[solid])
            w.apply_translation([0, 0, -WHEEL_SINK_MM / 1e3])
            CI.write_ascii_named(w, out / f"{name}.stl", name, self.wheel_meshes[solid].volume * 1e-9)
            c = w.bounds.mean(0)
            surfaces.append({"name": name, "stl": f"{name}.stl", "rotating": {
                "origin": [float(c[0]), float(c[1]), float(s.r_wheel - WHEEL_SINK_MM) / 1e3], "axis": [0, 1, 0], "omega": omega}})
        (out / "assembly.json").write_text(json.dumps({"extra_surfaces": surfaces, "label": label}, indent=1))
        m = self.mass(body_mesh)
        (out / "mass_report.json").write_text(json.dumps({
            "car_weight_kg": m["race_mass_g"] / 1e3, "com_mm": [m["com_x_car_mm"], 0.0, m["com_z_mm"]],
            "foam_g": m["foam_g"], "lead_g": m["lead_g"], "car_without_cartridge_g": m["car_g"],
            "note": "sidepod_opt: foam from the exact body mesh; other parts ASSUMED (see CarSpec)"}, indent=1))
        return out
