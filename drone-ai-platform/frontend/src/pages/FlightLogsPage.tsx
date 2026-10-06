import { useEffect, useState } from 'react';
import { Download, FileClock, RefreshCw } from 'lucide-react';
import { format } from 'date-fns';
import type { Flight, TelemetryRecord } from '../types';
import { EmptyState, MetricCard, PageHeading, Panel, StatusBadge } from '../components/common';
import { api } from '../services/api';
import { downloadAuthenticatedFile } from '../services/download';

export function FlightLogsPage() {
  const [flights, setFlights] = useState<Flight[]>([]);
  const [records, setRecords] = useState<TelemetryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exportError, setExportError] = useState('');
  const [selectedFlights, setSelectedFlights] = useState<string[]>([]);
  const [selectedTelemetry, setSelectedTelemetry] = useState<number[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      const [flightData, telemetryData] = await Promise.all([api.flights(), api.telemetryHistory(250)]);
      setFlights(flightData);
      setRecords(telemetryData);
      setError('');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not load stored flight data');
    } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const download = async (path: string, filename: string) => {
    setExportError('');
    try { await downloadAuthenticatedFile(path, filename); }
    catch (failure) { setExportError(failure instanceof Error ? failure.message : 'Export failed'); }
  };
  const toggleFlight = (id: string) => setSelectedFlights((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  const toggleTelemetry = (id: number) => setSelectedTelemetry((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  const totalFlights = flights.length;
  const completeFlights = flights.filter((flight) => flight.status === 'completed').length;
  const totalFlightTime = flights.reduce((sum, flight) => sum + flight.duration_seconds, 0);
  const visibleSamples = records.slice(-12).reverse();

  return <>
    <PageHeading eyebrow="Historical data" title="Flight logs" description="Stored flights, telemetry summaries and selectable CSV export." action={<><button className="button-secondary" onClick={() => void load()}><RefreshCw size={14} />Refresh</button><button className="button-primary" disabled={!selectedFlights.length} onClick={() => void download(`/flights/export.csv?ids=${selectedFlights.join(',')}`, 'selected-flight-logs.csv')}><Download size={14} />Export flights ({selectedFlights.length})</button></>} />
    {error && <div role="alert" className="mb-4 rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs text-rose-200">{error}</div>}
    {exportError && <div role="alert" className="mb-4 rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs text-rose-200">{exportError}</div>}
    <div className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-4"><MetricCard label="Recorded flights" value={totalFlights} icon={<FileClock size={17} />} /><MetricCard label="Completed flights" value={completeFlights} icon={<FileClock size={17} />} tone="blue" /><MetricCard label="Total airtime" value={`${Math.floor(totalFlightTime / 60)}m`} icon={<FileClock size={17} />} tone="amber" /><MetricCard label="Stored telemetry" value={records.length} unit="samples" icon={<FileClock size={17} />} tone="mint" /></div>

    <Panel title="Flight history" subtitle="Flights are recorded from in-air telemetry transitions; simulated records are labeled." action={<StatusBadge tone="info">Select rows to export</StatusBadge>}>
      {loading ? <div className="py-12 text-center text-xs text-slate-500">Loading flight history…</div> : flights.length === 0 ? <EmptyState icon={<FileClock size={22} />} title="No flights recorded yet" message="Flight summaries appear here after flight telemetry has been received and persisted." /> : <div className="overflow-x-auto"><table className="w-full min-w-[950px] border-collapse"><thead><tr><th className="table-header w-9"><span className="sr-only">Select</span></th>{['Flight', 'Started', 'Duration', 'Max altitude', 'Distance', 'Samples', 'Peak risk', 'Status'].map((label) => <th key={label} className="table-header">{label}</th>)}</tr></thead><tbody>{flights.map((flight) => <tr key={flight.id} className="hover:bg-slate-900/40"><td className="table-cell"><input type="checkbox" aria-label={`Select ${flight.name}`} checked={selectedFlights.includes(flight.id)} onChange={() => toggleFlight(flight.id)} className="accent-emerald-400" /></td><td className="table-cell"><span className="font-semibold text-slate-200">{flight.name}</span><span className="mt-1 block font-mono text-[9px] text-slate-600">{flight.id.slice(0, 8)}</span></td><td className="table-cell">{format(new Date(flight.started_at), 'MMM d, HH:mm:ss')}</td><td className="table-cell">{Math.floor(flight.duration_seconds / 60)}m {Math.floor(flight.duration_seconds % 60)}s</td><td className="table-cell">{flight.max_altitude_m.toFixed(1)} m</td><td className="table-cell">{flight.distance_m.toFixed(0)} m</td><td className="table-cell">{flight.telemetry_count}</td><td className="table-cell">{flight.max_risk_score}/100</td><td className="table-cell"><StatusBadge tone={flight.status === 'completed' ? 'good' : 'info'}>{flight.status}</StatusBadge></td></tr>)}</tbody></table></div>}
    </Panel>

    <Panel title="Telemetry samples" subtitle="Select one or more stored telemetry records for a scoped CSV export." className="mt-5" action={<button className="button-secondary" disabled={!selectedTelemetry.length} onClick={() => void download(`/telemetry/export.csv?ids=${selectedTelemetry.join(',')}`, 'selected-telemetry.csv')}><Download size={14} />Export selected ({selectedTelemetry.length})</button>}>
      <p className="mb-3 text-[11px] text-slate-500">{records.length} samples returned in the latest query. SQLite is used locally; PostgreSQL is supported for deployment.</p>
      {visibleSamples.length ? <div className="overflow-x-auto"><table className="w-full min-w-[820px] border-collapse"><thead><tr><th className="table-header w-9"><span className="sr-only">Select</span></th>{['Timestamp', 'Source', 'Mode', 'Position', 'Altitude', 'Speed', 'Battery', 'Risk'].map((label) => <th key={label} className="table-header">{label}</th>)}</tr></thead><tbody>{visibleSamples.map((record) => <tr key={record.id} className="hover:bg-slate-900/40"><td className="table-cell"><input type="checkbox" aria-label={`Select telemetry record ${record.id}`} checked={selectedTelemetry.includes(record.id)} onChange={() => toggleTelemetry(record.id)} className="accent-emerald-400" /></td><td className="table-cell font-mono text-[10px]">{format(new Date(record.timestamp), 'HH:mm:ss')}</td><td className="table-cell">{record.source === 'mock' ? <span className="text-amber-300">SIMULATED</span> : record.source.toUpperCase()}</td><td className="table-cell">{record.flight_mode}</td><td className="table-cell font-mono text-[10px]">{record.latitude?.toFixed(5) ?? '—'}, {record.longitude?.toFixed(5) ?? '—'}</td><td className="table-cell">{record.relative_altitude_m?.toFixed(1) ?? '—'} m</td><td className="table-cell">{record.ground_speed_m_s?.toFixed(1) ?? '—'} m/s</td><td className="table-cell">{record.battery_remaining_pct?.toFixed(0) ?? '—'}%</td><td className="table-cell">{record.flight_risk_score}/100</td></tr>)}</tbody></table></div> : <p className="py-8 text-center text-xs text-slate-500">No telemetry samples have been saved yet.</p>}
      {records.length > 0 && <p className="mt-3 text-[10px] text-slate-600">Most recent sample: {format(new Date(records[records.length - 1].timestamp), 'PPpp')}</p>}
    </Panel>
  </>;
}
