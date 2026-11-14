"""
FireGuard AI - Annotated camera view for the MJPEG stream.

Draws what the system "thinks" on top of the camera frame: YOLO boxes, the
current pipeline stage, the temporal-validation window, the pan/tilt aim point,
the LiDAR beam while measuring and the simulated water jet while suppressing.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

FONT = cv2.FONT_HERSHEY_SIMPLEX

STATE_COLOURS = {  # BGR
    "MONITORING": (94, 197, 34),
    "FIRE_DETECTED": (22, 115, 249),
    "TEMPORAL_VALIDATION": (22, 115, 249),
    "SENSOR_FUSION": (22, 115, 249),
    "FIRE_CONFIRMED": (68, 68, 239),
    "DISTANCE_ESTIMATION": (246, 130, 59),
    "PRESSURE_ESTIMATION": (246, 130, 59),
    "SUPPRESSION_ACTIVE": (250, 165, 96),
    "VERIFICATION": (250, 165, 96),
    "SUPPRESSION_COMPLETE": (94, 197, 34),
    "FALSE_ALARM_REJECTED": (180, 180, 180),
    "VISION_ONLY_ALERT": (8, 179, 234),
    "SMOKE_ONLY_ALERT": (8, 179, 234),
    "ESCALATED": (68, 68, 239),
}
CONFIRMED_STATES = {"FIRE_CONFIRMED", "DISTANCE_ESTIMATION", "PRESSURE_ESTIMATION", "SUPPRESSION_ACTIVE",
                    "VERIFICATION", "ESCALATED"}


def _label(img: np.ndarray, text: str, x: int, y: int, colour, scale: float = 0.5, pad: int = 4) -> None:
    (tw, th), _ = cv2.getTextSize(text, FONT, scale, 1)
    y = max(th + 2 * pad, y)
    cv2.rectangle(img, (x, y - th - 2 * pad), (x + tw + 2 * pad, y), colour, -1)
    cv2.putText(img, text, (x + pad, y - pad), FONT, scale, (255, 255, 255), 1, cv2.LINE_AA)


def _panel(img: np.ndarray, x1: int, y1: int, x2: int, y2: int, alpha: float = 0.55) -> None:
    roi = img[y1:y2, x1:x2]
    img[y1:y2, x1:x2] = (roi * (1 - alpha)).astype(np.uint8)


def render(frame: np.ndarray, detections: List[Dict[str, Any]], snap: Dict[str, Any],
           threshold: float, inference_ms: float, frame_no: int, simulated: bool,
           lidar_reading: Optional[float]) -> np.ndarray:
    img = frame.copy()
    h, w = img.shape[:2]
    state = snap["state"]
    colour = STATE_COLOURS.get(state, (200, 200, 200))
    confirmed = state in CONFIRMED_STATES

    # ---- detections ----------------------------------------------------------
    for d in detections:
        x1, y1, x2, y2 = int(d["x1"]), int(d["y1"]), int(d["x2"]), int(d["y2"])
        if d.get("kind") == "smoke":
            c = (200, 200, 200)
            cv2.rectangle(img, (x1, y1), (x2, y2), c, 1, cv2.LINE_AA)
            _label(img, f"smoke {d['conf'] * 100:.0f}%", x1, y1, (110, 110, 110), 0.42)
            continue
        if d["conf"] < threshold:
            c, thick, tag = (0, 200, 255), 1, "candidate"
        elif confirmed:
            c, thick, tag = (40, 40, 235), 3, "FIRE"
        else:
            c, thick, tag = (0, 140, 255), 2, "fire"
        cv2.rectangle(img, (x1, y1), (x2, y2), c, thick, cv2.LINE_AA)
        _label(img, f"{tag} {d['conf'] * 100:.0f}%", x1, y1, c, 0.45)

    # ---- aim point, LiDAR beam, water jet ------------------------------------
    aim = snap.get("aiming")
    nozzle = (40, h - 30)
    if aim and confirmed:
        tx, ty = aim["target_px"]
        cv2.circle(img, (tx, ty), 16, (40, 40, 235), 1, cv2.LINE_AA)
        cv2.line(img, (tx - 24, ty), (tx - 8, ty), (40, 40, 235), 1)
        cv2.line(img, (tx + 8, ty), (tx + 24, ty), (40, 40, 235), 1)
        cv2.line(img, (tx, ty - 24), (tx, ty - 8), (40, 40, 235), 1)
        cv2.line(img, (tx, ty + 8), (tx, ty + 24), (40, 40, 235), 1)
        if state == "DISTANCE_ESTIMATION":
            for i in range(0, 40, 2):  # dashed red laser line
                a, b = i / 40, (i + 1) / 40
                p1 = (int(nozzle[0] + (tx - nozzle[0]) * a), int(nozzle[1] + (ty - nozzle[1]) * a))
                p2 = (int(nozzle[0] + (tx - nozzle[0]) * b), int(nozzle[1] + (ty - nozzle[1]) * b))
                cv2.line(img, p1, p2, (60, 60, 255), 1, cv2.LINE_AA)
            if lidar_reading is not None:
                _label(img, f"LiDAR {lidar_reading:.2f} m", tx + 20, ty + 34, (60, 60, 200), 0.45)
        sup = snap.get("suppression") or {}
        if sup.get("valve_open_pct", 0) > 1:
            _draw_jet(img, nozzle, (tx, ty), sup["valve_open_pct"] / 100)

    # ---- HUD -----------------------------------------------------------------
    title = snap.get("title", state)
    _panel(img, 0, 0, w, 34, 0.6)
    cv2.circle(img, (16, 17), 6, colour, -1, cv2.LINE_AA)
    cv2.putText(img, title.upper(), (30, 23), FONT, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    info = f"YOLOv8 {inference_ms:.0f} ms | frame #{frame_no}"
    (tw, _), _ = cv2.getTextSize(info, FONT, 0.45, 1)
    cv2.putText(img, info, (w - tw - 12, 22), FONT, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    if simulated:
        _label(img, "SIMULATED SCENE", 8, h - 8, (0, 120, 160), 0.4)

    # temporal window strip (top left, under the HUD bar)
    t = snap.get("temporal") or {}
    win = t.get("window") or []
    if win:
        cell, gap = 9, 2
        text = f"temporal {t.get('positives', 0)}/{t.get('size', 0)} (need {t.get('required', 0)})"
        (tw, _), _ = cv2.getTextSize(text, FONT, 0.38, 1)
        x0, y0 = 14, 62
        _panel(img, x0 - 6, y0 - 18, x0 + max(tw, len(win) * (cell + gap)) + 8, y0 + cell + 6, 0.55)
        cv2.putText(img, text, (x0, y0 - 5), FONT, 0.38, (220, 220, 220), 1, cv2.LINE_AA)
        for i, v in enumerate(win):
            c = (60, 60, 230) if v == 1 else (70, 70, 70) if v == 0 else (40, 40, 40)
            cv2.rectangle(img, (x0 + i * (cell + gap), y0), (x0 + i * (cell + gap) + cell, y0 + cell), c, -1)
    return img


def _draw_jet(img: np.ndarray, start, end, strength: float) -> None:
    """Parabolic water jet from the nozzle to the target, with moving droplets."""
    (sx, sy), (ex, ey) = start, end
    apex_lift = 0.35 * abs(ex - sx) + 40
    pts = []
    for i in range(41):
        a = i / 40
        x = sx + (ex - sx) * a
        y = sy + (ey - sy) * a - apex_lift * 4 * a * (1 - a)
        pts.append((int(x), int(y)))
    overlay = img.copy()
    cv2.polylines(overlay, [np.array(pts, np.int32)], False, (255, 220, 170), max(2, int(6 * strength)), cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.45, img, 0.55, 0, dst=img)
    phase = (time.time() * 1.6) % 1.0
    for k in range(14):
        a = (phase + k / 14) % 1.0
        idx = int(a * 40)
        x, y = pts[idx]
        jitter = int(3 * math.sin(k * 7.3 + time.time() * 9))
        cv2.circle(img, (x + jitter, y), 2 + int(2 * strength), (255, 235, 200), -1, cv2.LINE_AA)
    cv2.circle(img, start, 7, (200, 160, 90), -1, cv2.LINE_AA)
    _label(img, "NOZZLE", start[0] - 20, start[1] - 10, (150, 110, 60), 0.38)
