import { Clock } from 'lucide-react';
import { STATE_META, toneOf } from '../../lib/pipeline';

export default function NarrationPanel({ pipeline }) {
  if (!pipeline) {
    return <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3142] p-5 h-36 animate-pulse" />;
  }
  const meta = STATE_META[pipeline.state] ?? { label: pipeline.state };
  const tone = toneOf(pipeline.state);
  const Icon = meta.icon;
  const inc = pipeline.incident;

  return (
    <div className={`rounded-xl border p-5 transition-colors duration-500 ${tone.bg} ${tone.border}`}>
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg bg-[#0f1419]/60 ${tone.text}`}>{Icon && <Icon className="w-6 h-6" />}</div>
        <div className="flex-1 min-w-0">
          <p className="text-[10px] uppercase tracking-[0.18em] text-gray-400">Current stage</p>
          <h2 className={`text-xl font-bold leading-tight ${tone.text}`}>{pipeline.title}</h2>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider">in stage</p>
          <p className="font-mono text-sm text-gray-200 tabular-nums">{pipeline.state_elapsed_s.toFixed(1)} s</p>
        </div>
      </div>
      <p className="text-sm text-gray-200 leading-relaxed mt-3 min-h-[3.5rem]">{pipeline.narration}</p>
      {inc && (
        <div className="flex items-center gap-1.5 mt-3 text-[11px] text-gray-400">
          <Clock className="w-3.5 h-3.5" />
          Incident <span className="font-mono text-gray-300">#{inc.id}</span> · t+{inc.elapsed_s.toFixed(1)} s since first detection
        </div>
      )}
    </div>
  );
}
