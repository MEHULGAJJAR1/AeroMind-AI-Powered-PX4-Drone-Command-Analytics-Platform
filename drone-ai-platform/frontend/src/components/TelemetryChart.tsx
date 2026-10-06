import { useMemo } from 'react';
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Telemetry } from '../types';

const tooltipStyle = { background: '#101827', border: '1px solid #2a394f', borderRadius: 10, color: '#e2e8f0', fontSize: 11 };

export function TelemetryChart({ history, metric, title, color = '#64e4b6', unit = '', kind = 'area', height = 220 }: {
  history: Telemetry[];
  metric: 'relative_altitude_m' | 'ground_speed_m_s' | 'battery_remaining_pct' | 'flight_risk_score' | 'drone_health_score' | 'gps_satellites';
  title?: string;
  color?: string;
  unit?: string;
  kind?: 'area' | 'line';
  height?: number;
}) {
  const data = useMemo(() => history.slice(-90).map((item) => ({
    time: new Date(item.timestamp).toLocaleTimeString([], { minute: '2-digit', second: '2-digit' }),
    value: item[metric] == null ? null : Number(item[metric]),
  })), [history, metric]);
  const latest = data.at(-1)?.value;
  return <div className="min-w-0">
    {title && <div className="mb-3 flex items-center justify-between"><span className="text-xs font-medium text-slate-300">{title}</span>{latest != null && <span className="text-xs font-semibold tabular-nums text-white">{latest.toFixed(1)} {unit}</span>}</div>}
    {data.length < 2 ? <div className="flex items-center justify-center text-xs text-slate-600" style={{ height }}>Collecting live samples…</div> : <ResponsiveContainer width="100%" height={height}>
      {kind === 'area' ? <AreaChart data={data} margin={{ top: 5, right: 4, left: -20, bottom: 0 }}>
        <defs><linearGradient id={`fill-${metric}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity={0.22} /><stop offset="95%" stopColor={color} stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid stroke="#253246" strokeDasharray="4 5" vertical={false} />
        <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 9 }} tickLine={false} axisLine={false} minTickGap={28} />
        <YAxis tick={{ fill: '#64748b', fontSize: 9 }} tickLine={false} axisLine={false} width={34} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value) => [`${Number(value).toFixed(1)} ${unit}`, title || metric]} labelStyle={{ color: '#94a3b8' }} />
        <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill={`url(#fill-${metric})`} connectNulls isAnimationActive={false} />
      </AreaChart> : <LineChart data={data} margin={{ top: 5, right: 4, left: -20, bottom: 0 }}>
        <CartesianGrid stroke="#253246" strokeDasharray="4 5" vertical={false} />
        <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 9 }} tickLine={false} axisLine={false} minTickGap={28} />
        <YAxis tick={{ fill: '#64748b', fontSize: 9 }} tickLine={false} axisLine={false} width={34} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value) => [`${Number(value).toFixed(1)} ${unit}`, title || metric]} labelStyle={{ color: '#94a3b8' }} />
        <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
      </LineChart>}
    </ResponsiveContainer>}
  </div>;
}
