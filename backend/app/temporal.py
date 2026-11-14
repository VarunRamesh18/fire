"""
FireGuard AI - Temporal validation of YOLO detections.

A single-frame detection is not trusted.  Fire is *validated* only when, inside
a sliding window of the last N inferred frames:

  * at least K frames contain a fire detection above the confidence threshold
    (persistence - rejects flashes, reflections, a passing red car), and
  * the fire boxes in consecutive positive frames overlap (mean IoU >= min_iou)
    (spatial consistency - rejects detections that jump around the image).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Sequence


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Intersection-over-union of two (x1, y1, x2, y2) boxes."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class _Entry:
    positive: bool
    conf: float
    box: Optional[tuple]


class TemporalValidator:
    def __init__(self, window: int = 15, min_positive: int = 10, min_iou: float = 0.1) -> None:
        self.configure(window, min_positive, min_iou)

    def configure(self, window: int, min_positive: int, min_iou: float) -> None:
        self.window = window
        self.min_positive = min(min_positive, window)
        self.min_iou = min_iou
        old = list(getattr(self, "_buf", []))
        self._buf: Deque[_Entry] = deque(old[-window:], maxlen=window)

    def reset(self) -> None:
        self._buf.clear()

    def update(self, fire_detections: List[Dict[str, Any]], threshold: float) -> bool:
        """Add one inferred frame. ``fire_detections`` are fire-class boxes only."""
        best = max(fire_detections, key=lambda d: d["conf"], default=None)
        positive = best is not None and best["conf"] >= threshold
        box = (best["x1"], best["y1"], best["x2"], best["y2"]) if positive else None
        self._buf.append(_Entry(positive, best["conf"] if best else 0.0, box))
        return positive

    # ------------------------------------------------------------------
    @property
    def positives(self) -> int:
        return sum(e.positive for e in self._buf)

    @property
    def consistency(self) -> Optional[float]:
        """Mean IoU between consecutive positive boxes in the window (None if < 2)."""
        boxes = [e.box for e in self._buf if e.positive]
        if len(boxes) < 2:
            return None
        vals = [iou(a, b) for a, b in zip(boxes, boxes[1:])]
        return sum(vals) / len(vals)

    @property
    def window_full(self) -> bool:
        return len(self._buf) == self.window

    @property
    def passed(self) -> bool:
        if self.positives < self.min_positive:
            return False
        c = self.consistency
        return c is None or c >= self.min_iou

    def recent_positives(self, n: int) -> int:
        return sum(e.positive for e in list(self._buf)[-n:])

    def status(self) -> Dict[str, Any]:
        entries = list(self._buf)
        c = self.consistency
        confs = [e.conf for e in entries if e.positive]
        return {
            "window": [1 if e.positive else 0 for e in entries] + [None] * (self.window - len(entries)),
            "confidences": [round(e.conf, 3) for e in entries],
            "size": self.window,
            "positives": self.positives,
            "required": self.min_positive,
            "ratio": round(self.positives / self.window, 3),
            "consistency": round(c, 3) if c is not None else None,
            "min_iou": self.min_iou,
            "mean_conf": round(sum(confs) / len(confs), 3) if confs else 0.0,
            "passed": self.passed,
        }
