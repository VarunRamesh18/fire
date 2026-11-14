import { Brain, CheckCircle, Circle, XCircle } from 'lucide-react';
import { STAGES, STATE_META, toneOf } from '../../lib/pipeline';
import { Tag } from '../pipeline/StageCard';

export default function DecisionPanel({ telemetry }) {
  const p = telemetry?.pipeline;
  const byKey = Object.fromEntries((p?.stages ?? []).map((s) => [s.key, s]));
  const alert = p?.is_alert;
  const tone = toneOf(p?.state);

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3142] p-5 h-full">
      <div className="flex items-center gap-2 mb-4">
        <Brain className="w-4 h-4 text-purple-400" />
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-300">System Decision</span>
        {p && <span className={`ml-auto text-[10px] font-semibold ${tone.text}`}>{STATE_META[p.state]?.label}</span>}
      </div>
      {alert && (
        <div className={`mb-3 px-3 py-2 rounded-lg border text-xs ${tone.bg} ${tone.border} ${tone.text}`}>{p.narration}</div>
      )}
      <div className="space-y-1.5">
        {STAGES.map((stage) => {
          const status = byKey[stage.key]?.status ?? 'pending';
          return (
            <div key={stage.key} className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-300 ${
              status === 'active' ? 'bg-orange-500/10 border border-orange-500/20'
                : status === 'done' ? 'bg-green-500/5' : status === 'failed' ? 'bg-red-500/5' : 'opacity-40'
            }`}>
              {status === 'done' ? <CheckCircle className="w-4 h-4 text-green-500 shrink-0" />
                : status === 'failed' ? <XCircle className="w-4 h-4 text-red-500 shrink-0" />
                  : status === 'active' ? <Circle className="w-4 h-4 text-orange-500 fill-orange-500 shrink-0 animate-pulse" />
                    : <Circle className="w-4 h-4 text-gray-600 shrink-0" />}
              <span className={`text-xs font-medium flex-1 ${status === 'pending' ? 'text-gray-600' : 'text-gray-200'}`}>{stage.label}</span>
              {byKey[stage.key]?.t != null && <span className="text-[10px] font-mono text-gray-500">t+{byKey[stage.key].t.toFixed(1)}s</span>}
              <Tag kind={stage.tag}>{stage.tag}</Tag>
            </div>
          );
        })}
      </div>
    </div>
  );
}
