import { useMemo } from 'react';
import { Activity, Battery, MapPin, Satellite, Signal, Wifi } from 'lucide-react';
import type { Telemetry } from '../types';
import { MetricCard, PageHeading, Panel, StatusBadge } from '../components/common';
import { TelemetryChart } from '../components/TelemetryChart';

export function TelemetryPage({ telemetry, history, socketConnected }: { telemetry: Telemetry | null; history: Telemetry[]; socketConnected: boolean }) {
  const records = useMemo(() => [...history].reverse().slice(0, 25), [history]);
  return <>
    <PageHeading eyebrow="Vehicle data" title="Telemetry" description="Live PX4/MAVLink measurements with availability-aware sensor fields." action={<StatusBadge tone={socketConnected ? 'good' : 'warning'} dot>{socketConnected ? 'WebSocket live' : 'HTTP fallback'}</StatusBadge>} />
    <div className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
      <MetricCard label="Latitude" value={telemetry?.latitude?.toFixed(5) ?? '—'} icon={<MapPin size={17} />} tone="blue" />
      <MetricCard label="Longitude" value={telemetry?.longitude?.toFixed(5) ?? '—'} icon={<MapPin size={17} />} tone="blue" />
      <MetricCard label="Battery voltage" value={telemetry?.battery_voltage_v?.toFixed(2) ?? '—'} unit="V" icon={<Battery size={17} />} tone="amber" />
      <MetricCard label="Link quality" value={telemetry?.link_quality_pct?.toFixed(0) ?? '—'} unit="%" icon={<Signal size={17} />} />
    </div>
    <div className="mb-5 grid gap-5 xl:grid-cols-2">
      <Panel title="Altitude profile" subtitle="Relative altitude above launch position"><TelemetryChart history={history} metric="relative_altitude_m" title="Altitude" unit="m" height={250} /></Panel>
      <Panel title="Velocity profile" subtitle="Ground speed derived from NED velocity"><TelemetryChart history={history} metric="ground_speed_m_s" title="Ground speed" color="#67a4ff" unit="m/s" height={250} /></Panel>
      <Panel title="Battery trend" subtitle="Remaining battery percentage"><TelemetryChart history={history} metric="battery_remaining_pct" title="Battery remaining" color="#f3bd5b" unit="%" height={230} /></Panel>
      <Panel title="GNSS quality" subtitle="Satellites reported by PX4"><TelemetryChart history={history} metric="gps_satellites" title="Satellite count" color="#a78bfa" unit="sat" height={230} /></Panel>
    </div>
    <Panel title="Recent samples" subtitle={`${records.length} most recent samples received in this browser session`}>
      {records.length ? <div className="overflow-x-auto"><table className="w-full min-w-[820px] border-collapse"><thead><tr>{['Timestamp', 'Source', 'Flight mode', 'Altitude', 'Speed', 'Battery', 'GPS', 'Risk'].map((item) => <th key={item} className="table-header">{item}</th>)}</tr></thead><tbody>{records.map((item, index) => <tr key={`${item.timestamp}-${index}`} className="hover:bg-slate-900/50"><td className="table-cell font-mono text-[10px]">{new Date(item.timestamp).toLocaleTimeString()}</td><td className="table-cell">{item.source === 'mock' ? <span className="text-amber-300">SIM</span> : item.source.toUpperCase()}</td><td className="table-cell">{item.flight_mode}</td><td className="table-cell">{item.relative_altitude_m?.toFixed(1) ?? '—'} m</td><td className="table-cell">{item.ground_speed_m_s?.toFixed(1) ?? '—'} m/s</td><td className="table-cell">{item.battery_remaining_pct?.toFixed(0) ?? '—'}%</td><td className="table-cell">{item.gps_satellites ?? '—'} <Satellite size={11} className="ml-1 inline text-slate-600" /></td><td className="table-cell"><span className={item.flight_risk_score > 60 ? 'text-rose-300' : item.flight_risk_score > 30 ? 'text-amber-300' : 'text-accent'}>{item.flight_risk_score}</span></td></tr>)}</tbody></table></div> : <div className="flex items-center justify-center gap-2 py-12 text-xs text-slate-500"><Wifi size={15} />Waiting for telemetry samples…</div>}
      <div className="mt-4 flex items-center gap-2 text-[10px] text-slate-600"><Activity size={12} />Ground speed is horizontal NED velocity; airspeed, CPU load and link metrics remain null when PX4 does not report them.</div>
    </Panel>
  </>;
}
