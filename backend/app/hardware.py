"""
FireGuard AI - Real hardware (Arduino Nano + MQ-2 + TF-Luna) over serial.

Used when DEMO_MODE is false.  A background thread reads *every* line as it
arrives and keeps only the newest values, so readings never lag behind the
sensor (the Arduino sends ~5 lines/s; reading one line per telemetry tick would
let the serial buffer grow and the data get older and older).

Expected line format (extra fields optional):

    SMOKE:1,DIST:2.45
    SMOKE:1,PPM:540,DIST:2.45,STR:1830
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from app.pipeline import SensorReading

logger = logging.getLogger("fireguard.hardware")

STALE_AFTER_S = 2.0


def parse_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse one Arduino line. Returns None if it contains no known field."""
    out: Dict[str, Any] = {}
    for part in line.strip().split(","):
        key, sep, val = part.partition(":")
        if not sep:
            continue
        key, val = key.strip().upper(), val.strip()
        try:
            if key == "SMOKE":
                out["smoke"] = val == "1"
            elif key == "PPM":
                out["ppm"] = float(val)
            elif key == "DIST":
                out["dist"] = float(val)
            elif key == "STR":
                out["strength"] = int(float(val))
        except ValueError:
            continue
    return out or None


class ArduinoSensors:
    def __init__(self, port: str, baud: int) -> None:
        self.port, self.baud = port, baud
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._latest: Dict[str, Any] = {}
        self._last_rx = 0.0
        self.connected = False
        self.error: Optional[str] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ArduinoSensors")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self.connected = False

    def _run(self) -> None:
        try:
            import serial  # type: ignore
        except ImportError:
            self.error = "pyserial not installed"
            return
        backoff = 1.0
        while not self._stop.is_set():
            try:
                with serial.Serial(self.port, self.baud, timeout=0.5) as ser:
                    self.connected, self.error, backoff = True, None, 1.0
                    logger.info("Arduino connected on %s @ %d", self.port, self.baud)
                    while not self._stop.is_set():
                        raw = ser.readline()
                        if not raw:
                            continue
                        parsed = parse_line(raw.decode("utf-8", errors="replace"))
                        if parsed:
                            with self._lock:
                                self._latest.update(parsed)
                                self._last_rx = time.time()
            except Exception as exc:
                self.connected = False
                self.error = str(exc)
                logger.warning("Arduino on %s unavailable: %s (retry in %.0fs)", self.port, exc, backoff)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 15.0)

    def reading(self) -> SensorReading:
        with self._lock:
            d = dict(self._latest)
            fresh = time.time() - self._last_rx < STALE_AFTER_S
        dist = d.get("dist") if fresh else None
        valid = dist is not None and 0.2 <= dist <= 8.0
        return SensorReading(
            smoke_ppm=d.get("ppm") if fresh else None,
            smoke_triggered=bool(d.get("smoke")) if fresh else False,
            smoke_adc=None,
            lidar_distance_m=dist if valid else None,
            lidar_valid=valid,
            lidar_strength=d.get("strength") if fresh else None,
            online=fresh and self.connected,
        )
