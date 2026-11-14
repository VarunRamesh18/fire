import { Timer, CheckCircle2, XCircle } from 'lucide-react';
import StageCard, { Stat } from './StageCard';
import { fmt } from '../../lib/pipeline';

export default function TemporalCard({ temporal, active }) {
  const w = temporal?.window ?? [];
  const confs = temporal?.confidences ?? [];
  const passed = temporal?.passed;
  const iouOk = temporal?.consistency == null || temporal.consistency >= temporal.min_iou;

  return (
    <StageCard title="Temporal Validation" icon={Timer} tag="AI" step={2} active={active}
      right={passed
        ? <span className="flex items-center gap-1 text-[10px] font-semibold text-green-400"><CheckCircle2 className="w-3.5 h-3.5" />VALIDATED</span>
        : <span className="flex items-center gap-1 text-[10px] font-semibold text-gray-500"><XCircle className="w-3.5 h-3.5" />not yet</span>}>
      <p className="text-[11px] text-gray-400 mb-3">
        A fire must persist in <b className="text-gray-200">{temporal?.required ?? '—'}</b> of the last{' '}
        <b className="text-gray-200">{temporal?.size ?? '—'}</b> frames, at a consistent location. This rejects flashes,
        reflections and one-frame mistakes.
      </p>
      <div className="flex gap-1 mb-1">
        {w.map((v, i) => (
          <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
            <div className={`w-full h-7 rounded-sm transition-colors duration-200 ${
              v === 1 ? 'bg-red-500' : v === 0 ? 'bg-[#2a3142]' : 'bg-[#161b26] border border-dashed border-[#2a3142]'
            }`} title={confs[i] != null ? `${(confs[i] * 100).toFixed(0)}%` : 'empty'} />
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[9px] text-gray-600 mb-3"><span>older</span><span>newest frame →</span></div>
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Positive frames" value={`${temporal?.positives ?? 0}/${temporal?.size ?? 0}`}
          tone={passed ? 'text-green-400' : 'text-white'} />
        <Stat label="Box overlap (IoU)" value={fmt(temporal?.consistency, 2)}
          tone={iouOk ? 'text-white' : 'text-red-400'} unit={`≥ ${fmt(temporal?.min_iou, 2)}`} />
        <Stat label="Mean confidence" value={temporal?.mean_conf ? `${(temporal.mean_conf * 100).toFixed(0)}%` : '—'} />
      </div>
    </StageCard>
  );
}
