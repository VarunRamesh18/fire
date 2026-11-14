"""API smoke tests - start the real app (loops, model, video threads) against a temp database."""

import time

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("api")
    saved = {k: getattr(settings, k) for k in ("DB_PATH", "RUNTIME_SETTINGS_PATH", "DEMO_MODE", "CAMERA_URL")}
    settings.DB_PATH = str(tmp / "test.db")
    settings.RUNTIME_SETTINGS_PATH = str(tmp / "runtime.json")
    settings.DEMO_MODE = True
    with TestClient(main.app) as c:
        yield c
    for k, v in saved.items():
        setattr(settings, k, v)


def test_health_and_status(client):
    assert client.get("/").json()["status"] == "ok"
    st = client.get("/api/status").json()
    assert st["system_state"] == "MONITORING"
    assert st["detector_mode"] in ("yolov8", "colour-fallback")


def test_telemetry_shape(client):
    time.sleep(1.0)
    t = client.get("/api/telemetry/latest").json()
    for key in ("system_state", "confidence", "pipeline", "sensors", "detector", "timestamp"):
        assert key in t
    assert t["timestamp"].endswith("+00:00")  # timezone-aware
    assert len(t["pipeline"]["stages"]) == 9
    assert t["sensors"]["smoke"]["simulated"] is True


def test_settings_mask_credentials_and_validate(client):
    settings.CAMERA_URL = "rtsp://admin:secret@10.0.0.5:554/stream"
    vals = client.get("/api/settings").json()["values"]
    assert "secret" not in vals["CAMERA_URL"] and "****" in vals["CAMERA_URL"]
    # sending the masked value back does not overwrite the real one
    client.post("/api/settings", json={"CAMERA_URL": vals["CAMERA_URL"]})
    assert settings.CAMERA_URL.endswith("admin:secret@10.0.0.5:554/stream")
    assert client.post("/api/settings", json={"CONFIDENCE_THRESHOLD": 3}).status_code == 422
    assert client.post("/api/settings", json={"DB_PATH": "x.db"}).status_code == 422
    r = client.post("/api/settings", json={"YOLO_MODEL_PATH": "../../evil.pt"})
    assert r.status_code == 422 and "models" in r.json()["detail"]
    ok = client.post("/api/settings", json={"NOZZLE_ANGLE_DEG": 35})
    assert ok.status_code == 200 and ok.json()["applied"] == ["NOZZLE_ANGLE_DEG"]
    assert settings.NOZZLE_ANGLE_DEG == 35


def test_scenario_actions(client):
    sc = client.get("/api/scenario").json()
    assert "clips" in sc and "scene" in sc
    assert client.post("/api/scenario", json={"action": "set_distance", "distance_m": 3.5}).json()["scene"][
        "distance_m"] == 3.5
    assert client.post("/api/scenario", json={"action": "set_distance", "distance_m": 50}).status_code == 422
    assert client.post("/api/scenario", json={"action": "inject_smoke", "duration_s": 2}).status_code == 200
    assert client.post("/api/scenario", json={"action": "reset"}).json()["scene"]["mode"] == "normal"
    assert client.post("/api/scenario", json={"action": "explode"}).status_code == 422


def test_history_endpoints(client):
    inc = client.get("/api/incidents").json()
    assert set(inc) >= {"incidents", "total"}
    ev = client.get("/api/events?limit=5").json()
    assert set(ev) >= {"events", "total"}
    stats = client.get("/api/events/stats").json()
    assert "total_incidents" in stats
    csv = client.get("/api/events/export/csv")
    assert csv.status_code == 200 and csv.text.startswith("id,started_at")
