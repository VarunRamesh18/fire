const TAG_STYLES = {
  AI: 'bg-purple-500/10 text-purple-300 border-purple-500/30',
  SENSOR: 'bg-blue-500/10 text-blue-300 border-blue-500/30',
  PHYSICS: 'bg-teal-500/10 text-teal-300 border-teal-500/30',
  ACTUATOR: 'bg-sky-500/10 text-sky-300 border-sky-500/30',
  SYSTEM: 'bg-gray-500/10 text-gray-300 border-gray-500/30',
  SIMULATED: 'bg-yellow-500/10 text-yellow-300 border-yellow-500/30',
};

export function Tag({ children, kind = 'SYSTEM' }) {
  return (
    <span className={`text-[9px] font-semibold tracking-wider px-1.5 py-0.5 rounded border ${TAG_STYLES[kind] ?? TAG_STYLES.SYSTEM}`}>
      {children}
    </span>
  );
}

export function Stat({ label, value, unit, tone = 'text-white', small = false }) {
  return (
    <div className="min-w-0">
      <p className="text-[9px] uppercase tracking-wider text-gray-500 truncate">{label}</p>
      <p className={`font-mono font-bold tabular-nums ${small ? 'text-sm' : 'text-lg'} ${tone} truncate`}>
        {value ?? '—'}{unit && <span className="text-[10px] text-gray-400 font-sans font-medium ml-1">{unit}</span>}
      </p>
    </div>
  );
}

export function Meter({ value, max = 1, colour = 'bg-orange-500', marker, markerLabel, height = 'h-2' }) {
  const pct = Math.max(0, Math.min(100, (value / (max || 1)) * 100));
  const mpct = marker != null ? Math.max(0, Math.min(100, (marker / (max || 1)) * 100)) : null;
  return (
    <div className={`relative w-full ${height} bg-[#0f1419] rounded-full`}>
      <div className={`${height} ${colour} rounded-full transition-all duration-300`} style={{ width: `${pct}%` }} />
      {mpct != null && (
        <div className="absolute -top-1 -bottom-1 w-0.5 bg-white/70" style={{ left: `${mpct}%` }} title={markerLabel} />
      )}
    </div>
  );
}

export default function StageCard({ title, icon: Icon, tag, active, step, children, className = '', right }) {
  return (
    <div className={`bg-[#1a1f2e] rounded-xl border p-4 transition-all duration-300 ${
      active ? 'border-orange-500/60 shadow-[0_0_0_1px_rgba(249,115,22,0.25),0_0_24px_rgba(249,115,22,0.12)]' : 'border-[#2a3142]'
    } ${className}`}>
      <div className="flex items-center gap-2 mb-3">
        {step != null && (
          <span className={`w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center ${
            active ? 'bg-orange-500 text-white' : 'bg-[#252b3b] text-gray-400'
          }`}>{step}</span>
        )}
        {Icon && <Icon className={`w-4 h-4 ${active ? 'text-orange-400' : 'text-gray-400'}`} />}
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-200 flex-1 truncate">{title}</span>
        {right}
        {tag && <Tag kind={tag}>{tag}</Tag>}
      </div>
      {children}
    </div>
  );
}
