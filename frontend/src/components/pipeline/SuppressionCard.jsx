import { Droplets, ShieldCheck } from 'lucide-react';
import StageCard, { Meter, Stat } from './StageCard';
import { fmt } from '../../lib/pipeline';

export default function SuppressionCard({ t, active }) {
  const s = t?.pipeline?.suppression ?? {};
  const scene = t?.scene;
  const target = s.target_pressure_bar ?? 0;
  const verifying = t?.system_state === 'VERIFICATION';

  return (
    <StageCard title="Suppression & Verification" icon={Droplets} tag="ACTUATOR" step={6} active={active}
      right={<span className="text-[9px] text-yellow-400/80 mr-1">simulated actuator</span>}>
      <div className="grid grid-cols-4 gap-3 mb-3">
        <Stat label="Valve" value={fmt(s.valve_open_pct, 0)} unit="%" tone={s.valve_open_pct > 0 ? 'text-sky-300' : 'text-gray-400'} />
        <Stat label="Pump" value={fmt(s.pump_pressure_bar, 2)} unit="bar" tone="text-sky-300" />
        <Stat label="Flow" value={fmt(s.flow_lpm, 1)} unit="L/min" />
        <Stat label="Water used" value={fmt(s.water_used_l, 2)} unit="L" />
      </div>
      <div className="space-y-2.5">
        <div>
          <div className="flex justify-between text-[10px] text-gray-500 mb-1"><span>Pump pressure → target {fmt(target, 2)} bar</span><span>{s.elapsed_s != null ? `${fmt(s.elapsed_s, 1)} s spraying` : ''}</span></div>
          <Meter value={s.pump_pressure_bar ?? 0} max={Math.max(target * 1.25, 0.1)} marker={target || null} colour="bg-sky-400" />
        </div>
        <div>
          <div className="flex justify-between text-[10px] text-gray-500 mb-1"><span>Flow vs required application rate</span><span>{fmt(s.flow_lpm, 1)} / {fmt(s.required_flow_lpm, 1)} L/min</span></div>
          <Meter value={s.flow_lpm ?? 0} max={Math.max((s.required_flow_lpm ?? 1) * 2, s.flow_lpm ?? 0, 0.1)} marker={s.required_flow_lpm} colour="bg-blue-500" />
        </div>
        {scene && (
          <div>
            <div className="flex justify-between text-[10px] text-gray-500 mb-1"><span>Fire intensity (simulated ground truth)</span><span className="font-mono">{fmt((scene.intensity ?? 0) * 100, 0)}%</span></div>
            <Meter value={scene.intensity ?? 0} max={1} colour="bg-orange-500" />
          </div>
        )}
        <div className={`rounded-lg border px-3 py-2 ${verifying ? 'border-green-500/40 bg-green-500/5' : 'border-[#2a3142] bg-[#0f1419]/60'}`}>
          <div className="flex items-center gap-2 text-[11px] mb-1.5">
            <ShieldCheck className={`w-3.5 h-3.5 ${verifying ? 'text-green-400' : 'text-gray-500'}`} />
            <span className="text-gray-300">YOLO verification: consecutive frames with no fire</span>
            <span className="ml-auto font-mono text-white">{s.clear_frames ?? 0}/{s.clear_frames_required ?? '—'}</span>
          </div>
          <Meter value={Math.min(s.clear_frames ?? 0, s.clear_frames_required ?? 1)} max={s.clear_frames_required ?? 1} colour="bg-green-500" height="h-1.5" />
          {s.reflashes > 0 && <p className="text-[10px] text-orange-400 mt-1">Re-flash detected {s.reflashes}× — suppression resumed</p>}
        </div>
      </div>
    </StageCard>
  );
}
