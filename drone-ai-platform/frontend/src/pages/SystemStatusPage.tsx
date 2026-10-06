import { useCallback, useEffect, useState } from 'react';
import { Activity, CircleCheck, CircleX, Database, Globe2, RefreshCw, Radio, Server, Wifi } from 'lucide-react';
import type { SystemEvent, SystemStatus, Telemetry } from '../types';
import { PageHeading, Panel, StatusBadge } from '../components/common';
import { api } from '../services/api';

function StatusItem({ icon, title, detail, value }: { icon: React.ReactNode; title: string; detail: string; value: string }) {
  const good = ['online', 'connected', 'simulated', 'client-reported'].includes(value.toLowerCase());
  const pending = ['not used', 'disabled'].includes(value.toLowerCase());
  return <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4"><span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${good ? 'bg-accent/10 text-accent' : pending ? 'bg-slate-800 text-slate-400' : 'bg-amber-400/10 text-amber-300'}`}>{icon}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-xs font-semibold text-white">{title}</h3><StatusBadge tone={good ? 'good' : pending ? 'neutral' : 'warning'} dot>{value}</StatusBadge></div><p className="mt-1 text-[10px] text-slate-500">{detail}</p></div></div>;
}

export function SystemStatusPage({ telemetry, socketConnected }: { telemetry: Telemetry | null; socketConnected: boolean }) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [events, setEvents] = useState<SystemEvent[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextStatus, nextEvents] = await Promise.all([api.systemStatus(), api.systemEvents()]);
      setStatus(nextStatus);
      setEvents(nextEvents);
      setError('');
    }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'System status unavailable'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 15000); return () => window.clearInterval(timer); }, [load]);
  const px4Value = status?.px4 || (telemetry?.connected ? telemetry.source === 'mock' ? 'simulated' : 'connected' : 'offline');
  const mavsdkValue = status?.mavsdk || (telemetry?.source === 'mock' ? 'not used' : 'offline');
  return <>
    <PageHeading eyebrow="Platform observability" title="System status" description="Health checks for the application, database, telemetry transport and PX4 link." action={<button className="button-secondary" onClick={() => void load()} disabled={loading}><RefreshCw size={14} className={loading ? 'animate-spin' : ''} />Refresh checks</button>} />
    {error && <div role="alert" className="mb-4 rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs text-rose-200">{error}</div>}
    <div className="mb-5 grid gap-3 md:grid-cols-2">
      <StatusItem icon={<Server size={18} />} title="FastAPI backend" detail="REST API and WebSocket process" value={status?.api || 'online'} />
      <StatusItem icon={<Database size={18} />} title="Database" detail="SQLAlchemy database connection" value={status?.database || 'checking'} />
      <StatusItem icon={<Radio size={18} />} title="PX4 vehicle" detail={`Telemetry mode: ${status?.telemetry_mode || telemetry?.source || 'unknown'}`} value={px4Value} />
      <StatusItem icon={<Activity size={18} />} title="MAVSDK" detail="Asynchronous MAVLink bridge" value={mavsdkValue} />
      <StatusItem icon={<Wifi size={18} />} title="WebSocket" detail="Live telemetry channel · automatic reconnect" value={socketConnected ? 'connected' : 'offline'} />
      <StatusItem icon={<Globe2 size={18} />} title="Frontend" detail="This browser session reached the application" value="client-reported" />
    </div>
    <Panel title="Connection diagnostics" subtitle="Current heartbeat and source details">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[
        ['Telemetry source', telemetry?.source || 'offline'],
        ['Connection state', telemetry?.connection_state || 'offline'],
        ['Vehicle mode', telemetry?.flight_mode || 'unknown'],
        ['Last received', status?.last_telemetry_at ? new Date(status.last_telemetry_at).toLocaleString() : 'waiting'],
      ].map(([label, value]) => <div key={label} className="rounded-lg bg-slate-900/60 p-3"><p className="text-[9px] font-semibold uppercase tracking-wider text-slate-600">{label}</p><p className="mt-1.5 truncate text-xs font-medium text-slate-200">{value}</p></div>)}</div>
      <div className="mt-4 flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-900/30 p-3 text-[10px] leading-5 text-slate-500"><CircleCheck size={13} className="mt-0.5 shrink-0 text-accent" />API and WebSocket statuses are observed from this client. The backend cannot independently assert browser rendering health.</div>
      {telemetry?.last_error && <div className="mt-3 flex items-start gap-2 rounded-lg border border-rose-400/15 bg-rose-400/[0.05] p-3 text-[10px] leading-5 text-rose-200"><CircleX size={13} className="mt-0.5 shrink-0" />{telemetry.last_error}</div>}
    </Panel>
    <Panel title="Recent system events" subtitle="Connection transitions and accepted operator commands" className="mt-5">
      {events.length ? <div className="divide-y divide-slate-800/70">{events.slice(0, 12).map((event) => <div key={event.id} className="flex flex-wrap items-center gap-3 py-3 first:pt-0 last:pb-0"><StatusBadge tone={event.level === 'ERROR' || event.level === 'CRITICAL' ? 'critical' : event.level === 'WARNING' ? 'warning' : 'info'}>{event.level}</StatusBadge><span className="min-w-24 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{event.category.replaceAll('_', ' ')}</span><span className="min-w-0 flex-1 text-xs text-slate-300">{event.message}</span><time className="text-[10px] text-slate-600">{new Date(event.created_at).toLocaleString()}</time></div>)}</div> : <p className="py-5 text-xs text-slate-500">No system events have been recorded yet.</p>}
    </Panel>
  </>;
}
