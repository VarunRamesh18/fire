import random

import pytest

from app.hardware import parse_line
from app.simulation import BACKGROUND_DISTANCE_M, FireScene, LidarSim, SmokeSensorSim


@pytest.fixture(autouse=True)
def seed():
    random.seed(1)


def test_smoke_sensor_delay_rise_and_hysteresis():
    s = SmokeSensorSim()
    t, dt = 0.0, 0.1
    readings = []
    while t < 20:
        src = 1000.0 if t < 10 else 0.0
        readings.append((t, s.update(t, dt, src, delay=3.0, tau=3.5, threshold=300, hysteresis=50)))
        t += dt
    before = [r for tt, r in readings if tt < 2.9]
    assert all(not r["triggered"] and r["ppm"] < 120 for r in before)  # smoke has not arrived yet
    first = next(tt for tt, r in readings if r["triggered"])
    assert 3.0 < first < 6.0
    assert max(r["ppm"] for _, r in readings) > 800
    assert all(0 <= r["adc"] <= 1023 for _, r in readings)
    # alarm stays on briefly after the source stops (transport delay + slow clearing)
    assert next(r for tt, r in readings if tt >= 12.0)["triggered"]


def test_lidar_noise_and_range_limits():
    lidar = LidarSim()
    near = [lidar.sample(0, 4.0, 60) for _ in range(500)]
    valid = [s.distance_m for s in near if s.valid]
    assert len(valid) > 450  # ~1 % dropouts
    assert all(abs(d - 4.0) < 0.15 for d in valid)
    far = [lidar.sample(0, 9.0, 60) for _ in range(50)]
    assert not any(s.valid for s in far)  # beyond TF-Luna 8 m range
    smoky = [lidar.sample(0, 4.0, 4000) for _ in range(500)]
    assert sum(s.valid for s in smoky) < len(valid)  # smoke attenuates the return


def test_fire_scene_water_knocks_fire_down(tmp_path):
    scene = FireScene(tmp_path, 4.0)
    scene.ignite(0.0)
    assert scene.fire_present and scene.smoke_source_ppm(0.0, 1400) > 0
    t, dt = 0.0, 0.1
    for _ in range(50):  # 5 s without water: fire grows
        scene.tick(t, dt, knockdown_ref_s=8.0)
        t += dt
    grown = scene.intensity
    assert grown > 0.55
    scene.apply_water(flow_lpm=20.0, required_lpm=20.0, pressure_ratio=1.0)
    while scene.mode == "fire" and t < 60:
        scene.tick(t, dt, knockdown_ref_s=8.0)
        t += dt
    assert scene.mode == "extinguished"
    assert 5.0 < t - 5.0 < 20.0  # ~ln(intensity/0.04)/k seconds at the design flow
    assert scene.water_applied_l > 0
    assert scene.lidar_target_m(True) == 4.0 and scene.lidar_target_m(False) == BACKGROUND_DISTANCE_M


def test_low_flow_extinguishes_slower(tmp_path):
    def time_to_extinguish(ratio):
        s = FireScene(tmp_path, 4.0)
        s.ignite(0.0)
        s.apply_water(10.0 * ratio, 10.0, 1.0)
        t = 0.0
        while s.mode == "fire" and t < 120:
            s.tick(t, 0.1, 8.0)
            t += 0.1
        assert s.mode == "extinguished"
        return t
    assert time_to_extinguish(0.5) > time_to_extinguish(1.0) * 1.5


def test_false_alarm_and_smoke_injection(tmp_path):
    s = FireScene(tmp_path, 4.0)
    s.false_alarm(0.0, 0.5)
    assert s.mode == "false_alarm" and s.smoke_source_ppm(0.0, 1400) == 0
    s.tick(0.6, 0.6, 8.0)
    assert s.mode == "normal"
    s.inject_smoke(1.0, 5.0)
    assert s.smoke_source_ppm(4.0, 1400) == pytest.approx(750)
    s.tick(7.0, 0.1, 8.0)
    assert s.smoke_source_ppm(7.0, 1400) == 0


def test_arduino_line_parser():
    assert parse_line("SMOKE:1,DIST:2.45") == {"smoke": True, "dist": 2.45}
    assert parse_line("SMOKE:0,PPM:120,DIST:3.1,STR:1830\r\n") == {"smoke": False, "ppm": 120.0, "dist": 3.1,
                                                                   "strength": 1830}
    assert parse_line("garbage") is None
    assert parse_line("SMOKE:1,DIST:abc") == {"smoke": True}
