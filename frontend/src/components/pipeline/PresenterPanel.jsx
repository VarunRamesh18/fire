import { useCallback, useEffect, useRef, useState } from 'react';
import { Flame, Zap, CloudFog, RotateCcw, Pause, Play, Ruler, Film, AlertCircle } from 'lucide-react';
import { getScenario, scenarioAction } from '../../services/api';

const SCENARIOS = [
  { action: 'ignite', key: 'i', label: 'Ignite fire', icon: Flame, style: 'bg-red-600 hover:bg-red-500 text-white',
    expect: 'Full pipeline: detect → validate → smoke → LiDAR → pressure → water → verified out' },
  { action: 'false_alarm', key: 'f', label: 'False alarm (flash)', icon: Zap, style: 'bg-[#252b3b] hover:bg-[#2f364a] text-yellow-300 border border-yellow-500/30',
    extra: { duration_s: 0.5 }, expect: '0.5 s flash → fails temporal validation → rejected, no water' },
  { action: 'inject_smoke', key: 's', label: 'Smoke only (cooking)', icon: CloudFog, style: 'bg-[#252b3b] hover:bg-[#2f364a] text-gray-200 border border-[#3a4256]',
    extra: { duration_s: 10 }, expect: 'MQ-2 alarm without flames → operator alert, no water' },
];

