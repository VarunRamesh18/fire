"""
FireGuard AI - Scenario simulator (camera scene + physical sensors).

The *scene* is the ground truth the presenter controls: which clip the camera
sees, whether a fire is burning, how far away it is and how strongly it burns.
The AI pipeline never reads the ground truth directly - it only sees

  * the composited camera frame   -> YOLOv8
  * simulated MQ-2 smoke readings -> smoke corroboration
  * simulated TF-Luna readings    -> distance estimation

and the fire only goes out because the pipeline's (simulated) water flow
reduces its intensity, which YOLO then has to confirm visually.
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.video import CANVAS_H, CANVAS_W, ClipPlayer, placeholder_frame

logger = logging.getLogger("fireguard.simulation")

BACKGROUND_DISTANCE_M = 7.2  # what the LiDAR sees when it is not aimed at a fire


# ---------------------------------------------------------------------------
# MQ-2 smoke sensor
# ---------------------------------------------------------------------------


class SmokeSensorSim:
    """MQ-2 smoke sensor model.

    * smoke takes ``delay`` seconds to travel from the fire to the sensor,
    * the sensor responds with a first-order lag (time constant ``tau``),
      clearing ~2.5x slower than it rises,
    * output: concentration (ppm), 10-bit ADC value and a digital alarm with hysteresis.
    """

    BASELINE_PPM = 55.0

    def __init__(self) -> None:
        self.ppm = self.BASELINE_PPM
        self.triggered = False
        self._hist: Deque[Tuple[float, float]] = deque()

    def reset(self) -> None:
        self.__init__()

    def update(self, now: float, dt: float, source_ppm: float, delay: float, tau: float,
               threshold: float, hysteresis: float) -> Dict[str, Any]:
        self._hist.append((now, source_ppm))
        while len(self._hist) > 2 and self._hist[1][0] <= now - delay:
            self._hist.popleft()
        delayed = self._hist[0][1] if self._hist[0][0] <= now - delay else 0.0
        target = self.BASELINE_PPM + delayed
        t = tau if target > self.ppm else tau * 2.5
        self.ppm += (target - self.ppm) * (1 - math.exp(-dt / t))
        noisy = max(0.0, self.ppm + random.gauss(0, 2.5 + 0.01 * self.ppm))
        if not self.triggered and noisy >= threshold:
            self.triggered = True
        elif self.triggered and noisy < threshold - hysteresis:
            self.triggered = False
        return {
            "ppm": round(noisy, 1),
            "adc": int(min(1023, max(0, 90 + noisy * 0.42))),
            "triggered": self.triggered,
            "threshold_ppm": threshold,
        }


# ---------------------------------------------------------------------------
# TF-Luna LiDAR
# ---------------------------------------------------------------------------


@dataclass
class LidarSample:
    t: float
    distance_m: Optional[float]
    strength: int
    valid: bool


class LidarSim:
    """Benewake TF-Luna model: 0.2-8 m range, +/-6 cm (<3 m) / 2 % (3-8 m) accuracy,
    1 cm resolution, signal strength falls with distance and smoke; weak or
    saturated returns are flagged invalid, like the real sensor."""

    RATE_HZ = 50
    MIN_RANGE, MAX_RANGE = 0.2, 8.0

    def __init__(self) -> None:
        self.samples: Deque[LidarSample] = deque(maxlen=60)

    def reset(self) -> None:
        self.samples.clear()

    def sample(self, now: float, true_m: float, smoke_ppm: float) -> LidarSample:
        strength = int(min(65535, 24000 / max(true_m, 0.2) ** 2 * math.exp(-smoke_ppm / 3000)))
        sigma = 0.02 if true_m < 3 else 0.007 * true_m
        dropout = 0.01 + smoke_ppm / 40000
        valid = (self.MIN_RANGE <= true_m <= self.MAX_RANGE and 100 <= strength < 65535
                 and random.random() > dropout)
        dist = round(true_m + random.gauss(0, sigma), 2) if valid else None
        s = LidarSample(now, dist, strength if valid else min(strength, 80), valid)
        self.samples.append(s)
        return s

    def update(self, now: float, dt: float, true_m: float, smoke_ppm: float) -> LidarSample:
        n = max(1, min(25, int(self.RATE_HZ * dt)))
        last = None
        for i in range(n):
            last = self.sample(now - dt + dt * (i + 1) / n, true_m, smoke_ppm)
        return last  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Scene (ground truth + camera image)
# ---------------------------------------------------------------------------


def load_clips(media_dir: Path) -> List[Dict[str, Any]]:
    manifest = media_dir / "clips.json"
    clips: List[Dict[str, Any]] = []
    if manifest.exists():
        try:
            clips = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Invalid %s: %s", manifest, exc)
    else:  # fall back to file names: anything containing "fire" is a fire clip
        for p in sorted(media_dir.glob("*.mp4")):
            clips.append({"id": p.stem, "label": p.stem, "file": p.name,
                          "kind": "fire" if "fire" in p.stem.lower() else "normal", "smoke_factor": 1.0})
    for c in clips:
        c["available"] = (media_dir / c["file"]).exists()
    return clips


class FireScene:
    """Presenter-controlled scenario: what the camera sees and what is really burning."""

    MODES = ("normal", "fire", "extinguished", "false_alarm")

    def __init__(self, media_dir: Path, distance_m: float) -> None:
        self.media_dir = media_dir
        self.clips = load_clips(media_dir)
        normals = [c for c in self.clips if c["kind"] == "normal" and c["available"]]
        fires = [c for c in self.clips if c["kind"] == "fire" and c["available"]]
        self.normal_clip = normals[0] if normals else None
        self.fire_clip = fires[0] if fires else None
        self._normal: Optional[ClipPlayer] = None
        self._fire: Optional[ClipPlayer] = None

        self.mode = "normal"
        self.intensity = 0.0
        self.distance_m = distance_m
        self.paused = False
        self.ignited_at: Optional[float] = None
        self.extinguished_at: Optional[float] = None
        self._false_alarm_until = 0.0
        self._smoke_puffs: List[Tuple[float, float]] = []
        self._residual_ppm = 0.0

        # water applied by the suppression system (set by the pipeline every tick)
        self.water_flow_lpm = 0.0
        self.water_required_lpm: Optional[float] = None
        self.water_pressure_ratio = 1.0
        self._intensity_at_water: Optional[float] = None
        self.haze = 0.0
        self.water_applied_l = 0.0

        rng = np.random.default_rng(7)
        tex = cv2.GaussianBlur(rng.integers(0, 255, (CANVAS_H * 2 // 4, CANVAS_W * 2 // 4), dtype=np.uint8), (0, 0), 9)
        tex = cv2.normalize(tex, None, 120, 235, cv2.NORM_MINMAX)
        self._steam_tex = cv2.resize(tex, (CANVAS_W * 2, CANVAS_H * 2))
        self._steam_phase = 0.0

    # ---- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        self._swap_players()

    def stop(self) -> None:
        for p in (self._normal, self._fire):
            if p:
                p.stop()

    def _swap_players(self) -> None:
        self.stop()
        self._normal = ClipPlayer(self.media_dir / self.normal_clip["file"]) if self.normal_clip else None
        self._fire = ClipPlayer(self.media_dir / self.fire_clip["file"]) if self.fire_clip else None
        for p in (self._normal, self._fire):
            if p:
                p.paused = self.paused
                p.start()
        self._sync_players()

    def _sync_players(self) -> None:
        """Only decode the clip(s) currently visible - halves the video CPU load."""
        if self._normal:
            self._normal.active = self.mode in ("normal", "false_alarm")
        if self._fire:
            self._fire.active = self.mode in ("fire", "extinguished", "false_alarm")

    # ---- presenter actions --------------------------------------------------
    def select_clips(self, normal_id: Optional[str], fire_id: Optional[str]) -> None:
        by_id = {c["id"]: c for c in self.clips if c["available"]}
        changed = False
        if normal_id and normal_id in by_id and by_id[normal_id]["kind"] == "normal":
            changed |= by_id[normal_id] is not self.normal_clip
            self.normal_clip = by_id[normal_id]
        if fire_id and fire_id in by_id and by_id[fire_id]["kind"] == "fire":
            changed |= by_id[fire_id] is not self.fire_clip
            self.fire_clip = by_id[fire_id]
        if changed:
            self._swap_players()

    def ignite(self, now: float) -> None:
        if self._fire is not None:
            self._fire.restart()
        self.mode = "fire"
        self.intensity = 0.55
        self.ignited_at = now
        self.extinguished_at = None
        self.haze = 0.0
        self._intensity_at_water = None
        self.water_applied_l = 0.0
        self._sync_players()

    def false_alarm(self, now: float, duration_s: float = 0.5) -> None:
        """A brief flash (glare / reflection / camera flash): fire-like pixels with no fire."""
        self.mode = "false_alarm"
        self._false_alarm_until = now + duration_s
        self._sync_players()

    def inject_smoke(self, now: float, seconds: float = 10.0) -> None:
        """Smoke without flames (e.g. cooking smoke) - tests the smoke-only path."""
        self._smoke_puffs.append((now, now + seconds))

    def reset(self) -> None:
        self.mode = "normal"
        self.intensity = 0.0
        self.haze = 0.0
        self.ignited_at = self.extinguished_at = None
        self._smoke_puffs.clear()
        self._residual_ppm = 0.0
        self._intensity_at_water = None
        self.water_flow_lpm = 0.0
        self.water_applied_l = 0.0
        self._sync_players()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        for p in (self._normal, self._fire):
            if p:
                p.paused = paused

    # ---- physics ------------------------------------------------------------
    def apply_water(self, flow_lpm: float, required_lpm: Optional[float], pressure_ratio: float) -> None:
        self.water_flow_lpm = max(0.0, flow_lpm)
        self.water_required_lpm = required_lpm
        self.water_pressure_ratio = max(0.0, min(1.0, pressure_ratio))

    def tick(self, now: float, dt: float, knockdown_ref_s: float) -> None:
        if self.paused:
            return
        self._steam_phase += dt
        self.water_applied_l += self.water_flow_lpm * dt / 60
        if self.mode == "false_alarm" and now >= self._false_alarm_until:
            self.mode = "normal"
        if self.mode == "fire":
            if self.water_flow_lpm <= 0:
                self.intensity += 0.12 * (1 - self.intensity) * dt  # unchecked fire grows
            else:
                if self._intensity_at_water is None:
                    self._intensity_at_water = self.intensity
                req = self.water_required_lpm or self.water_flow_lpm
                ratio = min(self.water_flow_lpm / max(req, 1e-6), 3.0) * self.water_pressure_ratio
                k = math.log(10) / knockdown_ref_s * ratio
                self.intensity *= math.exp(-k * dt)
                i0 = self._intensity_at_water or 1.0
                target_haze = min(0.93, max(0.0, 1 - self.intensity / i0) * 1.05)
                self.haze += (target_haze - self.haze) * min(1.0, dt * 2.5)
            if self.intensity < 0.04:
                self.mode = "extinguished"
                self.extinguished_at = now
                self._residual_ppm = 0.0
        elif self.mode == "extinguished":
            # steam/smoke slowly clears to a wet, smouldering scene
            target = 0.35 if self.water_flow_lpm > 0 else 0.15
            self.haze += (target - self.haze) * min(1.0, dt * 0.25)
        self._smoke_puffs = [p for p in self._smoke_puffs if p[1] > now]
        self._sync_players()

    def smoke_source_ppm(self, now: float, smoke_max_ppm: float) -> float:
        factor = (self.fire_clip or {}).get("smoke_factor", 1.0)
        ppm = 0.0
        if self.mode == "fire":
            ppm += self.intensity * smoke_max_ppm * factor
        elif self.mode == "extinguished" and self.extinguished_at is not None:
            # smoke and steam linger after knock-down and clear over ~15 s
            ppm += 0.45 * smoke_max_ppm * factor * math.exp(-(now - self.extinguished_at) / 15.0)
        for start, end in self._smoke_puffs:
            ramp = min(1.0, (now - start) / 2.0)
            ppm += 750 * ramp
        return ppm

    def lidar_target_m(self, aimed_at_fire: bool) -> float:
        return self.distance_m if aimed_at_fire else BACKGROUND_DISTANCE_M

    # ---- camera image -------------------------------------------------------
    def camera_frame(self) -> np.ndarray:
        normal = self._normal.latest() if self._normal else None
        fire = self._fire.latest() if self._fire else None
        if self.mode == "normal" or (self.mode != "normal" and fire is None):
            return normal if normal is not None else placeholder_frame("No normal clip - run tools/prepare_media.py")
        if self.mode == "false_alarm":
            base = normal if normal is not None else np.zeros_like(fire)
            return cv2.addWeighted(fire, 0.75, base, 0.35, 0)
        frame = fire
        if self.mode == "extinguished":
            gray = cv2.cvtColor(fire, cv2.COLOR_BGR2GRAY)
            frame = cv2.cvtColor((gray * 0.42).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        if self.haze > 0.01:
            frame = self._apply_steam(frame, self.haze)
        return frame

    def _apply_steam(self, frame: np.ndarray, alpha: float) -> np.ndarray:
        ox = int(self._steam_phase * 22) % CANVAS_W
        oy = int(self._steam_phase * 9) % CANVAS_H
        tex = self._steam_tex[oy:oy + CANVAS_H, ox:ox + CANVAS_W]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        steam = cv2.addWeighted(gray, 0.35, tex, 0.65, 0)
        steam = cv2.merge([np.clip(steam.astype(np.int16) + 8, 0, 255).astype(np.uint8), steam, steam])
        return cv2.addWeighted(steam, alpha, frame, 1 - alpha, 0)

    # ---- reporting ----------------------------------------------------------
    @property
    def fire_present(self) -> bool:
        return self.mode == "fire"

    def status(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "fire_present": self.fire_present,
            "intensity": round(self.intensity, 3),
            "distance_m": self.distance_m,
            "paused": self.paused,
            "haze": round(self.haze, 3),
            "normal_clip": self.normal_clip["id"] if self.normal_clip else None,
            "fire_clip": self.fire_clip["id"] if self.fire_clip else None,
            "smoke_injection_active": bool(self._smoke_puffs),
            "water_applied_l": round(self.water_applied_l, 2),
            "video_fps": round(self._active_fps(), 1),
        }

    def _active_fps(self) -> float:
        p = self._fire if self.mode in ("fire", "extinguished", "false_alarm") else self._normal
        return p.fps if p else 0.0

    @property
    def video_connected(self) -> bool:
        p = self._fire if self.mode in ("fire", "extinguished") else self._normal
        return bool(p and p.connected)
