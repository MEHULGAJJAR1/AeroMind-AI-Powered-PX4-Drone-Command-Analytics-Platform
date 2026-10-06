import type { ReactNode } from 'react';
import { Activity, ArrowDownRight, ArrowUpRight } from 'lucide-react';

export function PageHeading({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.2em] text-accent/80">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-[28px]">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm text-slate-400">{description}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  );
}

export function Panel({ title, subtitle, action, className = '', children }: { title?: string; subtitle?: string; action?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <section className={`panel ${className}`}>
      {(title || action) && (
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-sm font-semibold text-white">{title}</h2>}
            {subtitle && <p className="mt-1 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatusBadge({ children, tone = 'neutral', dot = false }: { children: ReactNode; tone?: 'good' | 'warning' | 'critical' | 'neutral' | 'info'; dot?: boolean }) {
  const styles = {
    good: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300',
    warning: 'border-amber-400/20 bg-amber-400/10 text-amber-300',
    critical: 'border-rose-400/20 bg-rose-400/10 text-rose-300',
    neutral: 'border-slate-500/20 bg-slate-500/10 text-slate-300',
    info: 'border-cyan-400/20 bg-cyan-400/10 text-cyan-300',
  };
  const dotStyles = { good: 'bg-emerald-400', warning: 'bg-amber-400', critical: 'bg-rose-400', neutral: 'bg-slate-400', info: 'bg-cyan-400' };
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${styles[tone]}`}>{dot && <span className={`h-1.5 w-1.5 rounded-full ${dotStyles[tone]}`} />}{children}</span>;
}

export function MetricCard({ label, value, unit, icon, tone = 'mint', hint, trend }: { label: string; value: string | number; unit?: string; icon: ReactNode; tone?: 'mint' | 'blue' | 'amber' | 'rose'; hint?: string; trend?: 'up' | 'down' | 'steady' }) {
  const colors = { mint: 'bg-accent/10 text-accent', blue: 'bg-cyan-400/10 text-cyan-300', amber: 'bg-amber-400/10 text-amber-300', rose: 'bg-rose-400/10 text-rose-300' };
  return (
    <div className="panel group min-w-0 transition duration-200 hover:-translate-y-0.5 hover:border-slate-600/80">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-slate-400">{label}</p>
          <div className="mt-3 flex items-baseline gap-1.5">
            <span className="truncate text-[26px] font-semibold tabular-nums tracking-tight text-white">{value}</span>
            {unit && <span className="text-xs text-slate-500">{unit}</span>}
          </div>
        </div>
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${colors[tone]}`}>{icon}</div>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="truncate text-[11px] text-slate-500">{hint || 'Live telemetry'}</span>
        {trend === 'up' ? <ArrowUpRight size={14} className="text-accent" /> : trend === 'down' ? <ArrowDownRight size={14} className="text-amber-300" /> : <Activity size={13} className="text-slate-600" />}
      </div>
    </div>
  );
}

export function EmptyState({ icon, title, message, action }: { icon?: ReactNode; title: string; message: string; action?: ReactNode }) {
  return <div className="flex min-h-52 flex-col items-center justify-center rounded-xl border border-dashed border-slate-700/70 px-6 py-10 text-center">
    <div className="mb-3 text-slate-500">{icon || <Activity size={22} />}</div>
    <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
    <p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">{message}</p>
    {action && <div className="mt-4">{action}</div>}
  </div>;
}

export function LoadingState({ label = 'Loading data' }: { label?: string }) {
  return <div className="flex items-center gap-2 py-8 text-xs text-slate-500"><span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-700 border-t-accent" />{label}</div>;
}
