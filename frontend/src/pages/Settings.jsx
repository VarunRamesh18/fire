import { useEffect, useMemo, useState } from 'react';
import {
  Settings as SettingsIcon, Camera, Brain, Timer, Cpu, Gauge, Droplets, Save, CheckCircle, AlertCircle, RotateCcw, Waves,
} from 'lucide-react';
import { getSettings, updateSettings } from '../services/api';

const n = (key, label, opts = {}) => ({ key, label, type: 'number', ...opts });

const GROUPS = [
  {
    title: 'Camera / video source', icon: Camera, fields: [
      { key: 'CAMERA_SOURCE', label: 'Source', type: 'select', options: [
        ['scenario', 'Scenario clips (simulation)'], ['ip', 'IP camera'], ['webcam', 'Local webcam']] },
      { key: 'CAMERA_URL', label: 'IP camera URL', type: 'text', show: (v) => v.CAMERA_SOURCE === 'ip',
        help: 'HTTP/MJPEG or RTSP. Credentials are masked when displayed.' },
      n('WEBCAM_INDEX', 'Webcam index', { step: 1, show: (v) => v.CAMERA_SOURCE === 'webcam' }),
      n('CAMERA_HFOV_DEG', 'Horizontal field of view', { unit: '°', step: 1, help: 'Used for pan/tilt aiming and fire-size estimation' }),
    ],
  },
  {
    title: 'YOLOv8 detection', icon: Brain, fields: [
      { key: 'YOLO_MODEL_PATH', label: 'Model weights', type: 'model', help: 'Files in backend/models/' },
      { key: 'CONFIDENCE_THRESHOLD', label: 'Alarm confidence threshold', type: 'range', min: 0.05, max: 0.95, step: 0.01 },
      { key: 'YOLO_IMGSZ', label: 'Inference size', type: 'select', options: [[320, '320 px (fastest)'], [480, '480 px'], [640, '640 px (trained size)'], [800, '800 px']] },
      { key: 'FIRE_CLASSES', label: 'Fire class names', type: 'text', help: 'Comma separated, matched to the model classes' },
      { key: 'SMOKE_CLASSES', label: 'Smoke class names', type: 'text' },
    ],
  },
  {
    title: 'Temporal validation', icon: Timer, fields: [
      n('TEMPORAL_WINDOW', 'Window size', { unit: 'frames', step: 1 }),
      n('TEMPORAL_MIN_POSITIVE', 'Positive frames required', { unit: 'frames', step: 1 }),
      n('TEMPORAL_MIN_IOU', 'Min. box overlap (IoU)', { step: 0.01 }),
      n('TEMPORAL_TIMEOUT_S', 'Reject if not validated within', { unit: 's', step: 0.5 }),
    ],
  },
  {
    title: 'Sensors', icon: Cpu, fields: [
      { key: 'DEMO_MODE', label: 'Simulated MQ-2 / TF-Luna sensors', type: 'toggle', help: 'Off = read the Arduino over serial' },
      { key: 'ARDUINO_PORT', label: 'Arduino port', type: 'text', show: (v) => !v.DEMO_MODE },
      { key: 'BAUD_RATE', label: 'Baud rate', type: 'select', options: [[9600, '9600'], [19200, '19200'], [57600, '57600'], [115200, '115200']], show: (v) => !v.DEMO_MODE },
      n('SMOKE_THRESHOLD_PPM', 'Smoke alarm threshold', { unit: 'ppm', step: 10 }),
      n('SENSOR_FUSION_TIMEOUT_S', 'Wait for smoke corroboration', { unit: 's', step: 1 }),
      n('LIDAR_SAMPLES', 'LiDAR samples (median filter)', { step: 1 }),
    ],
  },
  {
    title: 'Nozzle & geometry', icon: Droplets, fields: [
      n('NOZZLE_HEIGHT_M', 'Nozzle height above fire base', { unit: 'm', step: 0.1 }),
      n('TARGET_HEIGHT_M', 'Aim point above fire base', { unit: 'm', step: 0.05 }),
      n('NOZZLE_ANGLE_DEG', 'Nozzle elevation angle', { unit: '°', step: 1 }),
      n('NOZZLE_DIAMETER_MM', 'Nozzle orifice diameter', { unit: 'mm', step: 0.5 }),
      n('NOZZLE_CD', 'Discharge coefficient Cd', { step: 0.01 }),
      n('NOZZLE_CV', 'Velocity coefficient Cv', { step: 0.01 }),
      n('DRAG_MARGIN', 'Air-drag velocity margin', { step: 0.01, help: '0.10 = +10 % jet speed' }),
    ],
  },
  {
    title: 'Pipe & pump', icon: Waves, fields: [
      n('PIPE_LENGTH_M', 'Pipe length', { unit: 'm', step: 0.5 }),
      n('PIPE_DIAMETER_MM', 'Pipe inner diameter', { unit: 'mm', step: 1 }),
      n('PIPE_ROUGHNESS_MM', 'Pipe roughness ε', { unit: 'mm', step: 0.0005 }),
      n('MINOR_LOSS_K', 'Fittings/valve loss ΣK', { step: 0.1 }),
      n('PUMP_ELEVATION_M', 'Nozzle height above pump', { unit: 'm', step: 0.1 }),
      n('MIN_PRESSURE', 'Pump minimum pressure', { unit: 'bar', step: 0.1 }),
      n('MAX_PRESSURE', 'Pump maximum pressure', { unit: 'bar', step: 0.1 }),
      n('DESIGN_DENSITY_LPM_M2', 'Water application rate', { unit: 'L/min/m²', step: 0.1, help: 'NFPA 13 ordinary hazard 1 = 6.1' }),
    ],
  },
  {
    title: 'Suppression control & pacing', icon: Gauge, fields: [
      n('KNOCKDOWN_REF_S', 'Knock-down time at design flow', { unit: 's', step: 0.5 }),
      n('VERIFY_CLEAR_FRAMES', 'Fire-free frames to verify', { step: 1 }),
      n('POST_WET_S', 'Post-wetting time', { unit: 's', step: 0.5 }),
      n('SUPPRESSION_MAX_S', 'Escalate if not out within', { unit: 's', step: 5 }),
      n('COOLDOWN_S', 'Re-arm after', { unit: 's', step: 1 }),
      n('STAGE_MIN_DWELL_S', 'Min. time per stage on screen', { unit: 's', step: 0.1, help: 'Presentation pacing - 0 for real-time behaviour' }),
    ],
  },
];

