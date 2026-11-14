import pytest
from pydantic import ValidationError

from app.config import Settings, apply_updates


def test_apply_updates_validates_everything_before_applying():
    s = Settings(_env_file=None)
    before = s.NOZZLE_ANGLE_DEG
    with pytest.raises(ValidationError):
        apply_updates(s, {"NOZZLE_ANGLE_DEG": 45, "CONFIDENCE_THRESHOLD": 5})
    assert s.NOZZLE_ANGLE_DEG == before  # nothing half-applied


def test_apply_updates_rejects_unknown_and_inconsistent_keys():
    s = Settings(_env_file=None)
    with pytest.raises(ValueError, match="Not editable"):
        apply_updates(s, {"DB_PATH": "x.db"})
    with pytest.raises(ValueError, match="cannot exceed"):
        apply_updates(s, {"TEMPORAL_WINDOW": 5, "TEMPORAL_MIN_POSITIVE": 8})
    with pytest.raises(ValueError, match="MIN_PRESSURE"):
        apply_updates(s, {"MIN_PRESSURE": 9, "MAX_PRESSURE": 8})


def test_apply_updates_applies_valid_values():
    s = Settings(_env_file=None)
    assert apply_updates(s, {"NOZZLE_ANGLE_DEG": 40.0, "DEMO_MODE": False}) == {"NOZZLE_ANGLE_DEG": 40.0,
                                                                                "DEMO_MODE": False}
    assert s.NOZZLE_ANGLE_DEG == 40.0 and s.DEMO_MODE is False


def test_old_env_file_with_removed_keys_still_loads(tmp_path):
    env = tmp_path / ".env"
    env.write_text("PRESSURE_BASE=1.0\nPRESSURE_FACTOR=5.0\nDEMO_MODE=false\n", encoding="utf-8")
    s = Settings(_env_file=str(env))
    assert s.DEMO_MODE is False


def test_class_lists_are_normalised():
    s = Settings(_env_file=None, FIRE_CLASSES=" Fire , flame,", SMOKE_CLASSES="SMOKE")
    assert s.fire_classes == {"fire", "flame"} and s.smoke_classes == {"smoke"}
