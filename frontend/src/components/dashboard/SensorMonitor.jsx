import { Camera, Wind, Ruler, Cpu } from 'lucide-react';
import StatusIndicator from '../common/StatusIndicator';

function SensorCard({ icon: Icon, name, connected, primaryValue, primaryUnit, secondaryInfo, statusLabel, accentColor }) {
  return (
    <div className="bg-[#252b3b] rounded-lg border border-[#2a3142] p-4 hover:border-[#3a4256] transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={`p-1.5 rounded-md ${connected ? 'bg-green-500/10' : 'bg-gray-500/10'}`}>
            <Icon className={`w-4 h-4 ${connected ? accentColor : 'text-gray-500'}`} />
          </div>
          <div>
            <p className="text-xs font-semibold text-gray-200">{name}</p>
            <p className={`text-[10px] ${connected ? 'text-green-400' : 'text-red-400'}`}>
              {statusLabel || (connected ? 'Connected' : 'Disconnected')}
            </p>
          </div>
        </div>
        <StatusIndicator status={connected ? 'normal' : 'danger'} size="sm" />
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-lg font-mono font-bold text-white tabular-nums">{primaryValue ?? '—'}</span>
        {primaryUnit && <span className="text-xs text-gray-400">{primaryUnit}</span>}
      </div>
      {secondaryInfo && <p className="text-[10px] text-gray-500 mt-1">{secondaryInfo}</p>}
    </div>
  );
}

export default function SensorMonitor({ telemetry: t }) {
  const smoke = t?.sensors?.smoke ?? {};
  const lidar = t?.sensors?.lidar ?? {};
  const sim = t?.demo_mode;
  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3142] p-4">
      <div className="flex items-center gap-2 mb-4">
        <Cpu className="w-4 h-4 text-blue-400" />
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-300">Sensor Status</span>
        {sim && <span className="ml-auto text-[9px] font-semibold text-yellow-400">SIMULATED SENSORS</span>}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <SensorCard icon={Camera} name="Camera" connected={t?.camera_connected ?? false}
          primaryValue={t?.fps != null ? t.fps.toFixed(0) : null} primaryUnit="fps"
          secondaryInfo={t?.camera_source === 'scenario' ? 'Scenario video clips' : t?.camera_source === 'webcam' ? 'Local webcam' : 'IP camera stream'}
          accentColor="text-blue-400" />
        <SensorCard icon={Wind} name="Smoke (MQ-2)" connected={t?.smoke_sensor_connected ?? false}
          primaryValue={smoke.ppm != null ? Math.round(smoke.ppm) : null} primaryUnit="ppm"
          statusLabel={smoke.triggered ? 'ALARM' : undefined}
          secondaryInfo={`Alarm at ${smoke.threshold_ppm ?? '—'} ppm · ADC ${smoke.adc ?? '—'}`}
          accentColor="text-orange-400" />
        <SensorCard icon={Ruler} name="LiDAR (TF-Luna)" connected={t?.lidar_connected ?? false}
          primaryValue={lidar.valid && lidar.distance_m != null ? lidar.distance_m.toFixed(2) : 'invalid'} primaryUnit={lidar.valid ? 'm' : ''}
          secondaryInfo={`Strength ${lidar.strength ?? '—'} · ${lidar.aimed_at_fire ? 'aimed at fire' : 'scanning'}`}
          accentColor="text-purple-400" />
        <SensorCard icon={Cpu} name="Arduino" connected={sim || (t?.arduino_connected ?? false)}
          primaryValue={sim ? 'Simulated' : t?.arduino_connected ? 'Online' : 'Offline'}
          secondaryInfo={sim ? 'Switch off simulated sensors in Settings for hardware' : 'Serial link'}
          accentColor="text-teal-400" />
      </div>
    </div>
  );
}
