import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402


@pytest.fixture
def cfg() -> Settings:
    """Fast, deterministic settings for pipeline tests (independent of .env / runtime overrides)."""
    return Settings(
        _env_file=None,
        TEMPORAL_WINDOW=15, TEMPORAL_MIN_POSITIVE=10, TEMPORAL_MIN_IOU=0.1, TEMPORAL_TIMEOUT_S=6.0,
        CONFIDENCE_THRESHOLD=0.5, SMOKE_THRESHOLD_PPM=300, SENSOR_FUSION_TIMEOUT_S=15,
        LIDAR_SAMPLES=10, LIDAR_TIMEOUT_S=5, STAGE_MIN_DWELL_S=1.0,
        VERIFY_CLEAR_FRAMES=12, POST_WET_S=3, SUPPRESSION_MAX_S=60, COOLDOWN_S=5,
    )
