import { AlertTriangle, Check, ChevronRight, Info } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import type { ActiveAlert, AlertRecord } from '../types';
import { EmptyState } from './common';

export function AlertsPanel({ alerts, onAcknowledge, compact = false }: { alerts: (ActiveAlert | AlertRecord)[]; onAcknowledge?: (id: string) => void; compact?: boolean }) {
  if (!alerts.length) return <EmptyState title="All clear" message="No active telemetry warnings are currently being reported." />;
  return <div className="divide-y divide-slate-800/70">
    {alerts.slice(0, compact ? 4 : 30).map((alert, index) => {
      const record = alert as AlertRecord;
      const acknowledged = 'acknowledged_at' in alert && Boolean(record.acknowledged_at);
      const time = 'occurred_at' in alert ? record.occurred_at : null;
      const color = alert.severity === 'CRITICAL' ? 'text-rose-300 bg-rose-400/10' : alert.severity === 'WARNING' ? 'text-amber-300 bg-amber-400/10' : 'text-cyan-300 bg-cyan-400/10';
      return <div key={record.id || `${alert.category}-${index}`} className={`flex items-start gap-3 py-3 first:pt-0 last:pb-0 ${acknowledged ? 'opacity-55' : ''}`}>
        <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${color}`}>{alert.severity === 'INFO' ? <Info size={15} /> : <AlertTriangle size={15} />}</div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><p className="text-xs font-semibold text-slate-100">{alert.title}</p><span className={`rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wider ${color}`}>{alert.severity}</span></div>
          <p className="mt-1 text-xs leading-5 text-slate-400">{alert.message}</p>
          <p className="mt-1 text-[10px] uppercase tracking-[0.12em] text-slate-600">{alert.category.replaceAll('_', ' ')}{time ? ` · ${formatDistanceToNow(new Date(time), { addSuffix: true })}` : ''}</p>
        </div>
        {record.id && onAcknowledge && !acknowledged ? <button className="icon-button text-slate-500 hover:text-accent" aria-label={`Acknowledge ${alert.title}`} onClick={() => onAcknowledge(record.id)}><Check size={15} /></button> : compact ? <ChevronRight size={15} className="mt-1 text-slate-600" /> : null}
      </div>;
    })}
  </div>;
}