export default function PresenterPanel({ telemetry, shortcuts = false, compact = false, horizontal = false }) {
  const [clips, setClips] = useState([]);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [distance, setDistance] = useState(null);
  const debounce = useRef(null);
  const scene = telemetry?.scene;

  const load = useCallback(() => getScenario().then((d) => setClips(d.clips ?? [])).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (scene && distance === null) setDistance(scene.distance_m); }, [scene, distance]);

  const run = useCallback(async (action, extra = {}) => {
    setBusy(action);
    setError(null);
    try {
      await scenarioAction(action, extra);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }, []);

  const changeDistance = (v) => {
    setDistance(v);
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => run('set_distance', { distance_m: v }), 250);
  };

  useEffect(() => {
    if (!shortcuts) return undefined;
    const onKey = (e) => {
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
      const k = e.key.toLowerCase();
      const sc = SCENARIOS.find((s) => s.key === k);
      if (sc) { e.preventDefault(); run(sc.action, sc.extra); }
      else if (k === 'r') { e.preventDefault(); run('reset'); }
      else if (k === 'p') { e.preventDefault(); run(scene?.paused ? 'resume' : 'pause'); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [shortcuts, run, scene?.paused]);

  if (telemetry && telemetry.camera_source !== 'scenario') {
    return (
      <div className="text-[11px] text-gray-400 p-3">
        Presenter controls drive the simulated scene. The camera source is <b>{telemetry.camera_source}</b> — switch
        it to <b>scenario</b> in Settings to use them.
      </div>
    );
  }

  const fireClips = clips.filter((c) => c.kind === 'fire' && c.available);
  const normalClips = clips.filter((c) => c.kind === 'normal' && c.available);
  const selectCls = 'w-full px-2 py-1.5 rounded bg-[#252b3b] border border-[#2a3142] text-[11px] text-white';

  if (horizontal) {
    const small = 'flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg text-xs font-semibold transition-colors disabled:opacity-60';
    return (
      <div className="space-y-2.5">
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {SCENARIOS.map((s) => (
            <button key={s.action} title={s.expect} disabled={!!busy} onClick={() => run(s.action, s.extra)} className={`${small} ${s.style}`}>
              <s.icon className="w-3.5 h-3.5" /> {s.label}
              <kbd className="text-[9px] font-mono px-1 rounded bg-black/30">{s.key.toUpperCase()}</kbd>
            </button>
          ))}
          <button disabled={!!busy} onClick={() => run(scene?.paused ? 'resume' : 'pause')}
            className={`${small} bg-[#252b3b] hover:bg-[#2f364a] text-gray-200 border border-[#3a4256]`}>
            {scene?.paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}{scene?.paused ? 'Resume' : 'Pause'}
            <kbd className="text-[9px] font-mono opacity-70">P</kbd>
          </button>
          <button disabled={!!busy} onClick={() => run('reset')}
            className={`${small} bg-[#252b3b] hover:bg-[#2f364a] text-gray-200 border border-[#3a4256]`}>
            <RotateCcw className="w-3.5 h-3.5" /> Reset <kbd className="text-[9px] font-mono opacity-70">R</kbd>
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 items-center">
          <label className="flex items-center gap-2 text-[11px] text-gray-300">
            <Ruler className="w-3.5 h-3.5 text-purple-400 shrink-0" /> Distance
            <input type="range" min="1" max="10" step="0.1" value={distance ?? 4} onChange={(e) => changeDistance(parseFloat(e.target.value))}
              className="flex-1 accent-purple-500 min-w-0" />
            <span className="font-mono text-white w-12 text-right">{distance != null ? Number(distance).toFixed(1) : '—'} m</span>
          </label>
          <select value={scene?.normal_clip ?? ''} onChange={(e) => run('select_clips', { normal_clip: e.target.value })} className={selectCls}>
            {normalClips.map((c) => <option key={c.id} value={c.id}>Normal: {c.label}</option>)}
          </select>
          <select value={scene?.fire_clip ?? ''} onChange={(e) => run('select_clips', { fire_clip: e.target.value })} className={selectCls}>
            {fireClips.map((c) => <option key={c.id} value={c.id}>Fire: {c.label}</option>)}
          </select>
        </div>
        {error && <p className="flex items-center gap-1.5 text-[11px] text-red-400"><AlertCircle className="w-3.5 h-3.5" />{error}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-2">
        {SCENARIOS.map((s) => (
          <button key={s.action} disabled={!!busy} onClick={() => run(s.action, s.extra)}
            className={`group flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors disabled:opacity-60 ${s.style}`}>
            <s.icon className="w-4 h-4 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold">{s.label}</p>
              {!compact && <p className="text-[10px] opacity-75 leading-tight">{s.expect}</p>}
            </div>
            <kbd className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/30">{s.key.toUpperCase()}</kbd>
          </button>
        ))}
        <div className="grid grid-cols-2 gap-2">
          <button disabled={!!busy} onClick={() => run(scene?.paused ? 'resume' : 'pause')}
            className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-[#252b3b] hover:bg-[#2f364a] text-gray-200 text-xs font-medium border border-[#3a4256]">
            {scene?.paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            {scene?.paused ? 'Resume' : 'Pause'} <kbd className="text-[10px] font-mono opacity-70">P</kbd>
          </button>
          <button disabled={!!busy} onClick={() => run('reset')}
            className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-[#252b3b] hover:bg-[#2f364a] text-gray-200 text-xs font-medium border border-[#3a4256]">
            <RotateCcw className="w-3.5 h-3.5" /> Reset <kbd className="text-[10px] font-mono opacity-70">R</kbd>
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-[#2a3142] bg-[#0f1419]/50 p-3 space-y-2">
        <label className="flex items-center gap-2 text-[11px] text-gray-300">
          <Ruler className="w-3.5 h-3.5 text-purple-400" /> Fire distance (true)
          <span className="ml-auto font-mono text-white">{distance != null ? Number(distance).toFixed(1) : '—'} m</span>
        </label>
        <input type="range" min="1" max="10" step="0.1" value={distance ?? 4} onChange={(e) => changeDistance(parseFloat(e.target.value))}
          className="w-full accent-purple-500" />
        <div className="flex justify-between text-[9px] text-gray-600"><span>1 m</span><span className="text-red-400/70">TF-Luna max 8 m</span><span>10 m</span></div>
      </div>

      <div className="rounded-lg border border-[#2a3142] bg-[#0f1419]/50 p-3 space-y-2">
        <p className="flex items-center gap-2 text-[11px] text-gray-300"><Film className="w-3.5 h-3.5 text-blue-400" /> Camera clips</p>
        <select value={scene?.normal_clip ?? ''} onChange={(e) => run('select_clips', { normal_clip: e.target.value })}
          className="w-full px-2 py-1.5 rounded bg-[#252b3b] border border-[#2a3142] text-[11px] text-white">
          {normalClips.map((c) => <option key={c.id} value={c.id}>Normal: {c.label}</option>)}
        </select>
        <select value={scene?.fire_clip ?? ''} onChange={(e) => run('select_clips', { fire_clip: e.target.value })}
          className="w-full px-2 py-1.5 rounded bg-[#252b3b] border border-[#2a3142] text-[11px] text-white">
          {fireClips.map((c) => <option key={c.id} value={c.id}>Fire: {c.label}</option>)}
        </select>
      </div>

      {scene && (
        <div className="grid grid-cols-3 gap-2 text-[10px] text-gray-400">
          <div>Scene <span className="block font-mono text-gray-200">{scene.mode}</span></div>
          <div>Intensity <span className="block font-mono text-gray-200">{(scene.intensity * 100).toFixed(0)}%</span></div>
          <div>Video <span className="block font-mono text-gray-200">{scene.video_fps} fps</span></div>
        </div>
      )}
      {error && <p className="flex items-center gap-1.5 text-[11px] text-red-400"><AlertCircle className="w-3.5 h-3.5" />{error}</p>}
    </div>
  );
}
