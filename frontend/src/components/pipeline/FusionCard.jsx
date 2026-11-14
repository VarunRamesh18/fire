import { Wind, Camera, Check, X } from 'lucide-react';
import { AreaChart, Area, ReferenceLine, ResponsiveContainer, YAxis } from 'recharts';
import StageCard, { Stat } from './StageCard';

function Verdict({ ok, label }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold ${ok ? 'text-green-400' : 'text-gray-500'}`}>
      {ok ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}{label}
    </span>
  );
}

export default function FusionCard({ t, history = [], active }) {
  const smoke = t?.sensors?.smoke ?? {};
  const thr = smoke.threshold_ppm ?? 300;
  const visionValidated = t?.pipeline?.temporal?.passed;
  const data = history.slice(-160).map((h, i) => ({ i, ppm: h.smoke_ppm ?? 0 }));
  const max = Math.max(thr * 1.6, ...data.map((d) => d.ppm));
  const both = visionValidated && smoke.triggered;

  return (
    <StageCard title="Smoke Sensor Corroboration" icon={Wind} tag="SENSOR" step={3} active={active}
      right={smoke.simulated && <span className="text-[9px] text-yellow-400/80 mr-1">MQ-2 (simulated)</span>}>
      <div className="grid grid-cols-3 gap-3 mb-2">
        <Stat label="Smoke" value={smoke.ppm != null ? Math.round(smoke.ppm) : '—'} unit="ppm"
          tone={smoke.triggered ? 'text-orange-400' : 'text-white'} />
        <Stat label="ADC (A0)" value={smoke.adc ?? '—'} unit="/1023" />
        <Stat label="Digital alarm" value={smoke.triggered ? 'HIGH' : 'LOW'} tone={smoke.triggered ? 'text-orange-400' : 'text-gray-400'} />
      </div>
      <div className="h-24 -mx-1">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
            <defs>
              <linearGradient id="smokeGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f97316" stopOpacity={0.45} />
                <stop offset="100%" stopColor="#f97316" stopOpacity={0} />
              </linearGradient>
            </defs>
            <YAxis domain={[0, Math.ceil(max / 100) * 100]} stroke="#4b5563" fontSize={9} tickCount={3} />
            <ReferenceLine y={thr} stroke="#ef4444" strokeDasharray="4 3"
              label={{ value: `alarm ${thr} ppm`, fill: '#f87171', fontSize: 9, position: 'insideTopLeft' }} />
            <Area type="monotone" dataKey="ppm" stroke="#f97316" fill="url(#smokeGrad)" strokeWidth={2}
              isAnimationActive={false} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[10px] text-gray-500 mb-2">Last 40 s · smoke needs a few seconds to travel from the fire to the sensor</p>
      <div className="grid grid-cols-3 gap-2 items-center rounded-lg bg-[#0f1419]/60 border border-[#2a3142] px-3 py-2">
        <div className="flex items-center gap-1.5 text-[11px] text-gray-400"><Camera className="w-3.5 h-3.5" />Camera</div>
        <div className="flex items-center gap-1.5 text-[11px] text-gray-400"><Wind className="w-3.5 h-3.5" />MQ-2</div>
        <div className="text-[11px] text-gray-400">Decision</div>
        <Verdict ok={visionValidated} label={visionValidated ? 'fire' : 'no fire'} />
        <Verdict ok={smoke.triggered} label={smoke.triggered ? 'smoke' : 'clear'} />
        <span className={`text-[11px] font-bold ${both ? 'text-red-400' : visionValidated || smoke.triggered ? 'text-yellow-300' : 'text-gray-500'}`}>
          {both ? 'CONFIRM' : visionValidated || smoke.triggered ? 'WAIT / ALERT' : '—'}
        </span>
      </div>
    </StageCard>
  );
}
