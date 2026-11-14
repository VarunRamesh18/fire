import { useState } from 'react';
import { Workflow, SlidersHorizontal, X, Keyboard, AlertTriangle } from 'lucide-react';
import { useTelemetryContext } from '../components/layout/Layout';
import CameraFeed from '../components/dashboard/CameraFeed';
import PipelineStepper from '../components/pipeline/PipelineStepper';
import NarrationPanel from '../components/pipeline/NarrationPanel';
import DetectionCard from '../components/pipeline/DetectionCard';
import TemporalCard from '../components/pipeline/TemporalCard';
import FusionCard from '../components/pipeline/FusionCard';
import DistanceCard from '../components/pipeline/DistanceCard';
import PressureCard from '../components/pipeline/PressureCard';
import SuppressionCard from '../components/pipeline/SuppressionCard';
import IncidentReport from '../components/pipeline/IncidentReport';
import PresenterPanel from '../components/pipeline/PresenterPanel';

// Which detail card is "in focus" for each pipeline state
const FOCUS = {
  MONITORING: 'detection',
  FIRE_DETECTED: 'detection',
  TEMPORAL_VALIDATION: 'temporal',
  SENSOR_FUSION: 'fusion',
  VISION_ONLY_ALERT: 'fusion',
  SMOKE_ONLY_ALERT: 'fusion',
  FIRE_CONFIRMED: 'distance',
  DISTANCE_ESTIMATION: 'distance',
  PRESSURE_ESTIMATION: 'pressure',
  ESCALATED: 'report',
  SUPPRESSION_ACTIVE: 'suppression',
  VERIFICATION: 'suppression',
  SUPPRESSION_COMPLETE: 'report',
  FALSE_ALARM_REJECTED: 'report',
};

export default function Pipeline() {
  const { latestTelemetry: t, telemetryHistory } = useTelemetryContext();
  const [presenterOpen, setPresenterOpen] = useState(true);
  const state = t?.system_state ?? 'MONITORING';
  const focus = FOCUS[state] ?? 'detection';

  const cards = {
    detection: (a) => <DetectionCard t={t} active={a} />,
    temporal: (a) => <TemporalCard temporal={t?.pipeline?.temporal} active={a} />,
    fusion: (a) => <FusionCard t={t} history={telemetryHistory} active={a} />,
    distance: (a) => <DistanceCard t={t} active={a} />,
    pressure: (a) => <PressureCard t={t} active={a} />,
    suppression: (a) => <SuppressionCard t={t} active={a} />,
    report: (a) => <IncidentReport t={t} active={a} />,
  };

  return (
    <div className="mt-2 space-y-4">
      <div className="flex items-center gap-2">
        <Workflow className="w-5 h-5 text-orange-400" />
        <h1 className="text-lg font-bold text-white">Detection → Suppression Pipeline</h1>
        <span className="text-xs text-gray-500 hidden md:inline">YOLOv8 · temporal validation · sensor fusion · LiDAR · hydraulics</span>
        <button onClick={() => setPresenterOpen((o) => !o)}
          className={`ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
            presenterOpen ? 'bg-orange-500/10 border-orange-500/30 text-orange-300' : 'bg-[#252b3b] border-[#2a3142] text-gray-300 hover:text-white'
          }`}>
          <SlidersHorizontal className="w-3.5 h-3.5" /> Presenter controls
        </button>
      </div>

      <PipelineStepper pipeline={t?.pipeline} />

      {t && t.detection_fps > 0 && t.detection_fps < 3 && (
        <div className="flex items-center gap-2 px-4 py-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 text-xs text-yellow-300">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          AI is running slowly ({t.detection_fps} frames/s, {Math.round(t.inference_ms)} ms per frame). Stages will take longer.
          Close other applications, plug in the charger, or set the inference size to 480 px in Settings.
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <div className="xl:col-span-7 space-y-3">
          <CameraFeed telemetry={t} />
          {presenterOpen && (
            <div className="bg-[#151a26] rounded-xl border border-[#3a4256] p-3">
              <div className="flex items-center gap-2 mb-2.5">
                <SlidersHorizontal className="w-3.5 h-3.5 text-orange-400" />
                <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-300">Presenter controls</span>
                <span className="text-[10px] text-gray-500 flex items-center gap-1 ml-2"><Keyboard className="w-3 h-3" /> shortcuts work anywhere on this page</span>
                <button onClick={() => setPresenterOpen(false)} className="ml-auto text-gray-500 hover:text-white" title="Hide"><X className="w-4 h-4" /></button>
              </div>
              <PresenterPanel telemetry={t} shortcuts horizontal />
            </div>
          )}
        </div>
        <div className="xl:col-span-5 space-y-4">
          <NarrationPanel pipeline={t?.pipeline} />
          {cards[focus](true)}
        </div>
      </div>

      <div>
        <p className="text-[10px] uppercase tracking-[0.18em] text-gray-500 mb-2">All stages</p>
        <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4">
          {cards.detection(focus === 'detection')}
          {cards.temporal(focus === 'temporal')}
          {cards.fusion(focus === 'fusion')}
          {cards.distance(focus === 'distance')}
          {cards.suppression(focus === 'suppression')}
          {cards.report(focus === 'report')}
          <div className="md:col-span-2 2xl:col-span-3">{cards.pressure(focus === 'pressure')}</div>
        </div>
      </div>

    </div>
  );
}
