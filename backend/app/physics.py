"""
FireGuard AI - Physics models for distance, fire size, aiming and hydraulics.

Everything here is a pure function of its inputs so it can be unit-tested and
explained step by step on the dashboard.

Pressure estimation chain
-------------------------
1. Geometry      d  = sqrt(L^2 - dh^2)                 LiDAR slant range L -> horizontal distance d
2. Projectile    v0 = sqrt(g d^2 / (2 cos^2(t) (dh + d tan t)))
                 (water jet leaving the nozzle at angle t must drop dh over distance d)
3. Drag margin   v  = v0 (1 + drag_margin)
4. Nozzle        P_n = 1/2 rho (v / Cv)^2               Bernoulli across the nozzle
                 Q   = Cd A_n v                          volumetric flow
5. Pipe losses   dP_f = f (L_p / D_p) 1/2 rho V^2        Darcy-Weisbach, f from Swamee-Jain
                 dP_m = K 1/2 rho V^2                    fittings + valve
                 dP_z = rho g dz                         lift from pump to nozzle
6. Pump          P_pump = P_n + dP_f + dP_m + dP_z
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

G = 9.80665          # m/s^2
RHO = 998.2          # kg/m^3, water at 20 C
MU = 1.002e-3        # Pa.s, water at 20 C
PA_PER_BAR = 1e5
PSI_PER_BAR = 14.5038


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def horizontal_distance(slant_m: float, height_diff_m: float) -> float:
    """Horizontal distance from the LiDAR slant range and the height difference."""
    if slant_m <= abs(height_diff_m):
        return 0.0
    return math.sqrt(slant_m ** 2 - height_diff_m ** 2)


def aim_angles(cx_px: float, cy_px: float, width_px: int, height_px: int, hfov_deg: float) -> Dict[str, float]:
    """Pan/tilt angles (deg) that point the nozzle/LiDAR at pixel (cx, cy) - pinhole camera model."""
    f_px = (width_px / 2) / math.tan(math.radians(hfov_deg) / 2)
    pan = math.degrees(math.atan((cx_px - width_px / 2) / f_px))
    tilt = -math.degrees(math.atan((cy_px - height_px / 2) / f_px))
    vfov = math.degrees(2 * math.atan((height_px / 2) / f_px))
    return {"pan_deg": round(pan, 2), "tilt_deg": round(tilt, 2), "focal_px": round(f_px, 1), "vfov_deg": round(vfov, 1)}


def fire_size(bbox_w_px: float, bbox_h_px: float, width_px: int, distance_m: float, hfov_deg: float) -> Dict[str, float]:
    """Real-world flame size from its bounding box and distance (pinhole model).

    The burning area is modelled as a circular pool whose diameter equals the flame width.
    """
    f_px = (width_px / 2) / math.tan(math.radians(hfov_deg) / 2)
    w_m = bbox_w_px * distance_m / f_px
    h_m = bbox_h_px * distance_m / f_px
    area = math.pi * w_m ** 2 / 4
    return {"width_m": round(w_m, 2), "height_m": round(h_m, 2), "area_m2": round(area, 2)}


# ---------------------------------------------------------------------------
# Hydraulics
# ---------------------------------------------------------------------------


@dataclass
class HydraulicParams:
    nozzle_height_m: float = 2.5
    target_height_m: float = 0.3
    nozzle_angle_deg: float = 30.0
    nozzle_diameter_mm: float = 8.0
    nozzle_cd: float = 0.96
    nozzle_cv: float = 0.98
    pipe_length_m: float = 6.0
    pipe_diameter_mm: float = 20.0
    pipe_roughness_mm: float = 0.0015
    minor_loss_k: float = 4.0
    pump_elevation_m: float = 2.5
    drag_margin: float = 0.10
    min_pressure_bar: float = 0.5
    max_pressure_bar: float = 8.0
    design_density_lpm_m2: float = 6.1

    @classmethod
    def from_settings(cls, s: Any) -> "HydraulicParams":
        return cls(
            nozzle_height_m=s.NOZZLE_HEIGHT_M, target_height_m=s.TARGET_HEIGHT_M,
            nozzle_angle_deg=s.NOZZLE_ANGLE_DEG, nozzle_diameter_mm=s.NOZZLE_DIAMETER_MM,
            nozzle_cd=s.NOZZLE_CD, nozzle_cv=s.NOZZLE_CV, pipe_length_m=s.PIPE_LENGTH_M,
            pipe_diameter_mm=s.PIPE_DIAMETER_MM, pipe_roughness_mm=s.PIPE_ROUGHNESS_MM,
            minor_loss_k=s.MINOR_LOSS_K, pump_elevation_m=s.PUMP_ELEVATION_M, drag_margin=s.DRAG_MARGIN,
            min_pressure_bar=s.MIN_PRESSURE, max_pressure_bar=s.MAX_PRESSURE,
            design_density_lpm_m2=s.DESIGN_DENSITY_LPM_M2,
        )


@dataclass
class HydraulicResult:
    reachable: bool
    reason: Optional[str]
    slant_distance_m: float
    horizontal_distance_m: float
    height_drop_m: float
    angle_deg: float
    jet_velocity_ideal_ms: float = 0.0
    jet_velocity_ms: float = 0.0
    time_of_flight_s: float = 0.0
    apex_height_m: float = 0.0
    nozzle_pressure_bar: float = 0.0
    flow_lpm: float = 0.0
    pipe_velocity_ms: float = 0.0
    reynolds: float = 0.0
    friction_factor: float = 0.0
    friction_loss_bar: float = 0.0
    minor_loss_bar: float = 0.0
    elevation_loss_bar: float = 0.0
    pump_pressure_bar: float = 0.0
    pump_pressure_psi: float = 0.0
    command_pressure_bar: float = 0.0
    within_pump_capacity: bool = True
    required_flow_lpm: Optional[float] = None
    flow_ratio: Optional[float] = None
    est_knockdown_s: Optional[float] = None
    optimal_angle_deg: Optional[float] = None
    optimal_pump_pressure_bar: Optional[float] = None
    trajectory: List[Dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def friction_factor(reynolds: float, rel_roughness: float) -> float:
    """Darcy friction factor: laminar 64/Re, turbulent Swamee-Jain."""
    if reynolds <= 0:
        return 0.0
    if reynolds < 2300:
        return 64.0 / reynolds
    return 0.25 / (math.log10(rel_roughness / 3.7 + 5.74 / reynolds ** 0.9)) ** 2


def jet_velocity(d: float, dh: float, angle_deg: float) -> Optional[float]:
    """Launch speed for a projectile to travel horizontal ``d`` while dropping ``dh``.

    y(x) = x tan(t) - g x^2 / (2 v^2 cos^2 t);  require y(d) = -dh.
    Returns None when no launch speed reaches the target at this angle.
    """
    t = math.radians(angle_deg)
    denom = 2 * math.cos(t) ** 2 * (dh + d * math.tan(t))
    if d <= 0 or denom <= 0:
        return None
    return math.sqrt(G * d ** 2 / denom)


def _pump_pressure(v: float, dh_lift: float, p: HydraulicParams) -> Dict[str, float]:
    a_n = math.pi * (p.nozzle_diameter_mm / 1000) ** 2 / 4
    a_p = math.pi * (p.pipe_diameter_mm / 1000) ** 2 / 4
    q = p.nozzle_cd * a_n * v                                   # m^3/s
    v_pipe = q / a_p
    # static pressure upstream of the nozzle needed to accelerate pipe flow to jet speed
    p_noz = 0.5 * RHO * ((v / p.nozzle_cv) ** 2 - v_pipe ** 2)
    re = RHO * v_pipe * (p.pipe_diameter_mm / 1000) / MU
    f = friction_factor(re, p.pipe_roughness_mm / p.pipe_diameter_mm)
    dyn = 0.5 * RHO * v_pipe ** 2
    dp_f = f * (p.pipe_length_m / (p.pipe_diameter_mm / 1000)) * dyn
    dp_m = p.minor_loss_k * dyn
    dp_z = RHO * G * dh_lift
    total = p_noz + dp_f + dp_m + dp_z
    return {
        "q": q, "v_pipe": v_pipe, "p_noz": p_noz, "re": re, "f": f,
        "dp_f": dp_f, "dp_m": dp_m, "dp_z": dp_z, "total": total,
    }


def estimate_pressure(
    slant_distance_m: float,
    p: HydraulicParams,
    fire_area_m2: Optional[float] = None,
    knockdown_ref_s: float = 8.0,
) -> HydraulicResult:
    """Full pressure estimate for a fire at LiDAR slant range ``slant_distance_m``."""
    dh = p.nozzle_height_m - p.target_height_m
    d = horizontal_distance(slant_distance_m, dh)
    base = dict(
        slant_distance_m=round(slant_distance_m, 3), horizontal_distance_m=round(d, 3),
        height_drop_m=round(dh, 3), angle_deg=p.nozzle_angle_deg,
    )
    if d < 0.3:
        return HydraulicResult(reachable=False, reason="Target too close / directly below nozzle", **base)
    v0 = jet_velocity(d, dh, p.nozzle_angle_deg)
    if v0 is None:
        return HydraulicResult(reachable=False, reason="Target unreachable at this nozzle angle", **base)

    v = v0 * (1 + p.drag_margin)
    r = _pump_pressure(v, p.pump_elevation_m, p)
    pump_bar = r["total"] / PA_PER_BAR
    t = math.radians(p.nozzle_angle_deg)
    tof = d / (v0 * math.cos(t))
    apex = p.nozzle_height_m + (v0 * math.sin(t)) ** 2 / (2 * G) if p.nozzle_angle_deg > 0 else p.nozzle_height_m

    # trajectory (ideal, drag-free) in fire-base coordinates for plotting
    traj = []
    for i in range(25):
        x = d * i / 24
        y = p.nozzle_height_m + x * math.tan(t) - G * x ** 2 / (2 * v0 ** 2 * math.cos(t) ** 2)
        traj.append({"x": round(x, 3), "y": round(y, 3)})

    # angle that needs the least pump pressure (for the report)
    best_angle, best_p = None, None
    for a in range(0, 71):
        va = jet_velocity(d, dh, a)
        if va is None:
            continue
        pa = _pump_pressure(va * (1 + p.drag_margin), p.pump_elevation_m, p)["total"] / PA_PER_BAR
        if best_p is None or pa < best_p:
            best_angle, best_p = a, pa

    flow_lpm = r["q"] * 60_000
    req_flow = flow_ratio = knock = None
    if fire_area_m2 is not None and fire_area_m2 > 0:
        req_flow = p.design_density_lpm_m2 * fire_area_m2
        flow_ratio = flow_lpm / req_flow if req_flow > 0 else None
        if flow_ratio:
            knock = knockdown_ref_s / min(flow_ratio, 3.0)

    within = pump_bar <= p.max_pressure_bar
    return HydraulicResult(
        reachable=True,
        reason=None if within else f"Required {pump_bar:.2f} bar exceeds pump maximum {p.max_pressure_bar:.1f} bar",
        jet_velocity_ideal_ms=round(v0, 3),
        jet_velocity_ms=round(v, 3),
        time_of_flight_s=round(tof, 3),
        apex_height_m=round(apex, 3),
        nozzle_pressure_bar=round(r["p_noz"] / PA_PER_BAR, 3),
        flow_lpm=round(flow_lpm, 2),
        pipe_velocity_ms=round(r["v_pipe"], 3),
        reynolds=round(r["re"]),
        friction_factor=round(r["f"], 5),
        friction_loss_bar=round(r["dp_f"] / PA_PER_BAR, 4),
        minor_loss_bar=round(r["dp_m"] / PA_PER_BAR, 4),
        elevation_loss_bar=round(r["dp_z"] / PA_PER_BAR, 4),
        pump_pressure_bar=round(pump_bar, 3),
        pump_pressure_psi=round(pump_bar * PSI_PER_BAR, 2),
        command_pressure_bar=round(min(max(pump_bar, p.min_pressure_bar), p.max_pressure_bar), 3),
        within_pump_capacity=within,
        required_flow_lpm=round(req_flow, 2) if req_flow is not None else None,
        flow_ratio=round(flow_ratio, 3) if flow_ratio is not None else None,
        est_knockdown_s=round(knock, 1) if knock is not None else None,
        optimal_angle_deg=best_angle,
        optimal_pump_pressure_bar=round(best_p, 3) if best_p is not None else None,
        trajectory=traj,
        **base,
    )
