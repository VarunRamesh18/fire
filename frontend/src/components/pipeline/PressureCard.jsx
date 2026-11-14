import { Gauge, AlertTriangle } from 'lucide-react';
import StageCard from './StageCard';
import { fmt } from '../../lib/pipeline';

function Step({ n, title, formula, result, children }) {
  return (
    <div className="flex gap-2.5 py-1.5 border-b border-[#2a3142]/60 last:border-0">
      <span className="w-4 h-4 mt-0.5 rounded-full bg-teal-500/15 text-teal-300 text-[9px] font-bold flex items-center justify-center shrink-0">{n}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-[11px] font-semibold text-gray-200">{title}</p>
          <p className="text-[11px] font-mono font-bold text-teal-300 whitespace-nowrap">{result}</p>
        </div>
        <p className="text-[10px] font-mono text-gray-400 break-words">{formula}</p>
        {children}
      </div>
    </div>
  );
}

function Trajectory({ h }) {
  const pts = h.trajectory ?? [];
  if (!pts.length) return null;
  const maxX = Math.max(...pts.map((p) => p.x), 0.5);
  const maxY = Math.max(...pts.map((p) => p.y), h.apex_height_m ?? 0, 1) * 1.15;
  const W = 300, H = 130, pad = 18;
  const sx = (x) => pad + (x / maxX) * (W - 2 * pad);
  const sy = (y) => H - pad - (y / maxY) * (H - 2 * pad);
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(' ');
  const last = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
      <line x1={pad} x2={W - pad / 2} y1={sy(0)} y2={sy(0)} stroke="#374151" />
      <line x1={sx(0)} x2={sx(0)} y1={sy(0)} y2={sy(pts[0].y)} stroke="#64748b" strokeWidth="3" />
      <circle cx={sx(0)} cy={sy(pts[0].y)} r="4" fill="#38bdf8" />
      <path d={d} fill="none" stroke="#38bdf8" strokeWidth="2" strokeDasharray="5 3" />
      <text x={sx(last.x)} y={sy(0) + 1} fontSize="16" textAnchor="middle">🔥</text>
      <text x={sx(0) + 4} y={sy(pts[0].y) - 6} fontSize="9" fill="#94a3b8">nozzle {fmt(pts[0].y, 1)} m</text>
      <text x={(sx(0) + sx(last.x)) / 2} y={H - 3} fontSize="9" fill="#94a3b8" textAnchor="middle">
        {fmt(last.x, 2)} m horizontal · {fmt(h.angle_deg, 0)}° · flight {fmt(h.time_of_flight_s, 2)} s
      </text>
    </svg>
  );
}

export default function PressureCard({ t, active }) {
  const h = t?.pipeline?.hydraulics;
  const dist = t?.pipeline?.distance;

  return (
    <StageCard title="Pressure Estimation" icon={Gauge} tag="PHYSICS" step={5} active={active}>
      {!h ? (
        <p className="text-[11px] text-gray-500 py-6 text-center">
          Calculated from the LiDAR distance once it is acquired: projectile motion → Bernoulli → Darcy–Weisbach losses → pump pressure.
        </p>
      ) : !h.reachable ? (
        <div className="flex items-center gap-2 text-sm text-red-400 py-4"><AlertTriangle className="w-4 h-4" />{h.reason}</div>
      ) : (
        <>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-x-4">
            <div>
              <Step n={1} title="Geometry" result={`d = ${fmt(h.horizontal_distance_m, 2)} m`}
                formula={`√(L² − Δh²) = √(${fmt(h.slant_distance_m, 2)}² − ${fmt(h.height_drop_m, 2)}²)`} />
              <Step n={2} title="Projectile (jet speed)" result={`v = ${fmt(h.jet_velocity_ms, 2)} m/s`}
                formula={`v₀ = √(g·d² / 2cos²θ(Δh + d·tanθ)) = ${fmt(h.jet_velocity_ideal_ms, 2)} · (1 + drag margin)`} />
              <Step n={3} title="Nozzle (Bernoulli)" result={`${fmt(h.nozzle_pressure_bar, 3)} bar`}
                formula={`Pₙ = ½ρ(v/Cv)²  ·  Q = Cd·A·v = ${fmt(h.flow_lpm, 1)} L/min`} />
              <Step n={4} title="Losses" result={`${fmt(h.friction_loss_bar + h.minor_loss_bar + h.elevation_loss_bar, 3)} bar`}
                formula={`pipe f=${fmt(h.friction_factor, 4)} (Re ${h.reynolds}) ${fmt(h.friction_loss_bar, 3)} + fittings ${fmt(h.minor_loss_bar, 3)} + lift ρgΔz ${fmt(h.elevation_loss_bar, 3)}`} />
              <Step n={5} title="Pump pressure" result={`${fmt(h.pump_pressure_bar, 2)} bar`}
                formula={`= ${fmt(h.pump_pressure_psi, 1)} psi → command ${fmt(h.command_pressure_bar, 2)} bar ${h.command_pressure_bar > h.pump_pressure_bar ? '(pump minimum)' : ''}`} />
            </div>
            <div className="pt-1">
              <Trajectory h={h} />
              <div className="grid grid-cols-2 gap-2 mt-2 text-[10px]">
                <div className="rounded bg-[#0f1419]/60 border border-[#2a3142] px-2 py-1.5">
                  <p className="text-gray-500 uppercase tracking-wider text-[9px]">Flow vs required</p>
                  <p className="font-mono text-white">{fmt(h.flow_lpm, 1)} / {fmt(h.required_flow_lpm, 1)} L/min</p>
                </div>
                <div className="rounded bg-[#0f1419]/60 border border-[#2a3142] px-2 py-1.5">
                  <p className="text-gray-500 uppercase tracking-wider text-[9px]">Est. knock-down</p>
                  <p className="font-mono text-white">{fmt(h.est_knockdown_s, 1)} s · best angle {h.optimal_angle_deg ?? '—'}°</p>
                </div>
              </div>
            </div>
          </div>
          {!h.within_pump_capacity && (
            <p className="mt-2 text-[11px] text-red-400 flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5" />{h.reason}</p>
          )}
          {dist && <p className="text-[10px] text-gray-500 mt-2">Input: LiDAR median {fmt(dist.median_m, 2)} m (±{fmt(dist.std_m, 3)}) · ρ = 998 kg/m³ · g = 9.81 m/s²</p>}
        </>
      )}
    </StageCard>
  );
}
