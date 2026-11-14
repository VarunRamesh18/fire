import { SlidersHorizontal } from 'lucide-react';
import { useTelemetryContext } from '../components/layout/Layout';
import PresenterPanel from '../components/pipeline/PresenterPanel';
import { STATE_META, toneOf } from '../lib/pipeline';

// Full-page remote for a second device (phone / tablet) while the projector shows the pipeline page.
export default function Presenter() {
  const { latestTelemetry: t } = useTelemetryContext();
  const tone = toneOf(t?.system_state);
  return (
    <div className="mt-2 max-w-md mx-auto space-y-4">
      <div className="flex items-center gap-2">
        <SlidersHorizontal className="w-5 h-5 text-orange-400" />
        <h1 className="text-lg font-bold text-white">Presenter remote</h1>
      </div>
      <div className={`rounded-xl border p-4 ${tone.bg} ${tone.border}`}>
        <p className="text-[10px] uppercase tracking-wider text-gray-400">Pipeline stage</p>
        <p className={`text-lg font-bold ${tone.text}`}>{STATE_META[t?.system_state]?.label ?? '—'}</p>
        <p className="text-xs text-gray-300 mt-1">{t?.pipeline?.narration}</p>
      </div>
      <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3142] p-4">
        <PresenterPanel telemetry={t} shortcuts />
      </div>
    </div>
  );
}
