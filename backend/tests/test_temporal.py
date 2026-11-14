from app.temporal import TemporalValidator, iou


def box(x, conf=0.8, w=100):
    return [{"x1": x, "y1": 100, "x2": x + w, "y2": 200, "conf": conf}]


def test_iou():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == 1 / 3


def test_persistent_consistent_fire_passes():
    v = TemporalValidator(15, 10, 0.1)
    for i in range(9):
        v.update(box(100 + i), 0.5)
        assert not v.passed
    v.update(box(110), 0.5)
    assert v.passed
    st = v.status()
    assert st["positives"] == 10 and st["required"] == 10
    assert st["window"][:10] == [1] * 10 and st["window"][10:] == [None] * 5


def test_flicker_is_not_validated():
    v = TemporalValidator(15, 10, 0.1)
    for i in range(30):
        v.update(box(100) if i % 2 else [], 0.5)
    assert not v.passed  # only ~7-8 of 15 frames positive


def test_jumping_boxes_fail_spatial_consistency():
    v = TemporalValidator(15, 10, 0.1)
    for i in range(15):
        v.update(box(0 if i % 2 else 700), 0.5)
    assert v.positives == 15
    assert v.consistency == 0.0
    assert not v.passed


def test_low_confidence_not_counted():
    v = TemporalValidator(15, 10, 0.1)
    for _ in range(15):
        v.update(box(100, conf=0.3), 0.5)
    assert v.positives == 0


def test_reconfigure_keeps_recent_history():
    v = TemporalValidator(15, 10, 0.1)
    for _ in range(12):
        v.update(box(100), 0.5)
    v.configure(10, 8, 0.1)
    assert v.positives == 10 and v.passed
