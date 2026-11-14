"""
FireGuard AI - YOLOv8 detection engine.

Runs the trained Ultralytics YOLOv8 model on camera frames.  Detections are split
into *fire* boxes (used by the decision pipeline) and *smoke* boxes (visual smoke,
shown as supporting evidence) using the FIRE_CLASSES / SMOKE_CLASSES settings.

If the model cannot be loaded, a classical colour-segmentation detector is used
as a clearly labelled fallback so the dashboard still works.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger("fireguard.detection")


class DetectionEngine:
    def __init__(self) -> None:
        self._model: Any = None
        self._model_loaded = False
        self._model_path = settings.YOLO_MODEL_PATH
        self.class_names: Dict[int, str] = {}
        self.last_inference_ms: float = 0.0
        self.load_error: Optional[str] = None
        self.threads: Optional[int] = None

    # ------------------------------------------------------------------
    @staticmethod
    def resolve_model_path(path: str) -> Path:
        """Only allow .pt files inside MODELS_DIR (loading a .pt file can execute code)."""
        models_dir = settings.path(settings.MODELS_DIR).resolve()
        candidate = settings.path(path).resolve()
        if models_dir not in candidate.parents:
            raise ValueError(f"Model must be inside {settings.MODELS_DIR}/")
        if candidate.suffix != ".pt":
            raise ValueError("Model file must be a .pt file")
        return candidate

    async def load_model(self, path: Optional[str] = None) -> bool:
        path = path or settings.YOLO_MODEL_PATH
        try:
            resolved = self.resolve_model_path(path)
            if not resolved.exists():
                raise FileNotFoundError(f"{path} not found")
            import torch  # type: ignore
            from ultralytics import YOLO  # type: ignore

            # leave CPU cores free for video decoding / rendering instead of oversubscribing them
            self.threads = settings.YOLO_THREADS or max(2, (os.cpu_count() or 4) // 2)
            torch.set_num_threads(self.threads)
            loop = asyncio.get_running_loop()
            model = await loop.run_in_executor(None, lambda: YOLO(str(resolved)))
            # warm-up so the first real frame is not slow
            await loop.run_in_executor(None, lambda: model.predict(
                np.zeros((540, 960, 3), dtype=np.uint8), imgsz=settings.YOLO_IMGSZ, verbose=False))
            self._model, self._model_loaded, self._model_path = model, True, path
            self.class_names = {int(k): str(v) for k, v in model.names.items()}
            self.load_error = None
            logger.info("YOLOv8 model loaded from %s classes=%s", resolved, self.class_names)
            return True
        except Exception as exc:
            self._model_loaded = False
            self.load_error = str(exc)
            logger.error("YOLO model not loaded (%s) - using colour-segmentation fallback", exc)
            return False

    # ------------------------------------------------------------------
    async def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """Returns detections: x1, y1, x2, y2, conf, label, kind ('fire' | 'smoke' | 'other')."""
        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        try:
            fn = self._predict_yolo if self._model_loaded else self._predict_colour
            dets = await loop.run_in_executor(None, fn, frame)
        except Exception as exc:
            logger.error("Detection error: %s", exc)
            dets = []
        self.last_inference_ms = (time.perf_counter() - t0) * 1000
        return dets

    def _predict_yolo(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        # low floor so "candidate" boxes below the alarm threshold are still visible on screen
        floor = min(0.25, settings.CONFIDENCE_THRESHOLD)
        result = self._model.predict(frame, conf=floor, imgsz=settings.YOLO_IMGSZ, verbose=False)[0]
        out: List[Dict[str, Any]] = []
        if result.boxes is None:
            return out
        fire_cls, smoke_cls = settings.fire_classes, settings.smoke_classes
        for xyxy, conf, cls in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy(),
                                   result.boxes.cls.cpu().numpy()):
            label = self.class_names.get(int(cls), str(int(cls)))
            kind = "fire" if label.lower() in fire_cls else "smoke" if label.lower() in smoke_cls else "other"
            out.append({
                "x1": round(float(xyxy[0]), 1), "y1": round(float(xyxy[1]), 1),
                "x2": round(float(xyxy[2]), 1), "y2": round(float(xyxy[3]), 1),
                "conf": round(float(conf), 4), "label": label, "kind": kind,
            })
        return out

    @staticmethod
    def _predict_colour(frame: np.ndarray) -> List[Dict[str, Any]]:
        """Fallback: bright, saturated orange/yellow regions (classical fire-colour model)."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (5, 120, 190), (35, 255, 255))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        h, w = frame.shape[:2]
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:3]:
            area = cv2.contourArea(c)
            if area < 0.002 * h * w:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            conf = min(0.95, 0.35 + 6 * area / (h * w))
            out.append({"x1": float(x), "y1": float(y), "x2": float(x + bw), "y2": float(y + bh),
                        "conf": round(conf, 4), "label": "fire (colour fallback)", "kind": "fire"})
        return out

    # ------------------------------------------------------------------
    @property
    def model_loaded(self) -> bool:
        return self._model_loaded

    @property
    def model_path(self) -> str:
        return self._model_path

    @property
    def mode(self) -> str:
        return "yolov8" if self._model_loaded else "colour-fallback"
