// All requests are same-origin: the Vite dev/preview server proxies /api and /ws to the
// FastAPI backend, so the dashboard also works when opened from another device.
const API_BASE = '';

async function request(endpoint, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
  } catch {
    throw new Error('Backend server is not reachable. Ensure the FastAPI server is running on port 8000.');
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return response;
}

const json = (p) => p.then((r) => r.json());
const post = (endpoint, body) => json(request(endpoint, { method: 'POST', body: JSON.stringify(body ?? {}) }));

export const getStatus = () => json(request('/api/status'));
export const getLatestTelemetry = () => json(request('/api/telemetry/latest'));

function qs(params = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') q.set(k, v); });
  const s = q.toString();
  return s ? `?${s}` : '';
}

export const getEvents = (params) => json(request(`/api/events${qs(params)}`));
export const getIncidents = (params) => json(request(`/api/incidents${qs(params)}`));
export const getEventStats = () => json(request('/api/events/stats'));
export const exportEventsCSV = () => request('/api/events/export/csv').then((r) => r.blob());

export const getSettings = () => json(request('/api/settings'));
export const updateSettings = (values) => post('/api/settings', values);
export const toggleDemoMode = () => post('/api/demo/toggle');
export const getSensors = () => json(request('/api/sensors'));

export const getScenario = () => json(request('/api/scenario'));
export const scenarioAction = (action, extra = {}) => post('/api/scenario', { action, ...extra });
export const resetPipeline = () => post('/api/pipeline/reset');

export const getCameraStreamUrl = () => `${API_BASE}/api/stream/camera`;

export function getWebSocketUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/telemetry`;
}

export { API_BASE };