const inputCls = 'w-full px-3 py-2 rounded-lg bg-[#252b3b] border border-[#2a3142] text-xs text-white focus:border-blue-500 focus:outline-none';

function Field({ f, value, onChange, models }) {
  if (f.type === 'toggle') {
    return (
      <button type="button" onClick={() => onChange(!value)} className="flex items-center gap-3">
        <span className={`relative w-10 h-5 rounded-full transition-colors ${value ? 'bg-orange-500' : 'bg-[#252b3b] border border-[#2a3142]'}`}>
          <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${value ? 'translate-x-5' : ''}`} />
        </span>
        <span className="text-xs text-gray-300">{value ? 'Simulated' : 'Real hardware (Arduino)'}</span>
      </button>
    );
  }
  if (f.type === 'select' || f.type === 'model') {
    const opts = f.type === 'model' ? models.map((m) => [m, m]) : f.options;
    return (
      <select value={value ?? ''} onChange={(e) => onChange(typeof opts[0]?.[0] === 'number' ? Number(e.target.value) : e.target.value)} className={inputCls}>
        {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    );
  }
  if (f.type === 'range') {
    return (
      <div>
        <input type="range" min={f.min} max={f.max} step={f.step} value={value ?? 0} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-orange-500" />
        <div className="flex justify-between text-[10px] text-gray-500"><span>sensitive</span><span className="font-mono text-gray-200">{Math.round((value ?? 0) * 100)}%</span><span>strict</span></div>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <input type={f.type === 'number' ? 'number' : 'text'} step={f.step} value={value ?? ''}
        onChange={(e) => onChange(f.type === 'number' ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value)} className={inputCls} />
      {f.unit && <span className="text-[10px] text-gray-500 whitespace-nowrap">{f.unit}</span>}
    </div>
  );
}

export default function Settings() {
  const [original, setOriginal] = useState(null);
  const [form, setForm] = useState({});
  const [models, setModels] = useState([]);
  const [detector, setDetector] = useState(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = () => getSettings().then((d) => {
    setOriginal(d.values);
    setForm(d.values);
    setModels(d.models ?? []);
    setDetector(d.detector);
  }).catch((e) => setNotice({ type: 'error', msg: e.message }));
  useEffect(() => { load(); }, []);

  const changed = useMemo(() => (original
    ? Object.fromEntries(Object.entries(form).filter(([k, v]) => v !== original[k]))
    : {}), [form, original]);

  const save = async () => {
    setSaving(true);
    try {
      const res = await updateSettings(changed);
      setOriginal(res.values);
      setForm(res.values);
      setDetector(res.detector);
      setNotice({ type: 'success', msg: res.applied.length ? `Saved: ${res.applied.join(', ')}` : 'Nothing changed' });
    } catch (e) {
      setNotice({ type: 'error', msg: e.message });
    } finally {
      setSaving(false);
      setTimeout(() => setNotice(null), 6000);
    }
  };

  if (!original) {
    return (
      <div className="mt-2 flex items-center justify-center h-64">
        {notice ? <p className="text-sm text-red-400">{notice.msg}</p>
          : <div className="w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />}
      </div>
    );
  }

  const dirty = Object.keys(changed).length;
  return (
    <div className="mt-2 space-y-4 pb-16">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <SettingsIcon className="w-5 h-5 text-gray-400" />
          <h1 className="text-lg font-bold text-white">System Settings</h1>
          <span className="text-xs text-gray-500">Saved to runtime_settings.json and applied immediately</span>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setForm(original)} disabled={!dirty}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#252b3b] border border-[#2a3142] text-gray-300 text-xs disabled:opacity-40">
            <RotateCcw className="w-3.5 h-3.5" /> Discard
          </button>
          <button onClick={save} disabled={saving || !dirty}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-orange-500 text-white text-xs font-semibold hover:bg-orange-600 disabled:opacity-40">
            <Save className="w-3.5 h-3.5" /> {saving ? 'Saving...' : `Save${dirty ? ` (${dirty})` : ''}`}
          </button>
        </div>
      </div>

      {notice && (
        <div className={`flex items-center gap-2 px-4 py-3 rounded-lg border animate-slide-in ${
          notice.type === 'success' ? 'bg-green-500/10 border-green-500/20 text-green-400' : 'bg-red-500/10 border-red-500/20 text-red-400'}`}>
          {notice.type === 'success' ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
          <span className="text-xs">{notice.msg}</span>
        </div>
      )}
      {detector?.load_error && (
        <div className="px-4 py-3 rounded-lg border border-yellow-500/30 bg-yellow-500/10 text-xs text-yellow-300">
          YOLO model not loaded: {detector.load_error}. The colour-segmentation fallback is being used.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4">
        {GROUPS.map((g) => (
          <div key={g.title} className="bg-[#1a1f2e] rounded-xl border border-[#2a3142] p-5">
            <div className="flex items-center gap-2 mb-4 pb-3 border-b border-[#2a3142]">
              <g.icon className="w-4 h-4 text-gray-400" />
              <span className="text-sm font-semibold text-gray-200">{g.title}</span>
              {g.title.startsWith('YOLOv8') && detector?.classes && (
                <span className="ml-auto text-[10px] text-gray-500">classes: {Object.values(detector.classes).join(', ')}</span>
              )}
            </div>
            <div className="space-y-3">
              {g.fields.filter((f) => !f.show || f.show(form)).map((f) => (
                <div key={f.key}>
                  <label className={`text-xs font-medium block mb-1 ${changed[f.key] !== undefined ? 'text-orange-300' : 'text-gray-300'}`}>{f.label}</label>
                  <Field f={f} value={form[f.key]} models={models} onChange={(v) => setForm((p) => ({ ...p, [f.key]: v }))} />
                  {f.help && <p className="text-[10px] text-gray-500 mt-1">{f.help}</p>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
