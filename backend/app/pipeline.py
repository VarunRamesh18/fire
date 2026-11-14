"""
FireGuard AI - Detection-to-suppression decision pipeline.

Main flow (each stage is shown on the dashboard):

  MONITORING
    -> FIRE_DETECTED          YOLOv8 reports a fire box above the confidence threshold
    -> TEMPORAL_VALIDATION    fire persists in K of the last N frames, boxes overlap
    -> SENSOR_FUSION          MQ-2 smoke sensor must corroborate the camera
    -> FIRE_CONFIRMED         two independent sources agree - alarm, aim pan/tilt
    -> DISTANCE_ESTIMATION    TF-Luna LiDAR samples, median filtered
    -> PRESSURE_ESTIMATION    projectile + Bernoulli + Darcy-Weisbach -> pump pressure
    -> SUPPRESSION_ACTIVE     valve open, closed loop until YOLO sees no fire
    -> VERIFICATION           fire absent for N frames, post-wetting
    -> SUPPRESSION_COMPLETE   valve closed, incident report, re-arm

Side outcomes:
  FALSE_ALARM_REJECTED  detection did not persist (flash, reflection) or vanished
  VISION_ONLY_ALERT     camera sees fire, smoke sensor never confirms -> operator verifies, no water
  SMOKE_ONLY_ALERT      smoke without visible flames -> operator verifies, no water
  ESCALATED             LiDAR failure, target out of reach, or fire not knocked down in time

The pipeline is deterministic given its inputs (frames + sensor readings + time),
so it is fully unit-tested without video or hardware.
"""

from __future__ import annotations

import math
import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from app import physics
from app.temporal import TemporalValidator


class State(str, Enum):
    MONITORING = "MONITORING"
    FIRE_DETECTED = "FIRE_DETECTED"
    TEMPORAL_VALIDATION = "TEMPORAL_VALIDATION"
    SENSOR_FUSION = "SENSOR_FUSION"
    FIRE_CONFIRMED = "FIRE_CONFIRMED"
    DISTANCE_ESTIMATION = "DISTANCE_ESTIMATION"
    PRESSURE_ESTIMATION = "PRESSURE_ESTIMATION"
    SUPPRESSION_ACTIVE = "SUPPRESSION_ACTIVE"
    VERIFICATION = "VERIFICATION"
    SUPPRESSION_COMPLETE = "SUPPRESSION_COMPLETE"
    FALSE_ALARM_REJECTED = "FALSE_ALARM_REJECTED"
    VISION_ONLY_ALERT = "VISION_ONLY_ALERT"
    SMOKE_ONLY_ALERT = "SMOKE_ONLY_ALERT"
    ESCALATED = "ESCALATED"


MAIN_FLOW: List[State] = [
    State.MONITORING, State.FIRE_DETECTED, State.TEMPORAL_VALIDATION, State.SENSOR_FUSION,
    State.FIRE_CONFIRMED, State.DISTANCE_ESTIMATION, State.PRESSURE_ESTIMATION,
    State.SUPPRESSION_ACTIVE, State.VERIFICATION, State.SUPPRESSION_COMPLETE,
]
ALERT_STATES = {State.FALSE_ALARM_REJECTED, State.VISION_ONLY_ALERT, State.SMOKE_ONLY_ALERT, State.ESCALATED}
SPRAY_STATES = {State.SUPPRESSION_ACTIVE, State.VERIFICATION}
AIMED_STATES = {State.FIRE_CONFIRMED, State.DISTANCE_ESTIMATION, State.PRESSURE_ESTIMATION,
                State.SUPPRESSION_ACTIVE, State.VERIFICATION}

