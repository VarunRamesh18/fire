import { useState, useEffect, useCallback } from 'react';
import { WebSocketService } from '../services/websocket';
import { getWebSocketUrl } from '../services/api';

export default function useWebSocket() {
  const [telemetry, setTelemetry] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [error, setError] = useState(null);

  const handleMessage = useCallback((data) => {
    if (data && data.system_state) setTelemetry(data);
  }, []);

  const handleStatus = useCallback((status) => {
    setIsConnected(status.connected);
    setReconnectAttempts(status.reconnectAttempts);
    setError(status.error);
  }, []);

  useEffect(() => {
    const ws = new WebSocketService();
    ws.connect(getWebSocketUrl(), handleMessage, handleStatus);
    return () => ws.disconnect();
  }, [handleMessage, handleStatus]);

  return { telemetry, isConnected, reconnectAttempts, error };
}
