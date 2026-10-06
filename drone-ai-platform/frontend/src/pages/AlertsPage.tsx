import { useEffect, useState } from 'react';
import { Bell, CheckCheck, RefreshCw } from 'lucide-react';
import type { AlertRecord } from '../types';
import { AlertsPanel } from '../components/AlertsPanel';
import { PageHeading, Panel, StatusBadge } from '../components/common';
import { api } from '../services/api';

export function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [filter, setFilter] = useState<'all' | 'open' | 'acknowledged'>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = async () => {
    setLoading(true);
    try { setAlerts(await api.alerts()); setError(''); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not load alerts'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const acknowledge = async (id: string) => {
    try {
      const saved = await api.acknowledgeAlert(id);
      setAlerts((current) => current.map((item) => item.id === id ? saved : item));
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not acknowledge alert'); }
  };
  const filtered = alerts.filter((alert) => filter === 'all' || (filter === 'open' ? !alert.acknowledged_at : Boolean(alert.acknowledged_at)));
  const activeCount = alerts.filter((alert) => !alert.acknowledged_at).length;
  return <>
    <PageHeading eyebrow="Operational awareness" title="Alerts center" description="Review, acknowledge and track explainable findings from the telemetry stream." action={<button className="button-secondary" onClick={() => void load()}><RefreshCw size={14} />Refresh</button>} />
    <div className="mb-5 grid gap-3 sm:grid-cols-3"><div className="panel"><p className="text-[10px] uppercase tracking-wider text-slate-500">Unacknowledged</p><p className="mt-2 text-3xl font-semibold text-white">{activeCount}</p></div><div className="panel"><p className="text-[10px] uppercase tracking-wider text-slate-500">Critical</p><p className="mt-2 text-3xl font-semibold text-rose-300">{alerts.filter((item) => item.severity === 'CRITICAL' && !item.acknowledged_at).length}</p></div><div className="panel"><p className="text-[10px] uppercase tracking-wider text-slate-500">Acknowledged</p><p className="mt-2 text-3xl font-semibold text-accent">{alerts.filter((item) => item.acknowledged_at).length}</p></div></div>
    {error && <div role="alert" className="mb-4 rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs text-rose-200">{error}</div>}
    <Panel title="Alert history" subtitle="INFO · WARNING · CRITICAL" action={<div className="flex items-center gap-2"><StatusBadge tone={activeCount ? 'warning' : 'good'} dot>{activeCount} open</StatusBadge><select className="field !w-auto !py-2 text-xs" aria-label="Filter alerts" value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}><option value="all">All alerts</option><option value="open">Unacknowledged</option><option value="acknowledged">Acknowledged</option></select></div>}>
      {loading ? <div className="py-10 text-center text-xs text-slate-500">Loading alerts…</div> : filtered.length ? <AlertsPanel alerts={filtered} onAcknowledge={(id) => void acknowledge(id)} /> : <div className="flex flex-col items-center py-12 text-center"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent/10 text-accent"><CheckCheck size={20} /></span><h3 className="mt-3 text-sm font-semibold text-white">No alerts in this view</h3><p className="mt-1 text-xs text-slate-500">{alerts.length ? 'Try another filter or continue monitoring telemetry.' : 'New alerts are generated automatically when telemetry crosses configured thresholds.'}</p><Bell size={14} className="mt-4 text-slate-700" /></div>}
    </Panel>
  </>;
}
