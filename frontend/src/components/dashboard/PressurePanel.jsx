import { Gauge, Info } from 'lucide-react';
import { LineChart, Line, CartesianGrid, Tooltip, ResponsiveContainer, YAxis, XAxis } from 'recharts';
import { fmt } from '../../lib/pipeline';

export default function PressurePanel({ telemetry: t, pressureHistory = [] }) {
  const h = t?.pipeline?.hydraulics;
  const sup = t?.pipeline?.suppression ?? {};
  const data = pressureHistory.slice(-160).map((p, i) => ({ i, pump: p.pump_bar }));

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3142] p-6">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <Gauge className="w-5 h-5 text-orange-400" />
          <span className="text-sm font-semibold uppercase tracking-wider text-gray-200">Pressure & Suppression</span>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-teal-500/10 border border-teal-500/20">
          <Info className="w-3 h-3 text-teal-300" />
          <span className="text-[10px] font-medium text-teal-300">Physics model: projectile + Bernoulli + Darcy–Weisbach</span>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2 grid grid-cols-2 gap-3 content-start">
          {[
            ['Fire distance', fmt(t?.distance_m, 2), 'm'],
            ['Required pump', fmt(h?.pump_pressure_bar, 2), 'bar'],
            ['Jet velocity', fmt(h?.jet_velocity_ms, 2), 'm/s'],
            ['Design flow', fmt(h?.flow_lpm, 1), 'L/min'],
            ['Pump (live)', fmt(sup.pump_pressure_bar, 2), 'bar'],
            ['Water used', fmt(sup.water_used_l, 2), 'L'],
          ].map(([label, value, unit]) => (
            <div key={label} className="p-3 rounded-lg bg-[#252b3b]">
              <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">{label}</p>
              <p className="text-xl font-mono font-bold text-orange-400 tabular-nums">{value}<span className="text-xs text-gray-400 ml-1">{unit}</span></p>
            </div>
          ))}
        </div>
        <div className="lg:col-span-3">
          <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Live pump pressure (bar)</p>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3142" />
              <XAxis dataKey="i" hide />
              <YAxis stroke="#64748b" fontSize={10} domain={[0, 'auto']} />
              <Tooltip contentStyle={{ background: '#1a1f2e', border: '1px solid #2a3142', fontSize: 11 }} formatter={(v) => [`${Number(v).toFixed(2)} bar`, 'pump']} labelFormatter={() => ''} />
              <Line type="monotone" dataKey="pump" stroke="#38bdf8" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