STAGE_INFO: Dict[State, Dict[str, str]] = {
    State.MONITORING: {"title": "Monitoring", "tag": "SYSTEM"},
    State.FIRE_DETECTED: {"title": "YOLOv8 Fire Detection", "tag": "AI"},
    State.TEMPORAL_VALIDATION: {"title": "Temporal Validation", "tag": "AI"},
    State.SENSOR_FUSION: {"title": "Smoke Sensor Corroboration", "tag": "SENSOR"},
    State.FIRE_CONFIRMED: {"title": "Fire Confirmed - Alarm", "tag": "SYSTEM"},
    State.DISTANCE_ESTIMATION: {"title": "LiDAR Distance Estimation", "tag": "SENSOR"},
    State.PRESSURE_ESTIMATION: {"title": "Pressure Estimation", "tag": "PHYSICS"},
    State.SUPPRESSION_ACTIVE: {"title": "Suppression Active", "tag": "ACTUATOR"},
    State.VERIFICATION: {"title": "Extinguishment Verification", "tag": "AI"},
    State.SUPPRESSION_COMPLETE: {"title": "Suppression Complete", "tag": "SYSTEM"},
    State.FALSE_ALARM_REJECTED: {"title": "False Alarm Rejected", "tag": "AI"},
    State.VISION_ONLY_ALERT: {"title": "Unconfirmed - Operator Check", "tag": "SYSTEM"},
    State.SMOKE_ONLY_ALERT: {"title": "Smoke Only - Operator Check", "tag": "SENSOR"},
    State.ESCALATED: {"title": "Escalated to Fire Services", "tag": "SYSTEM"},
}

# After a fire is put out, smoke/steam lingers. Smoke-only alarms are ignored until it has
# cleared once (or this long has passed); a visible fire still triggers immediately.
RESIDUAL_SMOKE_HOLDOFF_S = 120.0

OUTCOMES = {
    State.SUPPRESSION_COMPLETE: "EXTINGUISHED",
    State.FALSE_ALARM_REJECTED: "FALSE_ALARM_REJECTED",
    State.ESCALATED: "ESCALATED",
}


@dataclass
class SensorReading:
    smoke_ppm: Optional[float]
    smoke_triggered: bool
    smoke_adc: Optional[int]
    lidar_distance_m: Optional[float]
    lidar_valid: bool
    lidar_strength: Optional[int]
    online: bool = True


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


