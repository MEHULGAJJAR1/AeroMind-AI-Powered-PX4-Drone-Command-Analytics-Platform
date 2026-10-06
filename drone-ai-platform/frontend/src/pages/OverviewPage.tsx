import { useMemo } from 'react';
import { Activity, Battery, Compass, Gauge, Navigation, Radio, Satellite, ShieldAlert, Signal } from 'lucide-react';
import type { Telemetry } from '../types';
import type { PageId } from '../components/Sidebar';
import { AlertsPanel } from '../components/AlertsPanel';
import { MapView } from '../components/MapView';
import { MetricCard, PageHeading, Panel, StatusBadge } from '../components/common';
import { StatusRing } from '../components/StatusRing';
import { TelemetryChart } from '../components/TelemetryChart';

export function OverviewPage({ telemetry, history, socketConnected, onNavigate }: { telemetry: Telemetry | null; history: Telemetry[]; socketConnected: boolean; onNavigate: (page: PageId) => void }) {
  const position = telemetry?.latitude != null && telemetry.longitude != null ? `${telemetry.latitude.toFixed(5)}°, ${telemetry.longitude.toFixed(5)}°` : '—';
  const mode = telemetry?.source === 'mock' ? 'SIMULATED' : telemetry?.source === 'px4' ? 'PX4 SITL' : 'OFFLINE';
  const alertCount = telemetry?.active_alerts.length || 0;
  const flightClock = useMemo(() => {
    const seconds = telemetry?.flight_time_seconds || 0;
    return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }, [telemetry?.flight_time_seconds]);
  return <>
    <PageHeading eyebrow="Operations overview" title="Mission control" description="A live operational picture of vehicle state, telemetry quality and flight risk." action={<button className="button-secondary" onClick={() => onNavigate('live')}><Radio size={14} />Open live flight</button>} />
    {telemetry?.source === 'mock' && <div className="mb-5 flex items-center gap-2 rounded-xl border border-amber-400/20 bg-amber-400/[0.07] px-4 py-3 text-xs text-amber-200"><span className="h-2 w-2 rounded-full bg-amber-300" /><strong>DEMO MODE</strong><span className="text-amber-100/70">Displayed values are simulated and are not a real aircraft connection.</span></div>}
    <div className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
      <MetricCard label="Relative altitude" value={telemetry?.relative_altitude_m?.toFixed(1) ?? '—'} unit="m" icon={<Navigation size={18} />} hint={telemetry?.absolute_altitude_m != null ? `MSL ${telemetry.absolute_altitude_m.toFixed(1)} m` : 'No position altitude'} tone="mint" />
      <MetricCard label="Ground speed" value={telemetry?.ground_speed_m_s?.toFixed(1) ?? '—'} unit="m/s" icon={<Gauge size={18} />} hint={telemetry?.airspeed_m_s != null ? `Airspeed ${telemetry.airspeed_m_s.toFixed(1)} m/s` : 'Airspeed unavailable'} tone="blue" />
      <MetricCard label="Battery remaining" value={telemetry?.battery_remaining_pct?.toFixed(0) ?? '—'} unit="%" icon={<Battery size={18} />} hint={telemetry?.battery_voltage_v != null ? `${telemetry.battery_voltage_v.toFixed(1)} V · ${telemetry.battery_current_a?.toFixed(1) ?? '—'} A` : 'Voltage unavailable'} tone={(telemetry?.battery_remaining_pct ?? 100) < 20 ? 'rose' : 'amber'} />
      <MetricCard label="GPS satellites" value={telemetry?.gps_satellites ?? '—'} unit="sat" icon={<Satellite size={18} />} hint={telemetry?.gps_fix_type || 'Fix status unavailable'} tone="blue" />
    </div>

    <div className="mb-5 grid gap-5 xl:grid-cols-[1.55fr_.85fr]">
      <Panel title="Flight track" subtitle={`${position} · Home distance ${telemetry?.distance_from_home_m?.toFixed(0) ?? '—'} m`} action={<StatusBadge tone={telemetry?.source === 'mock' ? 'warning' : telemetry?.connected ? 'good' : 'critical'} dot>{mode}</StatusBadge>} className="overflow-hidden !p-3 sm:!p-4">
        <MapView telemetry={telemetry} history={history} height="h-[280px] sm:h-[350px]" />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 px-1 text-[10px] text-slate-500">
          <div className="flex flex-wrap gap-4"><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-accent" />Vehicle / track</span><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-blue-400" />Home</span></div>
          <span>Map tiles © OpenStreetMap</span>
        </div>
      </Panel>
      <div className="flex flex-col gap-5">
        <Panel title="Vehicle state" subtitle="Connection and current flight mode">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Link status</p><div className="mt-2 flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${telemetry?.connected ? 'bg-accent shadow-[0_0_8px_#64e4b6]' : 'bg-rose-400'}`} /><span className="text-sm font-semibold text-white">{telemetry?.connected ? 'Connected' : 'Offline'}</span></div><p className="mt-1 text-[10px] text-slate-500">{telemetry?.source === 'mock' ? 'Simulated link' : socketConnected ? 'WebSocket live' : 'API fallback'}</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Armed state</p><div className="mt-2"><StatusBadge tone={telemetry?.armed ? 'warning' : 'neutral'} dot>{telemetry?.armed ? 'Armed' : 'Disarmed'}</StatusBadge></div><p className="mt-2 truncate text-[10px] text-slate-500">{telemetry?.flight_mode || '—'}</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Flight time</p><p className="mt-2 font-mono text-lg font-semibold text-white">{flightClock}</p><p className="mt-1 text-[10px] text-slate-500">HH:MM elapsed</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Heading</p><p className="mt-2 flex items-center gap-2 text-lg font-semibold text-white"><Compass size={16} className="text-accent" />{telemetry?.heading_deg?.toFixed(0) ?? '—'}°</p><p className="mt-1 text-[10px] text-slate-500">{position}</p></div>
          </div>
          <div className="mt-4 flex items-center justify-between border-t border-slate-800 pt-4"><div className="flex items-center gap-2"><Signal size={14} className="text-slate-500" /><span className="text-xs text-slate-400">Link quality</span></div><span className="text-xs font-semibold text-slate-200">{telemetry?.link_quality_pct != null ? `${telemetry.link_quality_pct.toFixed(0)}%` : 'Not reported'}</span></div>
        </Panel>
        <Panel title="AI flight risk" subtitle="Explainable checks from the recent telemetry window" action={<button onClick={() => onNavigate('analytics')} className="text-[10px] font-semibold text-accent hover:text-emerald-200">Details</button>}>
          <div className="flex items-center gap-5"><StatusRing score={telemetry?.flight_risk_score ?? 0} label="Risk" tone={(telemetry?.flight_risk_score ?? 0) > 60 ? 'rose' : (telemetry?.flight_risk_score ?? 0) > 30 ? 'amber' : 'mint'} size="sm" /><div><p className="text-sm font-semibold text-white">{alertCount ? `${alertCount} active finding${alertCount === 1 ? '' : 's'}` : 'No active anomalies'}</p><p className="mt-1 text-xs leading-5 text-slate-500">Health score <span className="text-slate-300">{telemetry?.drone_health_score ?? '—'}/100</span></p><p className="mt-2 flex items-center gap-1.5 text-[10px] text-slate-500"><Activity size={12} />Rules + IsolationForest</p></div></div>
        </Panel>
      </div>
    </div>

    <div className="grid gap-5 xl:grid-cols-[1.25fr_.75fr]">
      <Panel title="Flight telemetry" subtitle="Recent altitude and ground speed samples" action={<button onClick={() => onNavigate('telemetry')} className="text-[10px] font-semibold text-accent hover:text-emerald-200">Full telemetry</button>}>
        <TelemetryChart history={history} metric="relative_altitude_m" title="Altitude AGL" color="#64e4b6" unit="m" height={170} />
        <div className="my-4 border-t border-slate-800" />
        <TelemetryChart history={history} metric="ground_speed_m_s" title="Ground speed" color="#67a4ff" unit="m/s" height={140} />
      </Panel>
      <Panel title="Active alerts" subtitle="Telemetry-generated findings" action={<button onClick={() => onNavigate('alerts')} className="text-[10px] font-semibold text-accent hover:text-emerald-200">View center</button>}>
        {alertCount ? <AlertsPanel alerts={telemetry?.active_alerts || []} compact /> : <div className="rounded-xl border border-emerald-400/10 bg-emerald-400/[0.035] p-4"><div className="flex items-center gap-2 text-emerald-300"><ShieldAlert size={16} /><span className="text-xs font-semibold">No active warnings</span></div><p className="mt-2 text-xs leading-5 text-slate-500">Altitude, speed, battery, GNSS, estimator and sensor health are being monitored.</p></div>}
        <div className="mt-4 grid grid-cols-2 gap-2"><div className="rounded-lg bg-slate-900/70 p-3"><p className="text-[9px] uppercase tracking-wider text-slate-500">EKF health</p><p className={`mt-1 text-xs font-semibold ${telemetry?.ekf_ok ? 'text-accent' : telemetry?.ekf_ok === false ? 'text-rose-300' : 'text-slate-400'}`}>{telemetry?.ekf_ok == null ? 'Unavailable' : telemetry.ekf_ok ? 'Healthy' : 'Degraded'}</p></div><div className="rounded-lg bg-slate-900/70 p-3"><p className="text-[9px] uppercase tracking-wider text-slate-500">Air speed</p><p className="mt-1 text-xs font-semibold text-slate-300">{telemetry?.airspeed_m_s != null ? `${telemetry.airspeed_m_s.toFixed(1)} m/s` : 'Not reported'}</p></div></div>
      </Panel>
    </div>
  </>;
}
