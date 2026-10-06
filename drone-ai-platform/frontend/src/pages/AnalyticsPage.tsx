import { useEffect, useState } from 'react';
import { BrainCircuit, CircleHelp, Lightbulb, ShieldAlert, Sparkles } from 'lucide-react';
import type { Telemetry } from '../types';
import type { AnalyticsSummary } from '../types';
import { AlertsPanel } from '../components/AlertsPanel';
import { PageHeading, Panel, StatusBadge } from '../components/common';
import { StatusRing } from '../components/StatusRing';
import { TelemetryChart } from '../components/TelemetryChart';
import { api } from '../services/api';

export function AnalyticsPage({ telemetry, history }: { telemetry: Telemetry | null; history: Telemetry[] }) {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    const load = () => api.analytics().then((value) => { if (live) { setSummary(value); setError(''); } }).catch((failure) => { if (live) setError(failure instanceof Error ? failure.message : 'Analytics unavailable'); });
    void load();
    const timer = window.setInterval(() => void load(), 8000);
    return () => { live = false; window.clearInterval(timer); };
  }, []);
  const alerts = summary?.active_alerts ?? telemetry?.active_alerts ?? [];
  const risk = summary?.flight_risk_score ?? telemetry?.flight_risk_score ?? 0;
  const health = summary?.drone_health_score ?? telemetry?.drone_health_score ?? 100;
  return <>
    <PageHeading eyebrow="Machine intelligence" title="AI analytics" description="Explainable anomaly detection across battery, GPS, speed, altitude, estimator and sensor status." action={<StatusBadge tone="info"><BrainCircuit size={12} />Rules + IsolationForest</StatusBadge>} />
    {telemetry?.source === 'mock' && <div className="mb-5 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3 text-xs text-amber-200">Analytics are running on simulated telemetry. Scores are illustrative and must not be used as a safety certification.</div>}
    {error && <div role="alert" className="mb-4 rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs text-rose-200">{error}</div>}
    <div className="mb-5 grid gap-5 lg:grid-cols-[1fr_1fr_1fr]">
      <Panel className="flex items-center justify-between gap-4"><div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Flight risk score</p><p className="mt-2 text-xs text-slate-500">0 low · 100 critical</p></div><StatusRing score={risk} label="Risk" tone={risk > 60 ? 'rose' : risk > 30 ? 'amber' : 'mint'} /></Panel>
      <Panel className="flex items-center justify-between gap-4"><div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Drone health score</p><p className="mt-2 text-xs text-slate-500">Available checks only</p></div><StatusRing score={health} label="Health" tone={health < 55 ? 'rose' : health < 80 ? 'amber' : 'blue'} /></Panel>
      <Panel className="flex flex-col justify-center"><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Anomaly count</p><div className="mt-3 flex items-end justify-between"><span className="text-4xl font-semibold tabular-nums text-white">{summary?.anomaly_count ?? telemetry?.anomaly_count ?? 0}</span><span className="mb-1 flex items-center gap-1.5 text-xs text-slate-500"><ShieldAlert size={14} />active findings</span></div><p className="mt-2 text-[10px] text-slate-600">Based on latest telemetry sample</p></Panel>
    </div>
    <div className="mb-5 grid gap-5 xl:grid-cols-[1.35fr_.8fr]">
      <Panel title="Risk and health timeline" subtitle={`${summary?.history_samples ?? history.length} recent telemetry samples`}><TelemetryChart history={history} metric="flight_risk_score" title="Flight risk" color="#fb7185" unit="/100" height={200} /><div className="my-5 border-t border-slate-800" /><TelemetryChart history={history} metric="drone_health_score" title="Drone health" color="#67a4ff" unit="/100" height={170} /></Panel>
      <Panel title="Current findings" subtitle="Every finding includes a reason and recommended response"><AlertsPanel alerts={alerts} /></Panel>
    </div>
    <Panel title="Recommendations" subtitle="Operational prompts from the active risk model" action={<span className="flex items-center gap-1.5 text-[10px] text-slate-500"><CircleHelp size={13} />Decision support, not flight authority</span>}>
      <div className="grid gap-3 md:grid-cols-2">{(summary?.recommendations ?? telemetry?.recommendations ?? ['Waiting for telemetry samples before generating recommendations.']).map((item, index) => <div key={`${item}-${index}`} className="flex gap-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent"><Lightbulb size={16} /></span><div><p className="text-xs font-semibold text-slate-200">Recommendation {index + 1}</p><p className="mt-1 text-xs leading-5 text-slate-400">{item}</p></div></div>)}</div>
      <div className="mt-4 flex items-center gap-2 text-[10px] text-slate-600"><Sparkles size={12} />Model: {summary?.model ?? 'rules + rolling IsolationForest'} · Source: {summary?.source ?? telemetry?.source ?? 'offline'}</div>
    </Panel>
  </>;
}
