"""
FireGuard AI - Configuration Management

Settings are loaded (lowest to highest priority) from:
  1. the defaults below,
  2. environment variables / ``backend/.env``,
  3. ``runtime_settings.json`` - values changed from the dashboard Settings page.

Only keys listed in ``RUNTIME_EDITABLE`` can be changed at runtime through the API.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger("fireguard.config")

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # ---- Video source -------------------------------------------------------
    # "scenario" = presenter-controlled video clips from MEDIA_DIR (simulation)
    # "ip"       = IP camera stream at CAMERA_URL
    # "webcam"   = local webcam WEBCAM_INDEX
    CAMERA_SOURCE: str = Field(default="scenario", pattern="^(scenario|ip|webcam)$")
    CAMERA_URL: str = "http://192.168.1.100:8080/video"
    WEBCAM_INDEX: int = Field(default=0, ge=0)
    MEDIA_DIR: str = "media"
    CAMERA_HFOV_DEG: float = Field(default=70.0, gt=10, lt=170, description="Horizontal field of view of the camera")

    # ---- YOLOv8 detection ---------------------------------------------------
    MODELS_DIR: str = "models"
    YOLO_MODEL_PATH: str = "models/best.pt"
    YOLO_IMGSZ: int = Field(default=640, ge=160, le=1280)
    CONFIDENCE_THRESHOLD: float = Field(default=0.5, ge=0.05, le=0.99)
    FIRE_CLASSES: str = "fire,flame"
    SMOKE_CLASSES: str = "smoke"
    DETECTION_MAX_FPS: float = Field(default=12.0, gt=0, le=60)
    YOLO_THREADS: int = Field(default=0, ge=0, le=64, description="CPU threads for inference (0 = half the cores)")

    # ---- Temporal validation ------------------------------------------------
    TEMPORAL_WINDOW: int = Field(default=15, ge=3, le=120, description="Sliding window size (inferred frames)")
    TEMPORAL_MIN_POSITIVE: int = Field(default=10, ge=1, le=120, description="Positive frames needed in the window")
    TEMPORAL_MIN_IOU: float = Field(default=0.10, ge=0.0, le=1.0, description="Mean IoU between consecutive positive boxes")
    TEMPORAL_TIMEOUT_S: float = Field(default=6.0, gt=0, description="Reject as false alarm if not validated within this time")

    # ---- Sensor fusion ------------------------------------------------------
    SMOKE_THRESHOLD_PPM: float = Field(default=300.0, gt=0)
    SMOKE_HYSTERESIS_PPM: float = Field(default=50.0, ge=0)
    SENSOR_FUSION_TIMEOUT_S: float = Field(default=15.0, gt=0)

    # ---- Hardware (real sensors) --------------------------------------------
    DEMO_MODE: bool = Field(default=True, description="True = simulated MQ-2 / TF-Luna sensors")
    ARDUINO_PORT: str = "COM3"
    BAUD_RATE: int = 9600

    # ---- LiDAR distance estimation -----------------------------------------
    LIDAR_SAMPLES: int = Field(default=10, ge=3, le=200, description="Valid samples to median-filter")
    LIDAR_TIMEOUT_S: float = Field(default=5.0, gt=0)

    # ---- Hydraulics (pressure estimation) -----------------------------------
    NOZZLE_HEIGHT_M: float = Field(default=2.5, ge=0, le=20, description="Nozzle height above the fire base")
    TARGET_HEIGHT_M: float = Field(default=0.3, ge=0, le=5, description="Aim point height above the fire base")
    NOZZLE_ANGLE_DEG: float = Field(default=30.0, ge=-30, le=75, description="Nozzle elevation angle")
    NOZZLE_DIAMETER_MM: float = Field(default=8.0, gt=1, le=50)
    NOZZLE_CD: float = Field(default=0.96, gt=0.5, le=1.0, description="Nozzle discharge coefficient")
    NOZZLE_CV: float = Field(default=0.98, gt=0.5, le=1.0, description="Nozzle velocity coefficient")
    PIPE_LENGTH_M: float = Field(default=6.0, ge=0, le=500)
    PIPE_DIAMETER_MM: float = Field(default=20.0, gt=2, le=300)
    PIPE_ROUGHNESS_MM: float = Field(default=0.0015, ge=0, le=5, description="Absolute roughness (PVC ~0.0015 mm)")
    MINOR_LOSS_K: float = Field(default=4.0, ge=0, le=100, description="Sum of fitting/valve loss coefficients")
    PUMP_ELEVATION_M: float = Field(default=2.5, ge=-20, le=50, description="Nozzle height above the pump outlet")
    DRAG_MARGIN: float = Field(default=0.10, ge=0, le=1, description="Extra jet velocity to offset air drag")
    MIN_PRESSURE: float = Field(default=0.5, ge=0, le=50, description="Pump minimum operating pressure (bar)")
    MAX_PRESSURE: float = Field(default=8.0, gt=0, le=100, description="Pump maximum pressure (bar)")
    DESIGN_DENSITY_LPM_M2: float = Field(default=6.1, gt=0, le=50, description="Water application rate (NFPA 13 OH1 = 6.1)")

    # ---- Suppression control ------------------------------------------------
    KNOCKDOWN_REF_S: float = Field(default=8.0, gt=0, description="Time to reduce fire to 10% at the design flow rate")
    VERIFY_CLEAR_FRAMES: int = Field(default=12, ge=1, le=300)
    POST_WET_S: float = Field(default=3.0, ge=0, le=60)
    SUPPRESSION_MAX_S: float = Field(default=60.0, gt=0)
    COOLDOWN_S: float = Field(default=10.0, ge=0)
    STAGE_MIN_DWELL_S: float = Field(default=1.5, ge=0, le=10, description="Minimum time each stage stays on screen")

    # ---- Simulation ---------------------------------------------------------
    SIM_FIRE_DISTANCE_M: float = Field(default=4.0, ge=0.2, le=12)
    SMOKE_TRANSPORT_DELAY_S: float = Field(default=3.0, ge=0, le=30)
    SMOKE_RISE_TAU_S: float = Field(default=3.5, gt=0, le=60)
    SMOKE_MAX_PPM: float = Field(default=1400.0, gt=0, le=10000)

    # ---- Server -------------------------------------------------------------
    DB_PATH: str = "fireguard.db"
    RUNTIME_SETTINGS_PATH: str = "runtime_settings.json"
    WS_BROADCAST_INTERVAL: float = Field(default=0.25, gt=0.02, le=5)
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "validate_assignment": True,
        "extra": "ignore",  # old .env files may still contain removed keys (e.g. PRESSURE_BASE)
    }

    # ---- helpers -------------------------------------------------------------
    def path(self, value: str) -> Path:
        """Resolve a configured path relative to the backend directory."""
        p = Path(value)
        return p if p.is_absolute() else BACKEND_DIR / p

    @property
    def fire_classes(self) -> set[str]:
        return {c.strip().lower() for c in self.FIRE_CLASSES.split(",") if c.strip()}

    @property
    def smoke_classes(self) -> set[str]:
        return {c.strip().lower() for c in self.SMOKE_CLASSES.split(",") if c.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


# Keys the dashboard may change at runtime (and that get persisted).
RUNTIME_EDITABLE = (
    "CAMERA_SOURCE", "CAMERA_URL", "WEBCAM_INDEX", "CAMERA_HFOV_DEG",
    "YOLO_MODEL_PATH", "YOLO_IMGSZ", "CONFIDENCE_THRESHOLD", "FIRE_CLASSES", "SMOKE_CLASSES",
    "TEMPORAL_WINDOW", "TEMPORAL_MIN_POSITIVE", "TEMPORAL_MIN_IOU", "TEMPORAL_TIMEOUT_S",
    "SMOKE_THRESHOLD_PPM", "SENSOR_FUSION_TIMEOUT_S",
    "DEMO_MODE", "ARDUINO_PORT", "BAUD_RATE",
    "LIDAR_SAMPLES",
    "NOZZLE_HEIGHT_M", "TARGET_HEIGHT_M", "NOZZLE_ANGLE_DEG", "NOZZLE_DIAMETER_MM", "NOZZLE_CD", "NOZZLE_CV",
    "PIPE_LENGTH_M", "PIPE_DIAMETER_MM", "PIPE_ROUGHNESS_MM", "MINOR_LOSS_K", "PUMP_ELEVATION_M",
    "DRAG_MARGIN", "MIN_PRESSURE", "MAX_PRESSURE", "DESIGN_DENSITY_LPM_M2",
    "KNOCKDOWN_REF_S", "VERIFY_CLEAR_FRAMES", "POST_WET_S", "SUPPRESSION_MAX_S", "COOLDOWN_S",
    "STAGE_MIN_DWELL_S",
)


def editable_values(s: Settings) -> Dict[str, Any]:
    return {k: getattr(s, k) for k in RUNTIME_EDITABLE}


def apply_updates(s: Settings, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and apply ``updates`` (unknown keys rejected). Returns the applied subset.

    Everything is validated on a copy first, so a bad value never leaves the
    settings half-updated.
    """
    unknown = sorted(set(updates) - set(RUNTIME_EDITABLE))
    if unknown:
        raise ValueError(f"Not editable: {', '.join(unknown)}")
    validated = Settings.model_validate({**s.model_dump(), **updates})
    if validated.TEMPORAL_MIN_POSITIVE > validated.TEMPORAL_WINDOW:
        raise ValueError("TEMPORAL_MIN_POSITIVE cannot exceed TEMPORAL_WINDOW")
    if validated.MIN_PRESSURE >= validated.MAX_PRESSURE:
        raise ValueError("MIN_PRESSURE must be below MAX_PRESSURE")
    for k in updates:
        setattr(s, k, getattr(validated, k))
    return {k: getattr(s, k) for k in updates}


def load_runtime_overrides(s: Settings) -> None:
    path = s.path(s.RUNTIME_SETTINGS_PATH)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data = {k: v for k, v in data.items() if k in RUNTIME_EDITABLE}
        apply_updates(s, data)
        logger.info("Loaded %d runtime setting overrides from %s", len(data), path.name)
    except Exception as exc:  # a corrupt file must not stop the system
        logger.error("Ignoring invalid %s: %s", path.name, exc)


def save_runtime_overrides(s: Settings) -> None:
    path = s.path(s.RUNTIME_SETTINGS_PATH)
    path.write_text(json.dumps(editable_values(s), indent=2), encoding="utf-8")


settings = Settings()
load_runtime_overrides(settings)
logger.info("Configuration loaded. CAMERA_SOURCE=%s DEMO_MODE=%s", settings.CAMERA_SOURCE, settings.DEMO_MODE)
