import { Check, X } from 'lucide-react';
import { STAGES, toneOf } from '../../lib/pipeline';

export default function PipelineStepper({ pipeline }) {
  const byKey = Object.fromEntries((pipeline?.stages ?? []).map((s) => [s.key, s]));
  const tone = toneOf(pipeline?.state);

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3142] px-3 py-3 overflow-x-auto">
      <div className="flex items-start min-w-[760px]">
        {STAGES.map((stage, i) => {
          const s = byKey[stage.key] ?? { status: 'pending' };
          const Icon = stage.icon;
          const last = i === STAGES.length - 1;
          const circle = {
            done: 'bg-green-500/15 border-green-500 text-green-400',
            active: `${tone.bg} ${tone.solid} ${tone.text}`,
            failed: 'bg-red-500/15 border-red-500 text-red-400',
            pending: 'bg-[#252b3b] border-[#2a3142] text-gray-600',
          }[s.status];
          const label = {
            done: 'text-green-400', active: tone.text, failed: 'text-red-400', pending: 'text-gray-600',
          }[s.status];
          return (
            <div key={stage.key} className="flex items-start flex-1 last:flex-none">
              <div className="flex flex-col items-center w-[74px]">
                <div className={`relative w-10 h-10 rounded-full border-2 flex items-center justify-center transition-all duration-500 ${circle}`}>
                  {s.status === 'done' ? <Check className="w-4 h-4" /> : s.status === 'failed' ? <X className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
                  {s.status === 'active' && (
                    <span className={`absolute inset-0 rounded-full border-2 animate-ping opacity-30 ${tone.border}`} />
                  )}
                </div>
                <p className={`text-[10px] font-semibold mt-1.5 text-center leading-tight ${label}`}>{stage.label}</p>
                <p className="text-[9px] font-mono text-gray-500 h-3 tabular-nums">
                  {s.t != null ? `t+${s.t.toFixed(1)}s` : ''}
                </p>
              </div>
              {!last && (
                <div className={`flex-1 h-0.5 mt-5 mx-0.5 rounded transition-all duration-500 ${
                  s.status === 'done' ? 'bg-green-500' : s.status === 'active' ? `${tone.dot} opacity-60` : 'bg-[#2a3142]'
                }`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