class Pipeline:
    def __init__(self, cfg: Any) -> None:
        self.cfg = cfg
        self.validator = TemporalValidator(cfg.TEMPORAL_WINDOW, cfg.TEMPORAL_MIN_POSITIVE, cfg.TEMPORAL_MIN_IOU)
        self._events: List[Dict[str, Any]] = []
        self._reset_all(0.0)

    # ------------------------------------------------------------------ setup
    def _reset_all(self, now: float) -> None:
        self.state = State.MONITORING
        self.state_since = now
        self.incident: Optional[Dict[str, Any]] = None
        self.last_incident: Optional[Dict[str, Any]] = None
        self.validator.reset()
        self.frame_count = 0
        self.detect_frame = 0
        self.frame_w, self.frame_h = 960, 540
        self.last_positive = False
        self.last_fire_det: Optional[Dict[str, Any]] = None
        self.last_box_det: Optional[Dict[str, Any]] = None
        self.reading: Optional[SensorReading] = None
        self.smoke_since: Optional[float] = None
        self.smoke_clear_since: Optional[float] = None
        self.smoke_holdoff_until: Optional[float] = None
        self.reason: Optional[str] = None
        self._reset_episode()

    def _reset_episode(self) -> None:
        self.lidar_buffer: List[float] = []
        self.distance: Optional[Dict[str, Any]] = None
        self.aiming: Optional[Dict[str, Any]] = None
        self.fire_size: Optional[Dict[str, Any]] = None
        self.hydraulics: Optional[Dict[str, Any]] = None
        self.valve = 0.0
        self.pump_bar = 0.0
        self.flow_lpm = 0.0
        self.water_l = 0.0
        self.suppression_started: Optional[float] = None
        self.clear_frames = 0
        self.positive_streak = 0
        self.peak_conf = 0.0
        self.reflash_count = 0

    def reconfigure(self) -> None:
        self.validator.configure(self.cfg.TEMPORAL_WINDOW, self.cfg.TEMPORAL_MIN_POSITIVE, self.cfg.TEMPORAL_MIN_IOU)

    def reset(self, now: float) -> None:
        """Presenter reset: abort any running incident and re-arm."""
        if self.incident is not None:
            self._close_incident(now, "ABORTED", "Reset by operator")
        last = self.last_incident
        prev = self.state
        self._reset_all(now)
        self.last_incident = last
        if prev != State.MONITORING:
            self._events.append({"type": "transition", "from": prev.value, "to": State.MONITORING.value,
                                 "at": _iso(now), "note": "Reset by operator", "incident_id": None})

    # ------------------------------------------------------------------ inputs
    def on_frame(self, detections: List[Dict[str, Any]], frame_w: int, frame_h: int, now: float) -> None:
        """One YOLO-inferred frame."""
        self.frame_count += 1
        self.frame_w, self.frame_h = frame_w, frame_h
        fire = [d for d in detections if d.get("kind", "fire") == "fire"]
        self.last_positive = self.validator.update(fire, self.cfg.CONFIDENCE_THRESHOLD)
        best = max(fire, key=lambda d: d["conf"], default=None)
        self.last_fire_det = best
        if self.last_positive:
            self.last_box_det = best
            if self.incident is not None:
                self.peak_conf = max(self.peak_conf, best["conf"])
            self.clear_frames = 0
            self.positive_streak += 1
        else:
            self.clear_frames += 1
            self.positive_streak = 0
        self._evaluate(now)

    def on_tick(self, reading: SensorReading, now: float, dt: float) -> None:
        """Periodic sensor update (also drives the valve / pump dynamics)."""
        self.reading = reading
        if (self.state == State.DISTANCE_ESTIMATION and reading.lidar_valid
                and reading.lidar_distance_m is not None and self._elapsed(now) > 0.4):
            self.lidar_buffer.append(reading.lidar_distance_m)
        self._actuators(now, dt)
        self._evaluate(now)

    # ------------------------------------------------------------------ actuators
    def _actuators(self, now: float, dt: float) -> None:
        spraying = self.state in SPRAY_STATES and self.hydraulics is not None
        target_valve = 1.0 if spraying else 0.0
        self.valve += (target_valve - self.valve) * min(1.0, dt / 0.8)        # ~1 s solenoid/ball valve
        if self.valve < 0.01:
            self.valve = 0.0
        cmd = self.hydraulics["command_pressure_bar"] if self.hydraulics else 0.0
        target_p = cmd if self.valve > 0.05 else 0.0
        self.pump_bar += (target_p - self.pump_bar) * (1 - math.exp(-dt / 0.7))  # pump spin-up
        design_flow = self.hydraulics["flow_lpm"] if self.hydraulics else 0.0
        if cmd > 0 and self.valve > 0:
            self.flow_lpm = design_flow * math.sqrt(max(self.pump_bar, 0) / cmd) * self.valve
        else:
            self.flow_lpm = 0.0
        self.water_l += self.flow_lpm * dt / 60

    @property
    def pressure_ratio(self) -> float:
        cmd = self.hydraulics["command_pressure_bar"] if self.hydraulics else 0.0
        return min(1.0, self.pump_bar / cmd) if cmd > 0 else 0.0

    @property
    def required_flow_lpm(self) -> Optional[float]:
        return self.hydraulics.get("required_flow_lpm") if self.hydraulics else None

    @property
    def aimed_at_fire(self) -> bool:
        return self.state in AIMED_STATES

    # ------------------------------------------------------------------ transitions
    def _elapsed(self, now: float) -> float:
        return now - self.state_since

    def _goto(self, new: State, now: float, note: Optional[str] = None) -> None:
        prev = self.state
        if new == prev:
            return
        self.state, self.state_since = new, now
        if new == State.FIRE_DETECTED:
            self.detect_frame = self.frame_count
        if new == State.SUPPRESSION_COMPLETE:
            self.smoke_holdoff_until = now + RESIDUAL_SMOKE_HOLDOFF_S
        if self.incident is None and new != State.MONITORING:
            self._open_incident(now)
        if self.incident is not None:
            self.incident["timeline"].append({
                "state": new.value, "at": _iso(now),
                "t": round(now - self.incident["_t0"], 2), "note": note,
            })
        self._events.append({"type": "transition", "from": prev.value, "to": new.value, "at": _iso(now),
                             "note": note, "incident_id": self.incident["id"] if self.incident else None,
                             "confidence": self.last_fire_det["conf"] if self.last_fire_det else 0.0,
                             "smoke_ppm": self.reading.smoke_ppm if self.reading else None,
                             "distance_m": self.distance["median_m"] if self.distance else None,
                             "pressure_bar": self.hydraulics["pump_pressure_bar"] if self.hydraulics else None})
        if new in OUTCOMES:
            self._close_incident(now, OUTCOMES[new], note)
        if new == State.MONITORING:
            self.validator.reset()
            self._reset_episode()
            self.reason = None

    def _evaluate(self, now: float) -> None:
        c = self.cfg
        dwell = c.STAGE_MIN_DWELL_S
        el = self._elapsed(now)
        r = self.reading
        smoke = bool(r and r.smoke_triggered)
        v = self.validator
        s = self.state

        if s == State.MONITORING:
            if self.smoke_holdoff_until is not None and (not smoke or now >= self.smoke_holdoff_until):
                self.smoke_holdoff_until = None  # residual smoke has cleared (or hold-off expired)
            if self.last_positive:
                self._goto(State.FIRE_DETECTED, now, self._det_note())
            elif smoke and self.smoke_holdoff_until is not None:
                self.smoke_since = None  # residual smoke/steam from the fire just put out - not a new incident
            elif smoke:
                self.smoke_since = self.smoke_since or now
                if now - self.smoke_since >= 2.0:
                    self._goto(State.SMOKE_ONLY_ALERT, now, f"Smoke {r.smoke_ppm:.0f} ppm, no flames visible")
            else:
                self.smoke_since = None

        elif s == State.FIRE_DETECTED:
            if el >= min(dwell, 1.0):
                self._goto(State.TEMPORAL_VALIDATION, now)

        elif s == State.TEMPORAL_VALIDATION:
            since_detect = now - self._stage_start(State.FIRE_DETECTED, now)
            frames_since = self.frame_count - self.detect_frame
            if v.passed and el >= dwell * 0.5:
                st = v.status()
                cons = f", IoU {st['consistency']:.2f}" if st["consistency"] is not None else ""
                self._goto(State.SENSOR_FUSION, now, f"{st['positives']}/{st['size']} frames positive{cons}")
            elif v.recent_positives(5) == 0 and frames_since >= 5:
                self.reason = "Detection vanished - transient flash or reflection, not a fire"
                self._goto(State.FALSE_ALARM_REJECTED, now, self.reason)
            # Judged on frames, not only wall time: on a slow CPU the decision is delayed, never wrong.
            elif frames_since >= 2 * v.window or (since_detect >= c.TEMPORAL_TIMEOUT_S and frames_since >= v.window):
                self.reason = (f"Only {v.positives}/{v.window} frames positive after {frames_since} frames"
                               " - detection not persistent")
                self._goto(State.FALSE_ALARM_REJECTED, now, self.reason)

        elif s == State.SENSOR_FUSION:
            if smoke and el >= dwell:
                self._goto(State.FIRE_CONFIRMED, now, f"Camera + MQ-2 agree ({r.smoke_ppm:.0f} ppm)")
            elif v.recent_positives(v.window) < max(1, v.min_positive // 3):
                self.reason = "Fire no longer visible before smoke confirmation"
                self._goto(State.FALSE_ALARM_REJECTED, now, self.reason)
            elif el >= c.SENSOR_FUSION_TIMEOUT_S:
                self.reason = f"No smoke corroboration within {c.SENSOR_FUSION_TIMEOUT_S:.0f}s"
                self._goto(State.VISION_ONLY_ALERT, now, self.reason)

        elif s == State.VISION_ONLY_ALERT:
            if smoke:
                self._goto(State.FIRE_CONFIRMED, now, f"Smoke arrived late ({r.smoke_ppm:.0f} ppm)")
            elif v.recent_positives(v.window) == 0:
                self._close_incident(now, "VISION_ONLY_ALERT", self.reason)
                self._goto(State.MONITORING, now, "Vision cleared")

        elif s == State.SMOKE_ONLY_ALERT:
            if self.last_positive:
                self._goto(State.FIRE_DETECTED, now, self._det_note())
            elif not smoke:
                self.smoke_clear_since = self.smoke_clear_since or now
                if now - self.smoke_clear_since >= 3.0:
                    self.smoke_clear_since = None
                    self._close_incident(now, "SMOKE_ONLY_ALERT", "Smoke cleared")
                    self._goto(State.MONITORING, now, "Smoke cleared")
            else:
                self.smoke_clear_since = None

        elif s == State.FIRE_CONFIRMED:
            if self.aiming is None:
                self.aiming = self._compute_aiming()
            if el >= dwell:
                self.lidar_buffer = []
                self._goto(State.DISTANCE_ESTIMATION, now)

        elif s == State.DISTANCE_ESTIMATION:
            if len(self.lidar_buffer) >= c.LIDAR_SAMPLES and el >= dwell:
                self._finish_distance()
                self._goto(State.PRESSURE_ESTIMATION, now,
                           f"{self.distance['median_m']:.2f} m (+/-{self.distance['std_m']:.2f})")
            elif el >= c.LIDAR_TIMEOUT_S + dwell:
                self.reason = (f"LiDAR returned only {len(self.lidar_buffer)} valid samples"
                               " - target out of range (0.2-8 m) or obscured")
                self._goto(State.ESCALATED, now, self.reason)

        elif s == State.PRESSURE_ESTIMATION:
            if self.hydraulics is None:
                self._compute_hydraulics()
            if el >= dwell:
                h = self.hydraulics
                if not h["reachable"] or not h["within_pump_capacity"]:
                    self.reason = h["reason"]
                    self._goto(State.ESCALATED, now, self.reason)
                else:
                    self.suppression_started = now
                    self._goto(State.SUPPRESSION_ACTIVE, now,
                               f"Pump {h['pump_pressure_bar']:.2f} bar, {h['flow_lpm']:.1f} L/min")

        elif s == State.SUPPRESSION_ACTIVE:
            if self.clear_frames >= c.VERIFY_CLEAR_FRAMES:
                self._goto(State.VERIFICATION, now, f"No fire for {self.clear_frames} frames")
            elif self.suppression_started and now - self.suppression_started >= c.SUPPRESSION_MAX_S:
                self.reason = f"Fire not knocked down within {c.SUPPRESSION_MAX_S:.0f}s"
                self._goto(State.ESCALATED, now, self.reason)

        elif s == State.VERIFICATION:
            if self.positive_streak >= 3:
                self.reflash_count += 1
                self._goto(State.SUPPRESSION_ACTIVE, now, "Re-flash detected - resuming suppression")
            elif el >= max(c.POST_WET_S, dwell) and self.clear_frames >= c.VERIFY_CLEAR_FRAMES:
                self._goto(State.SUPPRESSION_COMPLETE, now,
                           f"Extinguished - {self.water_l:.1f} L used")

        elif s == State.SUPPRESSION_COMPLETE:
            if el >= c.COOLDOWN_S and self.valve == 0.0:
                self._goto(State.MONITORING, now, "Re-armed")

        elif s == State.FALSE_ALARM_REJECTED:
            if el >= max(dwell, 3.0):
                self._goto(State.MONITORING, now, "Re-armed")

        elif s == State.ESCALATED:
            if el >= c.COOLDOWN_S and v.recent_positives(v.window) == 0 and not smoke:
                self._goto(State.MONITORING, now, "Re-armed")

    # ------------------------------------------------------------------ computations
    def _det_note(self) -> str:
        d = self.last_box_det or self.last_fire_det
        return f"'{d['label']}' {d['conf'] * 100:.0f}% at frame #{self.frame_count}" if d else ""

    def _compute_aiming(self) -> Optional[Dict[str, Any]]:
        d = self.last_box_det
        if d is None:
            return None
        cx, cy = (d["x1"] + d["x2"]) / 2, (d["y1"] + d["y2"]) / 2
        a = physics.aim_angles(cx, cy, self.frame_w, self.frame_h, self.cfg.CAMERA_HFOV_DEG)
        a.update({"target_px": [round(cx), round(cy)]})
        return a

    def _finish_distance(self) -> None:
        buf = self.lidar_buffer[-max(self.cfg.LIDAR_SAMPLES, 3):]
        med = statistics.median(buf)
        std = statistics.pstdev(buf) if len(buf) > 1 else 0.0
        dh = self.cfg.NOZZLE_HEIGHT_M - self.cfg.TARGET_HEIGHT_M
        self.distance = {
            "median_m": round(med, 3), "std_m": round(std, 3), "samples": [round(x, 2) for x in buf],
            "n": len(buf), "min_m": round(min(buf), 2), "max_m": round(max(buf), 2),
            "horizontal_m": round(physics.horizontal_distance(med, dh), 3),
        }
        d = self.last_box_det
        if d is not None:
            self.fire_size = physics.fire_size(d["x2"] - d["x1"], d["y2"] - d["y1"], self.frame_w, med,
                                               self.cfg.CAMERA_HFOV_DEG)

    def _compute_hydraulics(self) -> None:
        params = physics.HydraulicParams.from_settings(self.cfg)
        area = self.fire_size["area_m2"] if self.fire_size else None
        res = physics.estimate_pressure(self.distance["median_m"], params, area, self.cfg.KNOCKDOWN_REF_S)
        self.hydraulics = res.to_dict()

    # ------------------------------------------------------------------ incidents
    def _open_incident(self, now: float) -> None:
        self.incident = {
            "id": uuid.uuid4().hex[:8], "_t0": now, "started_at": _iso(now),
            "timeline": [{"state": State.MONITORING.value, "at": _iso(now), "t": 0.0, "note": "Armed"}],
        }

    def _stage_start(self, state: State, default: float) -> float:
        if self.incident is None:
            return default
        for e in self.incident["timeline"]:
            if e["state"] == state.value:
                return self.incident["_t0"] + e["t"]
        return default

    def _t_of(self, state: State) -> Optional[float]:
        if self.incident is None:
            return None
        for e in self.incident["timeline"]:
            if e["state"] == state.value:
                return e["t"]
        return None

    def _close_incident(self, now: float, outcome: str, note: Optional[str]) -> None:
        inc = self.incident
        if inc is None:
            return
        report = {
            "id": inc["id"], "started_at": inc["started_at"], "ended_at": _iso(now),
            "duration_s": round(now - inc["_t0"], 2), "outcome": outcome, "reason": note,
            "timeline": inc["timeline"],
            "metrics": {
                "peak_confidence": round(self.peak_conf, 3),
                "t_detect_s": self._t_of(State.FIRE_DETECTED),
                "t_validated_s": self._t_of(State.SENSOR_FUSION),
                "t_confirmed_s": self._t_of(State.FIRE_CONFIRMED),
                "t_suppression_s": self._t_of(State.SUPPRESSION_ACTIVE),
                "t_extinguished_s": self._t_of(State.VERIFICATION),
                "distance_m": self.distance["median_m"] if self.distance else None,
                "horizontal_m": self.distance["horizontal_m"] if self.distance else None,
                "fire_area_m2": self.fire_size["area_m2"] if self.fire_size else None,
                "pump_pressure_bar": self.hydraulics["pump_pressure_bar"] if self.hydraulics else None,
                "flow_lpm": self.hydraulics["flow_lpm"] if self.hydraulics else None,
                "water_used_l": round(self.water_l, 2),
                "reflashes": self.reflash_count,
            },
        }
        self.last_incident = report
        self.incident = None
        self._events.append({"type": "incident", "incident": report})

    def drain_events(self) -> List[Dict[str, Any]]:
        ev, self._events = self._events, []
        return ev

    # ------------------------------------------------------------------ reporting
    def narration(self, now: float, fps: float) -> str:
        s, c, r, v = self.state, self.cfg, self.reading, self.validator
        st = v.status()
        d = self.last_box_det or self.last_fire_det
        h, dist = self.hydraulics, self.distance
        if s == State.MONITORING and self.smoke_holdoff_until is not None and r and r.smoke_triggered:
            return (f"Re-armed. Residual smoke/steam from the extinguished fire is clearing ({r.smoke_ppm:.0f} ppm) - "
                    "smoke-only alarms are held off until it clears; a visible fire would still trigger immediately.")
        if s == State.MONITORING:
            return (f"YOLOv8 is analysing the camera feed (~{fps:.0f} frames/s). No fire in view. "
                    f"Smoke sensor at {r.smoke_ppm:.0f} ppm." if r and r.smoke_ppm is not None
                    else f"YOLOv8 is analysing the camera feed (~{fps:.0f} frames/s). No fire in view.")
        if s == State.FIRE_DETECTED:
            conf = f"{d['conf'] * 100:.0f}%" if d else "-"
            return (f"YOLOv8 detected fire with {conf} confidence. A single frame is never trusted - "
                    "starting temporal validation.")
        if s == State.TEMPORAL_VALIDATION:
            cons = f"{st['consistency']:.2f}" if st["consistency"] is not None else "-"
            return (f"Checking persistence: {st['positives']}/{st['size']} recent frames contain fire "
                    f"(need {st['required']}); box overlap IoU {cons} (need {c.TEMPORAL_MIN_IOU:.2f}).")
        if s == State.SENSOR_FUSION:
            ppm = f"{r.smoke_ppm:.0f}" if r and r.smoke_ppm is not None else "-"
            return (f"Vision validated. Waiting for the MQ-2 smoke sensor to corroborate: {ppm} ppm "
                    f"(alarm at {c.SMOKE_THRESHOLD_PPM:.0f} ppm). Smoke takes a few seconds to reach the sensor.")
        if s == State.FIRE_CONFIRMED:
            aim = (f" Aiming pan {self.aiming['pan_deg']:+.1f} deg, tilt {self.aiming['tilt_deg']:+.1f} deg."
                   if self.aiming else "")
            return "Fire confirmed by two independent sources (camera + smoke sensor). Alarm raised." + aim
        if s == State.DISTANCE_ESTIMATION:
            n = len(self.lidar_buffer)
            med = f"{statistics.median(self.lidar_buffer):.2f} m" if self.lidar_buffer else "-"
            return (f"TF-Luna LiDAR aimed at the fire: {n}/{c.LIDAR_SAMPLES} valid samples, "
                    f"running median {med}. Median filtering rejects noise and smoke dropouts.")
        if s == State.PRESSURE_ESTIMATION and h and dist:
            if not h["reachable"]:
                return f"Pressure estimation failed: {h['reason']}."
            return (f"Horizontal distance {dist['horizontal_m']:.2f} m, nozzle {h['height_drop_m']:.2f} m above target "
                    f"at {h['angle_deg']:.0f} deg -> jet {h['jet_velocity_ms']:.2f} m/s. Nozzle "
                    f"{h['nozzle_pressure_bar']:.2f} bar + pipe/fitting/lift losses -> pump "
                    f"{h['pump_pressure_bar']:.2f} bar ({h['pump_pressure_psi']:.0f} psi), {h['flow_lpm']:.1f} L/min.")
        if s == State.SUPPRESSION_ACTIVE:
            return (f"Valve {self.valve * 100:.0f}% open, pump {self.pump_bar:.2f} bar, {self.flow_lpm:.1f} L/min - "
                    f"{self.water_l:.1f} L applied. Closed loop: spraying until YOLOv8 no longer sees fire.")
        if s == State.VERIFICATION:
            return (f"No fire detected for {self.clear_frames} consecutive frames. Post-wetting for "
                    f"{c.POST_WET_S:.0f} s to prevent re-ignition.")
        if s == State.SUPPRESSION_COMPLETE and self.last_incident:
            m = self.last_incident["metrics"]
            t_ext = m["t_extinguished_s"]
            return (f"Fire extinguished {t_ext:.1f} s after detection using {m['water_used_l']:.1f} L of water. "
                    "Valve closed - system re-arming." if t_ext is not None else "Suppression complete.")
        if s == State.FALSE_ALARM_REJECTED:
            return f"False alarm rejected: {self.reason}. No water released."
        if s == State.VISION_ONLY_ALERT:
            return (f"Camera sees fire but the smoke sensor has not confirmed within "
                    f"{c.SENSOR_FUSION_TIMEOUT_S:.0f} s. Automatic suppression withheld - operator asked to verify.")
        if s == State.SMOKE_ONLY_ALERT:
            ppm = f"{r.smoke_ppm:.0f}" if r and r.smoke_ppm is not None else "-"
            return (f"Smoke sensor alarm ({ppm} ppm) but no flames visible - possible smouldering or cooking "
                    "smoke. Operator alerted; no water released.")
        if s == State.ESCALATED:
            return f"Escalated to fire services: {self.reason}."
        return ""

    def stages(self, now: float) -> List[Dict[str, Any]]:
        """Status of every main-flow stage for the dashboard stepper."""
        visited: Dict[str, Dict[str, Any]] = {}
        timeline = (self.incident or {}).get("timeline") or (
            self.last_incident["timeline"] if self.last_incident and self.state in ALERT_STATES | {State.SUPPRESSION_COMPLETE} else [])
        for i, e in enumerate(timeline):
            nxt = timeline[i + 1]["t"] if i + 1 < len(timeline) else None
            visited.setdefault(e["state"], {"t": e["t"], "duration": None if nxt is None else round(nxt - e["t"], 2)})
        cur = self.state
        cur_idx = MAIN_FLOW.index(cur) if cur in MAIN_FLOW else None
        failed_at = None
        if cur in ALERT_STATES and len(timeline) >= 2:
            failed_at = timeline[-2]["state"]
        out = []
        for idx, st in enumerate(MAIN_FLOW[1:], start=1):
            info = visited.get(st.value)
            if st == cur:
                status = "done" if cur == State.SUPPRESSION_COMPLETE else "active"
            elif failed_at == st.value:
                status = "failed"
            elif info is not None and (cur_idx is None or idx < cur_idx or cur in ALERT_STATES):
                status = "done"
            else:
                status = "pending"
            out.append({"key": st.value, **STAGE_INFO[st], "status": status,
                        "t": info["t"] if info else None,
                        "duration": info["duration"] if info else None})
        return out

    def snapshot(self, now: float, fps: float = 0.0) -> Dict[str, Any]:
        inc = self.incident
        return {
            "state": self.state.value,
            "title": STAGE_INFO[self.state]["title"],
            "tag": STAGE_INFO[self.state]["tag"],
            "is_alert": self.state in ALERT_STATES,
            "state_elapsed_s": round(self._elapsed(now), 2),
            "narration": self.narration(now, fps),
            "reason": self.reason,
            "stages": self.stages(now),
            "temporal": self.validator.status(),
            "aiming": self.aiming,
            "distance": self.distance,
            "lidar_progress": {"n": len(self.lidar_buffer), "required": self.cfg.LIDAR_SAMPLES,
                               "samples": [round(x, 2) for x in self.lidar_buffer[-40:]]},
            "fire_size": self.fire_size,
            "hydraulics": self.hydraulics,
            "suppression": {
                "valve_open_pct": round(self.valve * 100, 1),
                "pump_pressure_bar": round(self.pump_bar, 3),
                "target_pressure_bar": self.hydraulics["command_pressure_bar"] if self.hydraulics else None,
                "flow_lpm": round(self.flow_lpm, 2),
                "required_flow_lpm": self.required_flow_lpm,
                "water_used_l": round(self.water_l, 2),
                "elapsed_s": round(now - self.suppression_started, 1) if self.suppression_started else None,
                "clear_frames": self.clear_frames,
                "clear_frames_required": self.cfg.VERIFY_CLEAR_FRAMES,
                "reflashes": self.reflash_count,
                "active": self.valve > 0,
            },
            "incident": {
                "id": inc["id"], "started_at": inc["started_at"], "elapsed_s": round(now - inc["_t0"], 2),
                "timeline": inc["timeline"],
            } if inc else None,
            "last_incident": self.last_incident,
        }
