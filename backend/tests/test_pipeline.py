"""End-to-end pipeline scenarios driven with synthetic frames and sensor readings."""

from typing import Callable, List, Optional

import pytest

from app.pipeline import MAIN_FLOW, Pipeline, SensorReading, State

DT = 0.1  # 10 inferred frames / sensor ticks per second


def fire_box(conf=0.8):
    return [{"x1": 400, "y1": 200, "x2": 520, "y2": 330, "conf": conf, "label": "fire", "kind": "fire"}]


def reading(smoke=False, ppm=None, dist: Optional[float] = 4.0):
    return SensorReading(smoke_ppm=ppm if ppm is not None else (450.0 if smoke else 60.0), smoke_triggered=smoke,
                         smoke_adc=None, lidar_distance_m=dist, lidar_valid=dist is not None, lidar_strength=1500)


class Driver:
    def __init__(self, cfg):
        self.p = Pipeline(cfg)
        self.t = 1000.0
        self.states: List[str] = [self.p.state.value]
        self.events: List[dict] = []
        self.max_valve = 0.0

    def run(self, seconds: float, frame: Callable[["Driver"], list], sense: Callable[["Driver"], SensorReading],
            until: Optional[State] = None) -> None:
        end = self.t + seconds
        while self.t < end:
            self.p.on_frame(frame(self), 960, 540, self.t)
            self.p.on_tick(sense(self), self.t, DT)
            self.max_valve = max(self.max_valve, self.p.valve)
            self.events += self.p.drain_events()
            if self.p.state.value != self.states[-1]:
                self.states.append(self.p.state.value)
            self.t += DT
            if until is not None and self.p.state == until:
                return

    @property
    def incidents(self):
        return [e["incident"] for e in self.events if e["type"] == "incident"]


def test_full_detection_to_suppression_flow(cfg):
    d = Driver(cfg)
    d.run(2, lambda d: [], lambda d: reading())
    assert d.p.state == State.MONITORING
    fire_on = {"v": True}
    t_fire = d.t
    # smoke reaches the sensor 3 s after ignition
    sense = lambda d: reading(smoke=d.t - t_fire > 3.0)
    frame = lambda d: fire_box() if fire_on["v"] else []
    d.run(30, frame, sense, until=State.SUPPRESSION_ACTIVE)
    assert d.p.state == State.SUPPRESSION_ACTIVE
    h = d.p.hydraulics
    assert h["reachable"] and h["within_pump_capacity"] and h["pump_pressure_bar"] > 0
    assert d.p.distance["median_m"] == pytest.approx(4.0)
    assert d.p.aiming is not None and d.p.fire_size["area_m2"] > 0
    d.run(3, frame, sense)
    assert d.p.valve > 0.9 and d.p.flow_lpm > 0 and d.p.water_l > 0
    fire_on["v"] = False  # water knocked the fire down - YOLO no longer sees it
    d.run(20, frame, lambda d: reading(smoke=False), until=State.SUPPRESSION_COMPLETE)
    assert d.p.state == State.SUPPRESSION_COMPLETE
    assert d.states == [s.value for s in MAIN_FLOW]  # every stage, in order
    inc = d.incidents[-1]
    assert inc["outcome"] == "EXTINGUISHED"
    m = inc["metrics"]
    assert m["t_detect_s"] == 0.0
    assert 0 < m["t_confirmed_s"] < m["t_suppression_s"] < m["t_extinguished_s"]
    assert m["water_used_l"] > 0 and m["peak_confidence"] == pytest.approx(0.8)
    snap = d.p.snapshot(d.t)
    assert all(s["status"] == "done" for s in snap["stages"])
    # residual smoke lingers after extinguishing: re-arm without raising a smoke-only alert
    d.run(cfg.COOLDOWN_S + 2, lambda d: [], lambda d: reading(smoke=True, ppm=700))
    assert d.p.state == State.MONITORING
    d.run(5, lambda d: [], lambda d: reading(smoke=True, ppm=600))
    assert d.p.state == State.MONITORING
    assert "Residual smoke" in d.p.narration(d.t, 10)
    transitions = [e for e in d.events if e["type"] == "transition"]
    assert transitions[-1]["to"] == "MONITORING"
    # once the smoke has cleared, a new smoke-only event is reported again
    d.run(1, lambda d: [], lambda d: reading(smoke=False))
    d.run(4, lambda d: [], lambda d: reading(smoke=True, ppm=600))
    assert d.p.state == State.SMOKE_ONLY_ALERT


def test_flash_is_rejected_as_false_alarm(cfg):
    d = Driver(cfg)
    d.run(1, lambda d: [], lambda d: reading())
    start = d.t
    d.run(6, lambda d: fire_box() if d.t - start < 0.5 else [], lambda d: reading())
    assert State.FALSE_ALARM_REJECTED.value in d.states
    assert State.SENSOR_FUSION.value not in d.states
    assert d.max_valve == 0.0
    assert d.incidents[-1]["outcome"] == "FALSE_ALARM_REJECTED"
    d.run(4, lambda d: [], lambda d: reading())
    assert d.p.state == State.MONITORING


