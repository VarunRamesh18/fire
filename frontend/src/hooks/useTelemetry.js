import { useState, useEffect, useRef } from 'react';
import useWebSocket from './useWebSocket';

const MAX_HISTORY = 240; // 60 s at 4 Hz
const MAX_FRAMES = 50;

export default function useTelemetry() {
  const { telemetry: t, isConnected, reconnectAttempts, error } = useWebSocket();
  const [telemetryHistory, setTelemetryHistory] = useState([]);
  const [frameRecords, setFrameRecords] = useState([]);
  const lastFrameIdRef = useRef(null);

  useEffect(() => {
    if (!t) return;
    const sup = t.pipeline?.suppression ?? {};
    setTelemetryHistory((prev) => {
      const next = [...prev, {
        timestamp: t.timestamp,
        confidence: t.confidence,
        fire_detected: t.fire_detected,
        distance_m: t.sensors?.lidar?.distance_m ?? null,
        smoke_ppm: t.sensors?.smoke?.ppm ?? null,
        smoke_threshold: t.sensors?.smoke?.threshold_ppm ?? null,
        estimated_pressure_bar: t.estimated_pressure_bar,
        estimated_pressure_psi: t.estimated_pressure_psi,
        pump_bar: sup.pump_pressure_bar ?? 0,
        flow_lpm: sup.flow_lpm ?? 0,
        intensity: t.scene?.intensity ?? null,
        system_state: t.system_state,
      }];
      return next.length > MAX_HISTORY ? next.slice(-MAX_HISTORY) : next;
    });

    if (t.frame_id !== lastFrameIdRef.current) {
      lastFrameIdRef.current = t.frame_id;
      setFrameRecords((prev) => {
        const next = [...prev, {
          frame_id: t.frame_id,
          timestamp: t.timestamp,
          fire_detected: t.fire_detected,
          confidence: t.confidence,
          smoke_triggered: t.smoke_triggered,
          distance_m: t.distance_m,
          estimated_pressure_bar: t.estimated_pressure_bar,
          system_decision: t.system_state,
        }];
        return next.length > MAX_FRAMES ? next.slice(-MAX_FRAMES) : next;
      });
    }
  }, [t]);

  return {
    latestTelemetry: t,
    telemetryHistory,
    frameRecords,
    fireDetectionHistory: telemetryHistory.map(({ timestamp, confidence, fire_detected }) => ({ timestamp, confidence, fire_detected })),
    distanceHistory: telemetryHistory.map(({ timestamp, distance_m }) => ({ timestamp, distance_m })),
    pressureHistory: telemetryHistory.map(({ timestamp, estimated_pressure_bar, pump_bar }) => ({ timestamp, estimated_pressure_bar, pump_bar })),
    isConnected,
    reconnectAttempts,
    error,
    demoMode: t?.demo_mode || false,
  };
}
