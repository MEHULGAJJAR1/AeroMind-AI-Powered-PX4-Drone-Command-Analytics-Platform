import { useState } from 'react';
import { Clock3, Compass, Link2, MapPin, Radio, RotateCw } from 'lucide-react';
import type { Telemetry } from '../types';
import { FlightControls } from '../components/FlightControls';
import { MapView } from '../components/MapView';
import { MetricCard, PageHeading, Panel, StatusBadge } from '../components/common';
import { TelemetryChart } from '../components/TelemetryChart';
import { api } from '../services/api';
export function LiveFlightPage({ telemetry, history, socketConnected, onRefresh }: { telemetry: Telemetry | null; history: Telemetry[]; socketConnected: boolean; onRefresh: () => Promise<unknown> }) {
  const [refreshing, setRefreshing] = useState(false);
  const [connectionFeedback, setConnectionFeedback] = useState('');
  const refresh = async () => {
    setRefreshing(true);
    try { await onRefresh(); } catch { /* The global telemetry banner reports the API error. */ } finally { setRefreshing(false); }
  };
  const requestConnect = async () => {
    setRefreshing(true);
    try {
      const result = await api.connect();
      setConnectionFeedback(result.message);
      await onRefresh();
    } catch (failure) {
      setConnectionFeedback(failure instanceof Error ? failure.message : 'Connection request failed');
    } finally { setRefreshing(false); }
  };
  return <>
    <PageHeading eyebrow="Live operations" title="Live flight" description="Vehicle position, flight state and guarded PX4 actions." action={<><StatusBadge tone={telemetry?.source === 'mock' ? 'warning' : telemetry?.connected ? 'good' : 'critical'} dot>{telemetry?.source === 'mock' ? 'Simulated' : telemetry?.connected ? 'PX4 connected' : 'Disconnected'}</StatusBadge>{telemetry?.source !== 'mock' && <button className="button-secondary !px-2.5 !py-2" disabled={refreshing} onClick={() => void requestConnect()}><Link2 size={13} />{telemetry?.connected ? 'Reconnect' : 'Connect PX4'}</button>}<button className="icon-button" aria-label="Refresh telemetry" onClick={() => void refresh()}><RotateCw size={15} className={refreshing ? 'animate-spin' : ''} /></button></>} />
    <div className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
      <MetricCard label="Altitude AGL" value={telemetry?.relative_altitude_m?.toFixed(1) ?? '—'} unit="m" icon={<MapPin size={17} />} />
      <MetricCard label="Speed" value={telemetry?.ground_speed_m_s?.toFixed(1) ?? '—'} unit="m/s" icon={<Radio size={17} />} tone="blue" />
      <MetricCard label="Heading" value={telemetry?.heading_deg?.toFixed(0) ?? '—'} unit="°" icon={<Compass size={17} />} tone="amber" />
      <MetricCard label="Flight time" value={`${Math.floor((telemetry?.flight_time_seconds ?? 0) / 60).toString().padStart(2, '0')}:${((telemetry?.flight_time_seconds ?? 0) % 60).toString().padStart(2, '0')}`} icon={<Clock3 size={17} />} tone="blue" />
    </div>
    {telemetry?.source === 'mock' && <div className="mb-4 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">Simulated vehicle feed · commands remain locked until a real PX4 connection is active.</div>}
    {connectionFeedback && <div role="status" className="mb-4 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-xs text-slate-300">{connectionFeedback}</div>}
    <div className="grid gap-5 xl:grid-cols-[1.55fr_.8fr]">
      <div className="space-y-5">
        <Panel title="Live map" subtitle={`${telemetry?.latitude?.toFixed(6) ?? '—'}, ${telemetry?.longitude?.toFixed(6) ?? '—'} · ${socketConnected ? 'WebSocket stream' : 'Polling fallback'}`} className="!p-3 sm:!p-4"><MapView telemetry={telemetry} history={history} follow height="h-[420px] sm:h-[540px]" /></Panel>
        <Panel title="Altitude and speed" subtitle="Rolling live samples"><div className="grid gap-6 md:grid-cols-2"><TelemetryChart history={history} metric="relative_altitude_m" title="Altitude" unit="m" height={185} /><TelemetryChart history={history} metric="ground_speed_m_s" title="Ground speed" color="#67a4ff" unit="m/s" height={185} /></div></Panel>
      </div>
      <div className="space-y-5">
        <Panel><FlightControls telemetry={telemetry} onRefresh={() => void refresh()} /></Panel>
        <Panel title="Navigation" subtitle="Position and home reference">
          <div className="space-y-3">{[
            ['Latitude', telemetry?.latitude?.toFixed(6) ?? '—'],
            ['Longitude', telemetry?.longitude?.toFixed(6) ?? '—'],
            ['Home distance', telemetry?.distance_from_home_m != null ? `${telemetry.distance_from_home_m.toFixed(0)} m` : '—'],
            ['Home position', telemetry?.home_position ? `${telemetry.home_position.latitude.toFixed(5)}, ${telemetry.home_position.longitude.toFixed(5)}` : 'Not set'],
            ['Fix / satellites', `${telemetry?.gps_fix_type || '—'} · ${telemetry?.gps_satellites ?? '—'}`],
          ].map(([key, value]) => <div key={key} className="flex items-start justify-between gap-4 border-b border-slate-800/70 pb-2.5 last:border-0 last:pb-0"><span className="text-xs text-slate-500">{key}</span><span className="text-right font-mono text-[11px] text-slate-200">{value}</span></div>)}</div>
        </Panel>
        <Panel title="Power system" subtitle="Battery telemetry, when available"><div className="mb-4 flex items-end justify-between"><span className="text-4xl font-semibold tabular-nums text-white">{telemetry?.battery_remaining_pct?.toFixed(0) ?? '—'}<span className="ml-1 text-sm text-slate-500">%</span></span><StatusBadge tone={(telemetry?.battery_remaining_pct ?? 100) < 20 ? 'critical' : 'good'}>{(telemetry?.battery_remaining_pct ?? 100) < 20 ? 'Low' : 'Nominal'}</StatusBadge></div><div className="h-2 overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full transition-all ${(telemetry?.battery_remaining_pct ?? 0) < 20 ? 'bg-rose-400' : 'bg-accent'}`} style={{ width: `${Math.max(0, Math.min(100, telemetry?.battery_remaining_pct ?? 0))}%` }} /></div><div className="mt-3 flex justify-between text-[10px] text-slate-500"><span>{telemetry?.battery_voltage_v?.toFixed(1) ?? '—'} V</span><span>{telemetry?.battery_current_a?.toFixed(1) ?? '—'} A</span></div></Panel>
      </div>
    </div>
  </>;
}
