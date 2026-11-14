import { FileText } from 'lucide-react';
import StageCard, { Stat } from './StageCard';
import { OUTCOME_META, STATE_META, TONES, fmt } from '../../lib/pipeline';

export function OutcomeBadge({ outcome }) {
  const m = OUTCOME_META[outcome] ?? { label: outcome, tone: 'muted' };
  const tone = TONES[m.tone];
  return <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${tone.bg} ${tone.border} ${tone.text}`}>{m.label}</span>;
}

export function Timeline({ timeline = [] }) {
  return (
    <ol className="relative border-l border-[#2a3142] ml-1.5 space-y-1.5">
      {timeline.map((e, i) => {
        const tone = TONES[STATE_META[e.state]?.tone ?? 'muted'];
        return (
          <li key={i} className="ml-3">
            <span className={`absolute -left-[4.5px] mt-1.5 w-2 h-2 rounded-full ${tone.dot}`} />
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-[10px] text-gray-500 w-12 tabular-nums">t+{fmt(e.t, 1)}s</span>
              <span className={`text-[11px] font-semibold ${tone.text}`}>{STATE_META[e.state]?.label ?? e.state}</span>
            </div>
            {e.note && <p className="text-[10px] text-gray-500 ml-14 -mt-0.5">{e.note}</p>}
          </li>
        );
      })}
    </ol>
  );
}

export default function IncidentReport({ t, active }) {
  const live = t?.pipeline?.incident;
  const last = t?.pipeline?.last_incident;
  const inc = live ?? last;
  const m = last && !live ? last.metrics : null;

  return (
    <StageCard title={live ? 'Incident in progress' : 'Last incident report'} icon={FileText} step={7} active={active}
      right={!live && last ? <OutcomeBadge outcome={last.outcome} /> : live ? <span className="text-[10px] font-mono text-orange-400 mr-1">#{live.id}</span> : null}>
      {!inc ? (
        <p className="text-[11px] text-gray-500 py-6 text-center">No incident yet — use the presenter controls to start a scenario.</p>
      ) : (
        <>
          {m && (
            <div className="grid grid-cols-3 gap-3 mb-3">
              <Stat small label="Confirmed after" value={fmt(m.t_confirmed_s, 1)} unit="s" />
              <Stat small label="Water on after" value={fmt(m.t_suppression_s, 1)} unit="s" />
              <Stat small label="Fire out after" value={fmt(m.t_extinguished_s, 1)} unit="s" tone="text-green-400" />
              <Stat small label="Distance" value={fmt(m.distance_m, 2)} unit="m" />
              <Stat small label="Pump" value={fmt(m.pump_pressure_bar, 2)} unit="bar" />
              <Stat small label="Water used" value={fmt(m.water_used_l, 2)} unit="L" />
            </div>
          )}
          {last?.reason && !live && <p className="text-[11px] text-gray-400 mb-2">{last.reason}</p>}
          <div className="max-h-80 overflow-y-auto pr-1"><Timeline timeline={inc.timeline} /></div>
        </>
      )}
    </StageCard>
  );
}