def test_flickering_detection_times_out(cfg):
    d = Driver(cfg)
    counter = {"i": 0}

    def flicker(d):
        counter["i"] += 1
        return fire_box() if counter["i"] % 2 else []

    d.run(8, flicker, lambda d: reading())
    assert State.FALSE_ALARM_REJECTED.value in d.states
    assert "not persistent" in d.incidents[-1]["reason"]


def test_slow_ai_frame_rate_delays_but_does_not_reject_real_fire(cfg):
    """On a slow laptop YOLO may run at ~1 fps: validation must wait for frames, not time out."""
    p = Pipeline(cfg)
    t, states = 1000.0, []
    for step in range(400):  # 40 s, one inferred frame per second
        if step % 10 == 0:
            p.on_frame(fire_box(), 960, 540, t)
        p.on_tick(reading(smoke=step > 30), t, DT)
        if not states or states[-1] != p.state.value:
            states.append(p.state.value)
        t += DT
    assert State.FALSE_ALARM_REJECTED.value not in states
    assert State.FIRE_CONFIRMED.value in states


def test_vision_without_smoke_alerts_operator_and_withholds_water(cfg):
    d = Driver(cfg)
    d.run(25, lambda d: fire_box(), lambda d: reading(smoke=False))
    assert d.p.state == State.VISION_ONLY_ALERT
    assert d.max_valve == 0.0
    snap = d.p.snapshot(d.t)
    assert next(s for s in snap["stages"] if s["key"] == "SENSOR_FUSION")["status"] == "failed"
    # smoke arrives late -> confirmed after all
    d.run(3, lambda d: fire_box(), lambda d: reading(smoke=True))
    assert State.FIRE_CONFIRMED.value in d.states


def test_smoke_without_flames_alerts_operator(cfg):
    d = Driver(cfg)
    d.run(4, lambda d: [], lambda d: reading(smoke=True, ppm=600))
    assert d.p.state == State.SMOKE_ONLY_ALERT
    assert d.max_valve == 0.0
    d.run(5, lambda d: [], lambda d: reading(smoke=False))
    assert d.p.state == State.MONITORING
    assert d.incidents[-1]["outcome"] == "SMOKE_ONLY_ALERT"


def test_lidar_failure_escalates(cfg):
    d = Driver(cfg)
    d.run(30, lambda d: fire_box(), lambda d: reading(smoke=True, dist=None), until=State.ESCALATED)
    assert d.p.state == State.ESCALATED
    assert "LiDAR" in d.p.reason
    assert d.max_valve == 0.0


def test_target_beyond_pump_capacity_escalates(cfg):
    cfg.MIN_PRESSURE, cfg.MAX_PRESSURE = 0.1, 0.6
    d = Driver(cfg)
    d.run(30, lambda d: fire_box(), lambda d: reading(smoke=True, dist=7.5), until=State.ESCALATED)
    assert d.p.state == State.ESCALATED
    assert "exceeds pump maximum" in d.p.reason
    assert d.incidents[-1]["outcome"] == "ESCALATED"


def test_reflash_during_verification_resumes_suppression(cfg):
    d = Driver(cfg)
    fire = {"v": True}
    d.run(30, lambda d: fire_box() if fire["v"] else [], lambda d: reading(smoke=True), until=State.SUPPRESSION_ACTIVE)
    fire["v"] = False
    d.run(10, lambda d: fire_box() if fire["v"] else [], lambda d: reading(smoke=True), until=State.VERIFICATION)
    assert d.p.state == State.VERIFICATION
    fire["v"] = True
    d.run(1, lambda d: fire_box() if fire["v"] else [], lambda d: reading(smoke=True))
    assert d.p.state == State.SUPPRESSION_ACTIVE and d.p.reflash_count == 1


def test_suppression_timeout_escalates(cfg):
    cfg.SUPPRESSION_MAX_S = 5
    d = Driver(cfg)
    d.run(40, lambda d: fire_box(), lambda d: reading(smoke=True), until=State.ESCALATED)
    assert d.p.state == State.ESCALATED and "not knocked down" in d.p.reason


def test_reset_aborts_running_incident(cfg):
    d = Driver(cfg)
    d.run(3, lambda d: fire_box(), lambda d: reading())
    assert d.p.incident is not None
    d.p.reset(d.t)
    ev = d.p.drain_events()
    assert any(e["type"] == "incident" and e["incident"]["outcome"] == "ABORTED" for e in ev)
    assert d.p.state == State.MONITORING and d.p.incident is None


def test_narration_available_for_every_state(cfg):
    p = Pipeline(cfg)
    for st in State:
        p.state = st
        assert isinstance(p.narration(0.0, 12.0), str)
