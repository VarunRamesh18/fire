"""
FireGuard AI - FastAPI application.

Three background loops:
  * detection_loop  - latest camera frame -> YOLOv8 -> pipeline.on_frame()        (~12 fps)
  * telemetry_loop  - scene physics, sensors -> pipeline.on_tick(), WebSocket push (4 Hz)
  * display_loop    - annotated camera view encoded as JPEG for the MJPEG stream   (~25 fps)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import cv2
import numpy as np
from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import ValidationError

from app import database as db
from app import overlay
from app.config import apply_updates, editable_values, save_runtime_overrides, settings
from app.detection import DetectionEngine
from app.hardware import ArduinoSensors
from app.pipeline import Pipeline, SensorReading
from app.schemas import ScenarioAction
from app.simulation import FireScene, LidarSim, SmokeSensorSim
from app.video import StreamPlayer, placeholder_frame
from app.websocket import ConnectionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(name)-22s  %(levelname)-7s  %(message)s")
logger = logging.getLogger("fireguard.main")


class Runtime:
    """All live objects of the running system."""

    def __init__(self) -> None:
        self.engine = DetectionEngine()
        self.pipeline = Pipeline(settings)
        self.scene = FireScene(settings.path(settings.MEDIA_DIR), settings.SIM_FIRE_DISTANCE_M)
        self.stream: Optional[StreamPlayer] = None
        self.smoke = SmokeSensorSim()
        self.lidar = LidarSim()
        self.arduino: Optional[ArduinoSensors] = None
        self.ws = ConnectionManager()
        self.detections: list = []
        self.frame_no = 0
        self.det_times: list[float] = []
        self.jpeg: Optional[bytes] = None
        self.sensor_status: Dict[str, Any] = {}
        self.reading: Optional[SensorReading] = None
        self.tasks: list[asyncio.Task] = []
        self.running = False

    # ---- sources ------------------------------------------------------------
    def start_source(self) -> None:
        self.stop_source()
        if settings.CAMERA_SOURCE == "scenario":
            self.scene.start()
        else:
            src: Any = settings.WEBCAM_INDEX if settings.CAMERA_SOURCE == "webcam" else settings.CAMERA_URL
            self.stream = StreamPlayer(src)
            self.stream.start()

    def stop_source(self) -> None:
        self.scene.stop()
        if self.stream is not None:
            self.stream.stop()
            self.stream = None

    def camera_frame(self) -> Optional[np.ndarray]:
        if settings.CAMERA_SOURCE == "scenario":
            return self.scene.camera_frame()
        return self.stream.latest() if self.stream else None

    @property
    def camera_connected(self) -> bool:
        if settings.CAMERA_SOURCE == "scenario":
            return self.scene.video_connected
        return bool(self.stream and self.stream.connected)

    @property
    def video_fps(self) -> float:
        if settings.CAMERA_SOURCE == "scenario":
            return self.scene.status()["video_fps"]
        return round(self.stream.fps, 1) if self.stream else 0.0

    @property
    def detection_fps(self) -> float:
        t = self.det_times
        return round((len(t) - 1) / (t[-1] - t[0]), 1) if len(t) > 1 and t[-1] > t[0] else 0.0

    def start_sensors(self) -> None:
        self.stop_sensors()
        self.smoke.reset()
        self.lidar.reset()
        if not settings.DEMO_MODE:
            self.arduino = ArduinoSensors(settings.ARDUINO_PORT, settings.BAUD_RATE)
            self.arduino.start()

    def stop_sensors(self) -> None:
        if self.arduino is not None:
            self.arduino.stop()
            self.arduino = None


rt = Runtime()


# ---------------------------------------------------------------------------
# loops
# ---------------------------------------------------------------------------


async def persist_events() -> None:
    for ev in rt.pipeline.drain_events():
        try:
            if ev["type"] == "transition":
                await db.save_transition(ev)
            else:
                await db.save_incident(ev["incident"])
        except Exception as exc:
            logger.error("Failed to store %s: %s", ev["type"], exc)


async def detection_loop() -> None:
    while rt.running:
        t0 = time.perf_counter()
        try:
            frame = rt.camera_frame()
            if frame is None:
                await asyncio.sleep(0.1)
                continue
            dets = await rt.engine.detect(frame)
            now = time.time()
            rt.detections = dets
            rt.frame_no += 1
            rt.det_times = [t for t in rt.det_times if now - t < 3.0] + [now]
            rt.pipeline.on_frame(dets, frame.shape[1], frame.shape[0], now)
            await persist_events()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Detection loop error: %s", exc, exc_info=True)
            await asyncio.sleep(0.5)
        spare = 1.0 / settings.DETECTION_MAX_FPS - (time.perf_counter() - t0)
        await asyncio.sleep(max(0.0, spare))


def read_sensors(now: float, dt: float) -> SensorReading:
    if settings.DEMO_MODE:
        src = rt.scene.smoke_source_ppm(now, settings.SMOKE_MAX_PPM)
        s = rt.smoke.update(now, dt, src, settings.SMOKE_TRANSPORT_DELAY_S, settings.SMOKE_RISE_TAU_S,
                            settings.SMOKE_THRESHOLD_PPM, settings.SMOKE_HYSTERESIS_PPM)
        target = rt.scene.lidar_target_m(rt.pipeline.aimed_at_fire)
        ls = rt.lidar.update(now, dt, target, s["ppm"])
        rt.sensor_status = {
            "smoke": {**s, "online": True, "simulated": True},
            "lidar": {"distance_m": ls.distance_m, "valid": ls.valid, "strength": ls.strength,
                      "aimed_at_fire": rt.pipeline.aimed_at_fire, "online": True, "simulated": True},
        }
        return SensorReading(s["ppm"], s["triggered"], s["adc"], ls.distance_m, ls.valid, ls.strength)
    r = rt.arduino.reading() if rt.arduino else SensorReading(None, False, None, None, False, None, online=False)
    rt.sensor_status = {
        "smoke": {"ppm": r.smoke_ppm, "adc": r.smoke_adc, "triggered": r.smoke_triggered,
                  "threshold_ppm": settings.SMOKE_THRESHOLD_PPM, "online": r.online, "simulated": False},
        "lidar": {"distance_m": r.lidar_distance_m, "valid": r.lidar_valid, "strength": r.lidar_strength,
                  "aimed_at_fire": rt.pipeline.aimed_at_fire, "online": r.online, "simulated": False},
    }
    return r


def build_telemetry(now: float) -> Dict[str, Any]:
    p = rt.pipeline
    snap = p.snapshot(now, rt.detection_fps)
    fire = [d for d in rt.detections if d.get("kind") == "fire"]
    smoke_v = [d for d in rt.detections if d.get("kind") == "smoke"]
    best = max((d["conf"] for d in fire), default=0.0)
    h = p.hydraulics
    r = rt.reading
    return {
        # summary fields (used across the dashboard)
        "frame_id": rt.frame_no,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fire_detected": p.last_positive,
        "confidence": round(best, 4),
        "visual_smoke_confidence": round(max((d["conf"] for d in smoke_v), default=0.0), 4),
        "smoke_triggered": bool(r and r.smoke_triggered),
        "smoke_ppm": r.smoke_ppm if r else None,
        "distance_m": (p.distance or {}).get("median_m") or (r.lidar_distance_m if r else None),
        "estimated_pressure_bar": h["pump_pressure_bar"] if h and h.get("reachable") else None,
        "estimated_pressure_psi": h["pump_pressure_psi"] if h and h.get("reachable") else None,
        "system_state": p.state.value,
        "bounding_boxes": rt.detections,
        "fps": rt.video_fps,
        "detection_fps": rt.detection_fps,
        "inference_ms": round(rt.engine.last_inference_ms, 1),
        "camera_connected": rt.camera_connected,
        "camera_source": settings.CAMERA_SOURCE,
        "arduino_connected": bool(rt.arduino and rt.arduino.connected),
        "smoke_sensor_connected": bool(rt.sensor_status.get("smoke", {}).get("online")),
        "lidar_connected": bool(rt.sensor_status.get("lidar", {}).get("online")),
        "demo_mode": settings.DEMO_MODE,
        "detector": {
            "mode": rt.engine.mode, "model_path": rt.engine.model_path, "classes": rt.engine.class_names,
            "threshold": settings.CONFIDENCE_THRESHOLD, "load_error": rt.engine.load_error,
            "imgsz": settings.YOLO_IMGSZ, "threads": rt.engine.threads,
        },
        "sensors": rt.sensor_status,
        "pipeline": snap,
        "scene": rt.scene.status() if settings.CAMERA_SOURCE == "scenario" else None,
    }


async def telemetry_loop() -> None:
    last = time.time()
    while rt.running:
        try:
            now = time.time()
            dt = max(1e-3, now - last)
            last = now
            p = rt.pipeline
            rt.scene.apply_water(p.flow_lpm, p.required_flow_lpm, p.pressure_ratio)
            rt.scene.tick(now, dt, settings.KNOCKDOWN_REF_S)
            rt.reading = read_sensors(now, dt)
            p.on_tick(rt.reading, now, dt)
            await persist_events()
            await rt.ws.broadcast(build_telemetry(now))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Telemetry loop error: %s", exc, exc_info=True)
        await asyncio.sleep(settings.WS_BROADCAST_INTERVAL)


def _render_jpeg(frame: Optional[np.ndarray], snap: Dict[str, Any], dets: list, lidar: Optional[float],
                 inference_ms: float, frame_no: int) -> Optional[bytes]:
    if frame is None:
        frame = placeholder_frame("No video")
    img = overlay.render(frame, dets, snap, settings.CONFIDENCE_THRESHOLD, inference_ms, frame_no,
                         settings.CAMERA_SOURCE == "scenario", lidar)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes() if ok else None


async def display_loop() -> None:
    loop = asyncio.get_running_loop()
    while rt.running:
        try:
            if rt.ws.get_connection_count() > 0 or _stream_clients > 0:
                # snapshot state on the event loop; only pixel work runs in the worker thread
                args = (rt.camera_frame(), rt.pipeline.snapshot(time.time(), rt.detection_fps), rt.detections,
                        rt.sensor_status.get("lidar", {}).get("distance_m"), rt.engine.last_inference_ms,
                        rt.frame_no)
                rt.jpeg = await loop.run_in_executor(None, _render_jpeg, *args)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Display loop error: %s", exc)
        await asyncio.sleep(0.05)


_stream_clients = 0


# ---------------------------------------------------------------------------
# app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting FireGuard AI (source=%s, simulated sensors=%s)", settings.CAMERA_SOURCE, settings.DEMO_MODE)
    await db.init_db()
    await rt.engine.load_model()
    rt.start_source()
    rt.start_sensors()
    rt.running = True
    rt.tasks = [asyncio.create_task(f()) for f in (detection_loop, telemetry_loop, display_loop)]
    yield
    rt.running = False
    for t in rt.tasks:
        t.cancel()
    await asyncio.gather(*rt.tasks, return_exceptions=True)
    rt.stop_source()
    rt.stop_sensors()
    await db.close_db()
    logger.info("FireGuard AI stopped.")


app = FastAPI(title="FireGuard AI Backend", version="2.0.0", lifespan=lifespan,
              description="YOLOv8 fire detection -> temporal validation -> sensor fusion -> "
                          "LiDAR distance -> hydraulic pressure estimation -> suppression.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.get("/", tags=["Health"])
async def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "FireGuard AI", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/status", tags=["Status"])
async def status() -> Dict[str, Any]:
    return {
        "system_state": rt.pipeline.state.value,
        "camera_source": settings.CAMERA_SOURCE,
        "camera_connected": rt.camera_connected,
        "demo_mode": settings.DEMO_MODE,
        "model_loaded": rt.engine.model_loaded,
        "detector_mode": rt.engine.mode,
        "detection_fps": rt.detection_fps,
        "ws_connections": rt.ws.get_connection_count(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/telemetry/latest", tags=["Telemetry"])
async def latest_telemetry() -> Dict[str, Any]:
    return build_telemetry(time.time())


# ---- scenario (presenter controls) ------------------------------------------


@app.get("/api/scenario", tags=["Scenario"])
async def get_scenario() -> Dict[str, Any]:
    return {"scene": rt.scene.status(), "clips": rt.scene.clips, "camera_source": settings.CAMERA_SOURCE}


@app.post("/api/scenario", tags=["Scenario"])
async def scenario_action(body: ScenarioAction) -> Dict[str, Any]:
    now = time.time()
    s = rt.scene
    if body.action == "ignite":
        if body.fire_clip:
            s.select_clips(None, body.fire_clip)
        s.ignite(now)
    elif body.action == "false_alarm":
        s.false_alarm(now, body.duration_s or 0.5)
    elif body.action == "inject_smoke":
        s.inject_smoke(now, body.duration_s or 10.0)
    elif body.action == "set_distance":
        if body.distance_m is None:
            raise HTTPException(422, "distance_m required")
        s.distance_m = body.distance_m
    elif body.action == "select_clips":
        s.select_clips(body.normal_clip, body.fire_clip)
    elif body.action in ("pause", "resume"):
        s.set_paused(body.action == "pause")
    elif body.action == "reset":
        s.reset()
        rt.smoke.reset()
        rt.lidar.reset()
        rt.pipeline.reset(now)
        await persist_events()
    logger.info("Scenario action: %s", body.action)
    return {"scene": s.status()}


@app.post("/api/pipeline/reset", tags=["Scenario"])
async def pipeline_reset() -> Dict[str, Any]:
    rt.pipeline.reset(time.time())
    await persist_events()
    return {"state": rt.pipeline.state.value}


# ---- history ----------------------------------------------------------------


@app.get("/api/incidents", tags=["History"])
async def incidents(limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0),
                    start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    rows, total = await db.get_incidents(limit, offset, start_date, end_date)
    return {"incidents": rows, "total": total, "limit": limit, "offset": offset}


@app.get("/api/events", tags=["History"])
async def events(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                 start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    rows, total = await db.get_transitions(limit, offset, start_date, end_date)
    return {"events": rows, "total": total, "limit": limit, "offset": offset}


@app.get("/api/events/stats", tags=["History"])
async def stats() -> Dict[str, Any]:
    return await db.get_stats()


@app.get("/api/events/export/csv", tags=["History"])
async def export_csv() -> Response:
    return Response(content=await db.export_csv(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=fireguard_incidents.csv"})


# ---- settings ---------------------------------------------------------------

_CRED = re.compile(r"(//[^:/@]+:)([^@]+)@")


def _mask(url: str) -> str:
    return _CRED.sub(r"\1****@", url)


def settings_payload() -> Dict[str, Any]:
    values = editable_values(settings)
    values["CAMERA_URL"] = _mask(values["CAMERA_URL"])
    models = sorted(str(p.relative_to(settings.path("."))).replace("\\", "/")
                    for p in settings.path(settings.MODELS_DIR).glob("*.pt"))
    return {"values": values, "models": models, "detector": {"mode": rt.engine.mode, "classes": rt.engine.class_names,
                                                             "load_error": rt.engine.load_error}}


@app.get("/api/settings", tags=["Settings"])
async def get_settings() -> Dict[str, Any]:
    return settings_payload()


@app.post("/api/settings", tags=["Settings"])
async def update_settings(updates: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    if "CAMERA_URL" in updates and "****" in str(updates["CAMERA_URL"]):
        updates.pop("CAMERA_URL")  # masked value sent back unchanged
    updates = {k: v for k, v in updates.items() if getattr(settings, k, object()) != v}
    if "YOLO_MODEL_PATH" in updates:
        try:
            DetectionEngine.resolve_model_path(updates["YOLO_MODEL_PATH"])
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    try:
        applied = apply_updates(settings, updates)
    except ValidationError as exc:
        raise HTTPException(422, "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    save_runtime_overrides(settings)
    keys = set(applied)
    if keys & {"CAMERA_SOURCE", "CAMERA_URL", "WEBCAM_INDEX"}:
        rt.start_source()
    if keys & {"YOLO_MODEL_PATH"}:
        await rt.engine.load_model(settings.YOLO_MODEL_PATH)
    if keys & {"DEMO_MODE", "ARDUINO_PORT", "BAUD_RATE"}:
        rt.start_sensors()
    if keys & {"TEMPORAL_WINDOW", "TEMPORAL_MIN_POSITIVE", "TEMPORAL_MIN_IOU"}:
        rt.pipeline.reconfigure()
    logger.info("Settings updated: %s", ", ".join(sorted(keys)) or "(no changes)")
    return {"applied": sorted(keys), **settings_payload()}


@app.post("/api/demo/toggle", tags=["Settings"])
async def toggle_demo() -> Dict[str, Any]:
    apply_updates(settings, {"DEMO_MODE": not settings.DEMO_MODE})
    save_runtime_overrides(settings)
    rt.start_sensors()
    return {"demo_mode": settings.DEMO_MODE}


@app.get("/api/sensors", tags=["Sensors"])
async def sensors() -> Dict[str, Any]:
    return {"sensors": rt.sensor_status, "camera_connected": rt.camera_connected, "demo_mode": settings.DEMO_MODE}


# ---- streams ----------------------------------------------------------------


@app.get("/api/stream/camera", tags=["Stream"])
async def camera_stream() -> StreamingResponse:
    async def gen():
        global _stream_clients
        _stream_clients += 1
        try:
            last = None
            while True:
                jpeg = rt.jpeg
                if jpeg is not None and jpeg is not last:
                    last = jpeg
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                await asyncio.sleep(0.03)
        finally:
            _stream_clients -= 1

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


@app.websocket("/ws/telemetry")
async def ws_telemetry(websocket: WebSocket) -> None:
    await rt.ws.connect(websocket)
    try:
        while True:
            if (await websocket.receive_text()).strip().lower() == "ping":
                await websocket.send_json({"pong": True})
    except WebSocketDisconnect:
        pass
    finally:
        rt.ws.disconnect(websocket)
