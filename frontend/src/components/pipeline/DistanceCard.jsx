import { Ruler, Crosshair } from 'lucide-react';
import StageCard, { Stat } from './StageCard';
import { fmt } from '../../lib/pipeline';

export default function DistanceCard({ t, active }) {
  const p = t?.pipeline ?? {};
  const lidar = t?.sensors?.lidar ?? {};
  const dist = p.distance;
  const samples = dist?.samples ?? p.lidar_progress?.samples ?? [];
  const lo = samples.length ? Math.min(...samples) - 0.05 : 0;
  const hi = samples.length ? Math.max(...samples) + 0.05 : 1;
  const median = dist?.median_m;
  const y = (v) => 100 - ((v - lo) / (hi - lo || 1)) * 100;

  return (
    <StageCard title="LiDAR Distance Estimation" icon={Ruler} tag="SENSOR" step={4} active={active}
      right={lidar.simulated && <span className="text-[9px] text-yellow-400/80 mr-1">TF-Luna (simulated)</span>}>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <Stat label="Live reading" value={lidar.valid ? fmt(lidar.distance_m, 2) : 'invalid'} unit={lidar.valid ? 'm' : ''}
          tone={lidar.valid ? 'text-white' : 'text-red-400'} />
        <Stat label="Signal strength" value={lidar.strength ?? '—'} />
        <Stat label="Aimed at fire" value={lidar.aimed_at_fire ? 'YES' : 'no'} tone={lidar.aimed_at_fire ? 'text-orange-400' : 'text-gray-400'} />
      </div>

      <div className="relative h-20 rounded-lg bg-[#0f1419]/60 border border-[#2a3142] mb-1 overflow-hidden">
        {samples.length === 0 ? (
          <p className="absolute inset-0 flex items-center justify-center text-[11px] text-gray-600">
            Samples are collected once the fire is confirmed and the LiDAR is aimed
          </p>
        ) : (
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
            {median != null && <line x1="0" x2="100" y1={y(median)} y2={y(median)} stroke="#22c55e" strokeWidth="0.8" strokeDasharray="2 1" vectorEffect="non-scaling-stroke" />}
            {samples.map((v, i) => (
              <circle key={i} cx={(i + 0.5) * (100 / Math.max(samples.length, 1))} cy={y(v)} r="1.6" fill="#a78bfa" />
            ))}
          </svg>
        )}
      </div>
      <p className="text-[10px] text-gray-500 mb-3">
        {dist ? `median of ${dist.n} valid samples` : `${Math.min(p.lidar_progress?.n ?? 0, p.lidar_progress?.required ?? 0)}/${p.lidar_progress?.required ?? '—'} valid samples`} · purple = raw readings · green = median
      </p>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Median (slant)" value={fmt(median, 2)} unit="m" tone="text-green-400" />
        <Stat label="Std deviation" value={dist ? `±${fmt(dist.std_m, 3)}` : '—'} unit="m" />
        <Stat label="Horizontal" value={fmt(dist?.horizontal_m, 2)} unit="m" />
      </div>
      {(p.aiming || p.fire_size) && (
        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
          {p.aiming && (
            <div className="flex items-center gap-2 rounded bg-[#0f1419]/60 border border-[#2a3142] px-2 py-1.5">
              <Crosshair className="w-3.5 h-3.5 text-red-400" />
              <span className="text-gray-400">Pan</span><span className="font-mono text-white">{fmt(p.aiming.pan_deg, 1)}°</span>
              <span className="text-gray-400">Tilt</span><span className="font-mono text-white">{fmt(p.aiming.tilt_deg, 1)}°</span>
            </div>
          )}
          {p.fire_size && (
            <div className="rounded bg-[#0f1419]/60 border border-[#2a3142] px-2 py-1.5 text-gray-400">
              Fire ≈ <span className="font-mono text-white">{fmt(p.fire_size.width_m, 2)}×{fmt(p.fire_size.height_m, 2)} m</span>,
              area <span className="font-mono text-white">{fmt(p.fire_size.area_m2, 2)} m²</span>
            </div>
          )}
        </div>
      )}
    </StageCard>
  );
}
