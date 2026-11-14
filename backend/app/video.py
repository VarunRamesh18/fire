"""
FireGuard AI - Video sources.

* ``ClipPlayer``   plays a video file in real time (native fps, looping) - used by the
                   scenario simulator as a stand-in for the camera.
* ``StreamPlayer`` reads an IP camera URL or a local webcam index, reconnecting forever
                   with back-off if the stream drops.

Both run on a background thread and expose the most recent frame, already fitted
to the fixed camera canvas (CANVAS_W x CANVAS_H) so every source looks like the
same camera to the rest of the system.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np

logger = logging.getLogger("fireguard.video")

CANVAS_W, CANVAS_H = 960, 540


def fit_canvas(frame: np.ndarray, w: int = CANVAS_W, h: int = CANVAS_H) -> np.ndarray:
    """Fit ``frame`` into a w x h canvas keeping aspect ratio.

    Empty side areas are filled with a dark, desaturated, blurred copy of the frame
    (like phone video shown on a TV) - dark and colourless so the detector ignores it.
    """
    fh, fw = frame.shape[:2]
    if (fw, fh) == (w, h):
        return frame
    s = min(w / fw, h / fh)
    nw, nh = max(1, int(fw * s)), max(1, int(fh * s))
    fg = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    if (nw, nh) == (w, h):
        return fg
    small = cv2.resize(frame, (max(1, w // 10), max(1, h // 10)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    bg = cv2.resize(cv2.GaussianBlur(gray, (0, 0), 2), (w, h))
    bg = cv2.cvtColor((bg * 0.22).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    x, y = (w - nw) // 2, (h - nh) // 2
    bg[y:y + nh, x:x + nw] = fg
    return bg


def placeholder_frame(text: str) -> np.ndarray:
    frame = np.full((CANVAS_H, CANVAS_W, 3), 18, dtype=np.uint8)
    cv2.putText(frame, text, (40, CANVAS_H // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (90, 90, 200), 2)
    return frame


class _Player:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.fps: float = 0.0
        self.connected: bool = False
        self._frame_times: list[float] = []

    def latest(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._frame

    def _publish(self, frame: np.ndarray) -> None:
        fitted = fit_canvas(frame)
        now = time.time()
        self._frame_times = [t for t in self._frame_times if now - t < 2.0] + [now]
        if len(self._frame_times) > 1:
            self.fps = (len(self._frame_times) - 1) / (self._frame_times[-1] - self._frame_times[0])
        with self._lock:
            self._frame = fitted

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=type(self).__name__)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self.connected = False

    def _run(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class ClipPlayer(_Player):
    """Loops a video file at its native frame rate."""

    def __init__(self, path: Optional[Path]) -> None:
        super().__init__()
        self.path = path
        self.paused = False      # presenter pause (freezes the picture)
        self.active = True       # False while the clip is not on screen: skip decoding to save CPU
        self._restart = threading.Event()
        self.position_s: float = 0.0
        self.duration_s: float = 0.0

    def restart(self) -> None:
        """Seek back to the first frame (e.g. when a fire is ignited)."""
        self._restart.set()

    def _run(self) -> None:
        if self.path is None or not self.path.exists():
            logger.warning("Clip not found: %s", self.path)
            self._publish(placeholder_frame(f"Clip missing: {self.path.name if self.path else '-'}"))
            return
        cap = cv2.VideoCapture(str(self.path))
        if not cap.isOpened():
            self._publish(placeholder_frame(f"Cannot open {self.path.name}"))
            return
        self.connected = True
        clip_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        self.duration_s = n_frames / clip_fps
        period = 1.0 / clip_fps
        next_t = time.perf_counter()
        try:
            first = True
            while not self._stop.is_set():
                if self._restart.is_set():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self._restart.clear()
                    first = True
                if first:  # always publish one frame so the clip has a picture ready
                    ok, frame = cap.read()
                    if ok:
                        self._publish(frame)
                    first = False
                    next_t = time.perf_counter() + period
                    continue
                if self.paused or not self.active:
                    time.sleep(0.03)
                    next_t = time.perf_counter()
                    continue
                ok, frame = cap.read()
                if not ok:  # loop
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                self.position_s = cap.get(cv2.CAP_PROP_POS_FRAMES) / clip_fps
                self._publish(frame)
                next_t += period
                delay = next_t - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_t = time.perf_counter()  # running late: don't try to catch up
        finally:
            cap.release()
            self.connected = False


class StreamPlayer(_Player):
    """IP camera / webcam reader with automatic reconnect."""

    def __init__(self, source: Union[str, int]) -> None:
        super().__init__()
        self.source = source

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            cap = cv2.VideoCapture(self.source)
            if not cap.isOpened():
                self.connected = False
                self._publish(placeholder_frame("Camera offline - retrying..."))
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 15.0)
                continue
            logger.info("Camera stream opened")
            self.connected, backoff = True, 1.0
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    logger.warning("Camera stream lost - reconnecting")
                    break
                self._publish(frame)
            cap.release()
            self.connected = False
