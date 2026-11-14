import { useEffect, useState } from 'react';
import { BarChart3, Flame, Ruler, Gauge, Timer, Ban, Droplets, AlertTriangle, Wind } from 'lucide-react';
import { AreaChart, Area, ReferenceLine, ResponsiveContainer, YAxis, CartesianGrid } from 'recharts';
import { useTelemetryContext } from '../components/layout/Layout';
import DetectionChart from '../components/charts/DetectionChart';
import DistanceChart from '../components/charts/DistanceChart';
import { getEventStats } from '../services/api';
import { fmt } from '../lib/pipeline';

function StatCard({ icon: Icon, label, value, unit, color, hint }) {
  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3142] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon className={`w-4 h-4 ${color}`} />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">{label}</span>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-2xl font-mono font-bold text-white tabular-nums">{value ?? '—'}</span>
        {unit && <span className="text-sm text-gray-400">{unit}</span>}
      </div>
      {hint && <p className="text-[10px] text-gray-500 mt-1">{hint}</p>}
    </div>
  );
}

function ChartCard({ title, icon: Icon, children }) {
  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3142] p-5">
      <div className="flex items-center gap-2 mb-4">
        <Icon className="w-4 h-4 text-gray-400" />
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-300">{title}</span>
      </div>
      {children}
    </div>
  );
}

export default function Analytics() {
  const { telemetryHistory, fireDetectionHistory, distanceHistory, latestTelemetry } = useTelemetryContext();
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const load = () => getEventStats().then(setStats).catch((e) => setError(e.message));
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const thr = latestTelemetry?.sensors?.smoke?.threshold_ppm ?? 300;
  const smokeData = telemetryHistory.map((h, i) => ({ i, ppm: h.smoke_ppm ?? 0 }));

  return (
    <div className="mt-2 space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <BarChart3 className="w-5 h-5 text-blue-400" />
        <h1 className="text-lg font-bold text-white">Analytics</h1>
        <span className="text-xs text-gray-500 ml-2">Incident statistics (all time) · live charts (last 60 s)</span>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Flame} label="Fires extinguished" value={stats?.extinguished} color="text-green-400"
          hint={`${stats?.total_incidents ?? 0} incidents in total`} />
        <StatCard icon={Ban} label="False alarms rejected" value={stats?.false_alarms_rejected} color="text-gray-300"
          hint="Failed temporal validation" />
        <StatCard icon={AlertTriangle} label="Operator alerts" value={stats?.operator_alerts} color="text-yellow-300"
          hint="Camera or smoke alone - no water" />
        <StatCard icon={AlertTriangle} label="Escalated" value={stats?.escalated} color="text-red-400" hint="Out of range / not knocked down" />
        <StatCard icon={Timer} label="Avg time to confirm" value={fmt(stats?.avg_time_to_confirm_s, 1)} unit="s" color="text-orange-400" />
        <StatCard icon={Droplets} label="Avg time to water" value={fmt(stats?.avg_time_to_suppression_s, 1)} unit="s" color="text-sky-300" />
        <StatCard icon={Timer} label="Avg time to fire-out" value={fmt(stats?.avg_time_to_extinguish_s, 1)} unit="s" color="text-green-400" />
        <StatCard icon={Gauge} label="Avg pump pressure" value={fmt(stats?.avg_pump_pressure_bar, 2)} unit="bar" color="text-orange-400"
          hint={`Avg distance ${fmt(stats?.avg_distance_m, 2)} m · ${fmt(stats?.total_water_l, 1)} L water total`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard title="YOLOv8 Fire Confidence" icon={Flame}>
          <DetectionChart data={fireDetectionHistory} />
        </ChartCard>
        <ChartCard title="Smoke Concentration (MQ-2)" icon={Wind}>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={smokeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3142" />
              <YAxis stroke="#64748b" fontSize={10} domain={[0, 'auto']} />
              <ReferenceLine y={thr} stroke="#ef4444" strokeDasharray="4 3" />
              <Area type="monotone" dataKey="ppm" stroke="#f97316" fill="#f9731633" strokeWidth={2} dot={false} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="LiDAR Distance" icon={Ruler}>
          <DistanceChart data={distanceHistory} />
        </ChartCard>
      </div>
    </div>
  );
}
