import math

import pytest

from app import physics
from app.physics import G, HydraulicParams, estimate_pressure


def test_horizontal_distance_pythagoras():
    assert physics.horizontal_distance(5.0, 3.0) == pytest.approx(4.0)
    assert physics.horizontal_distance(2.0, 3.0) == 0.0  # target directly below


@pytest.mark.parametrize("d,dh,angle", [(3.0, 2.2, 30), (6.0, 2.2, 15), (4.0, 0.5, 45), (5.0, 2.0, 0)])
def test_jet_velocity_hits_target(d, dh, angle):
    v = physics.jet_velocity(d, dh, angle)
    t = math.radians(angle)
    y = d * math.tan(t) - G * d ** 2 / (2 * v ** 2 * math.cos(t) ** 2)
    assert y == pytest.approx(-dh, abs=1e-9)


def test_jet_velocity_unreachable_when_aimed_too_low():
    # aimed 60 deg downward cannot reach 5 m away while dropping only 1 m
    assert physics.jet_velocity(5.0, 1.0, -60) is None


def test_friction_factor_regimes():
    assert physics.friction_factor(1000, 0) == pytest.approx(0.064)
    # smooth pipe, Re = 1e5 -> ~0.018 (Moody chart)
    assert physics.friction_factor(1e5, 1e-6) == pytest.approx(0.018, abs=0.001)


def test_pressure_components_add_up():
    r = estimate_pressure(4.0, HydraulicParams(), fire_area_m2=0.5)
    assert r.reachable and r.within_pump_capacity
    total = r.nozzle_pressure_bar + r.friction_loss_bar + r.minor_loss_bar + r.elevation_loss_bar
    assert r.pump_pressure_bar == pytest.approx(total, abs=0.01)
    assert r.pump_pressure_psi == pytest.approx(r.pump_pressure_bar * 14.5038, abs=0.05)
    assert r.trajectory[0]["y"] == pytest.approx(2.5)
    assert r.trajectory[-1]["y"] == pytest.approx(0.3, abs=1e-3)  # lands on the aim point
    assert r.required_flow_lpm == pytest.approx(6.1 * 0.5)
    assert r.optimal_angle_deg is not None and r.optimal_pump_pressure_bar <= r.pump_pressure_bar + 1e-9


def test_pressure_increases_with_distance():
    p = HydraulicParams()
    pressures = [estimate_pressure(d, p).pump_pressure_bar for d in (3.0, 4.0, 5.0, 6.0, 7.0)]
    assert pressures == sorted(pressures)


def test_out_of_pump_capacity_is_flagged():
    r = estimate_pressure(7.5, HydraulicParams(max_pressure_bar=0.6, min_pressure_bar=0.1))
    assert r.reachable and not r.within_pump_capacity
    assert "exceeds pump maximum" in r.reason
    assert r.command_pressure_bar == pytest.approx(0.6)


def test_too_close_is_unreachable():
    r = estimate_pressure(2.0, HydraulicParams())  # slant 2.0 < 2.2 m height difference
    assert not r.reachable and r.reason


def test_fire_size_and_aiming_pinhole():
    # 90 deg HFOV -> focal length = W/2 -> an object half the image wide at d metres is d metres wide
    size = physics.fire_size(480, 240, 960, 4.0, 90)
    assert size["width_m"] == pytest.approx(4.0)
    assert size["height_m"] == pytest.approx(2.0)
    assert size["area_m2"] == pytest.approx(math.pi * 4.0, abs=0.01)
    centre = physics.aim_angles(480, 270, 960, 540, 70)
    assert centre["pan_deg"] == 0 and centre["tilt_deg"] == 0
    edge = physics.aim_angles(960, 270, 960, 540, 70)
    assert edge["pan_deg"] == pytest.approx(35.0, abs=0.01)
    up = physics.aim_angles(480, 0, 960, 540, 70)
    assert up["tilt_deg"] > 0
