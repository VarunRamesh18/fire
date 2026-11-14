import { useState, useEffect, useCallback } from 'react';
import { History, Download, ChevronLeft, ChevronRight, ChevronDown, Calendar, RefreshCw } from 'lucide-react';
import { getIncidents, exportEventsCSV } from '../services/api';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { OutcomeBadge, Timeline } from '../components/pipeline/IncidentReport';
import { fmt } from '../lib/pipeline';

const PAGE_SIZE = 15;
const formatDate = (ts) => (ts ? new Date(ts).toLocaleString() : '—');
// date inputs give local calendar days; convert to UTC instants for the API
const dayStart = (d) => (d ? new Date(`${d}T00:00:00`).toISOString() : undefined);
const dayEnd = (d) => (d ? new Date(new Date(`${d}T00:00:00`).getTime() + 86400000).toISOString() : undefined);

export default function EventHistory() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [open, setOpen] = useState(null);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getIncidents({ limit: PAGE_SIZE, offset: page * PAGE_SIZE, start_date: dayStart(startDate), end_date: dayEnd(endDate) });
      setRows(data.incidents);
      setTotal(data.total);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [page, startDate, endDate]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const url = URL.createObjectURL(await exportEventsCSV());
      const a = document.createElement('a');
      a.href = url;
      a.download = `fireguard-incidents-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(`Export failed: ${e.message}`);
    } finally {
      setExporting(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const headers = ['', 'Started', 'Outcome', 'Peak conf.', 'Confirmed', 'Water on', 'Fire out', 'Distance', 'Pump', 'Water', 'Duration'];

  return (
    <div className="mt-2 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <History className="w-5 h-5 text-blue-400" />
          <h1 className="text-lg font-bold text-white">Incident History</h1>
          <span className="text-xs text-gray-500 ml-1">{total} incidents</span>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchRows} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#252b3b] border border-[#2a3142] text-gray-300 text-xs hover:text-white">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
          <button onClick={handleExport} disabled={exporting}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-medium hover:bg-blue-500/20 disabled:opacity-50">
            <Download className="w-3.5 h-3.5" /> {exporting ? 'Exporting...' : 'Export CSV'}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 p-3 bg-[#1a1f2e] rounded-xl border border-[#2a3142]">
        <Calendar className="w-4 h-4 text-gray-400" />
        <span className="text-xs text-gray-400">Filter:</span>
        {[['From', startDate, setStartDate], ['To', endDate, setEndDate]].map(([label, val, set]) => (
          <div key={label} className="flex items-center gap-2">
            <label className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</label>
            <input type="date" value={val} onChange={(e) => { set(e.target.value); setPage(0); }}
              className="px-2 py-1 rounded bg-[#252b3b] border border-[#2a3142] text-xs text-white focus:border-blue-500 focus:outline-none" />
          </div>
        ))}
        {(startDate || endDate) && (
          <button onClick={() => { setStartDate(''); setEndDate(''); setPage(0); }} className="text-xs text-gray-400 hover:text-white">Clear</button>
        )}
      </div>

      <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3142] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[#2a3142] bg-[#252b3b]">
                {headers.map((h) => (
                  <th key={h} className="px-3 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-gray-400 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a3142]/50">
              {loading ? (
                <tr><td colSpan={headers.length}><LoadingSpinner message="Loading incidents..." /></td></tr>
              ) : error ? (
                <tr><td colSpan={headers.length} className="p-6 text-center text-red-400">{error}</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={headers.length} className="p-10 text-center">
                  <History className="w-10 h-10 text-gray-700 mx-auto mb-2" />
                  <p className="text-gray-500">No incidents recorded yet</p>
                  <p className="text-xs text-gray-600 mt-1">An incident is recorded each time the pipeline leaves Monitoring</p>
                </td></tr>
              ) : rows.map((r) => {
                const m = r.metrics ?? {};
                const isOpen = open === r.id;
                return [
                  <tr key={r.id} onClick={() => setOpen(isOpen ? null : r.id)} className="hover:bg-[#252b3b]/50 cursor-pointer">
                    <td className="px-3 py-2"><ChevronDown className={`w-3.5 h-3.5 text-gray-500 transition-transform ${isOpen ? '' : '-rotate-90'}`} /></td>
                    <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{formatDate(r.started_at)}</td>
                    <td className="px-3 py-2"><OutcomeBadge outcome={r.outcome} /></td>
                    <td className="px-3 py-2 font-mono text-gray-300">{m.peak_confidence ? `${(m.peak_confidence * 100).toFixed(0)}%` : '—'}</td>
                    <td className="px-3 py-2 font-mono text-gray-300">{m.t_confirmed_s != null ? `${fmt(m.t_confirmed_s, 1)} s` : '—'}</td>
                    <td className="px-3 py-2 font-mono text-gray-300">{m.t_suppression_s != null ? `${fmt(m.t_suppression_s, 1)} s` : '—'}</td>
                    <td className="px-3 py-2 font-mono text-green-400">{m.t_extinguished_s != null ? `${fmt(m.t_extinguished_s, 1)} s` : '—'}</td>
                    <td className="px-3 py-2 font-mono text-gray-300">{m.distance_m != null ? `${fmt(m.distance_m, 2)} m` : '—'}</td>
                    <td className="px-3 py-2 font-mono text-gray-300">{m.pump_pressure_bar != null ? `${fmt(m.pump_pressure_bar, 2)} bar` : '—'}</td>
                    <td className="px-3 py-2 font-mono text-gray-300">{m.water_used_l ? `${fmt(m.water_used_l, 2)} L` : '—'}</td>
                    <td className="px-3 py-2 font-mono text-gray-400">{fmt(r.duration_s, 1)} s</td>
                  </tr>,
                  isOpen && (
                    <tr key={`${r.id}-detail`} className="bg-[#151a26]">
                      <td />
                      <td colSpan={headers.length - 1} className="px-3 py-3">
                        {r.reason && <p className="text-[11px] text-gray-400 mb-2">{r.reason}</p>}
                        <Timeline timeline={r.timeline} />
                      </td>
                    </tr>
                  ),
                ];
              })}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-[#2a3142]">
            <span className="text-xs text-gray-500">Page {page + 1} of {totalPages}</span>
            <div className="flex items-center gap-2">
              <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
                className="p-1.5 rounded bg-[#252b3b] border border-[#2a3142] text-gray-400 hover:text-white disabled:opacity-40"><ChevronLeft className="w-4 h-4" /></button>
              <button onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                className="p-1.5 rounded bg-[#252b3b] border border-[#2a3142] text-gray-400 hover:text-white disabled:opacity-40"><ChevronRight className="w-4 h-4" /></button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
