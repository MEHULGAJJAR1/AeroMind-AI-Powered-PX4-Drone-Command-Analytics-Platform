import { Activity, Battery, Check, Cpu, Crosshair, Gauge, Radio, ShieldAlert, Signal, X } from 'lucide-react';
import type { ReactNode } from 'react';
import type { Telemetry } from '../types';
import { MetricCard, PageHeading, Panel, StatusBadge } from '../components/common';
import { StatusRing } from '../components/StatusRing';
import { TelemetryChart } from '../components/TelemetryChart';

function SensorCard({ title, detail, value, icon }: { title: string; detail: string; value: boolean | null | undefined; icon: ReactNode }) {
  const tone = value === true ? 'good' : value === false ? 'critical' : 'neutral';
  return <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4"><div className="flex items-start justify-between"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-800 text-slate-300">{icon}</span>{value == null ? <StatusBadge tone="neutral">Unavailable</StatusBadge> : <StatusBadge tone={tone} dot>{value ? 'Healthy' : 'Attention'}</StatusBadge>}</div><h3 className="mt-4 text-sm font-semibold text-white">{title}</h3><p className="mt-1 text-[11px] leading-5 text-slate-500">{detail}</p><div className={`mt-4 h-1 rounded-full ${value === true ? 'bg-accent/70' : value === false ? 'bg-rose-400/70' : 'bg-slate-700'}`} /></div>;
}

export function DroneHealthPage({ telemetry, history }: { telemetry: Telemetry | null; history: Telemetry[] }) {
  const sensorItems = [
    { title: 'Gyroscope', detail: 'Angular rate sensor calibration and status.', value: telemetry?.gyro_ok, icon: <Crosshair size={17} /> },
    { title: 'Accelerometer', detail: 'Acceleration and gravity reference health.', value: telemetry?.accelerometer_ok, icon: <Activity size={17} /> },
    { title: 'Magnetometer', detail: 'Compass calibration and heading reference.', value: telemetry?.magnetometer_ok, icon: <Radio size={17} /> },
    { title: 'EKF / estimator', detail: 'PX4 local and global state estimate.', value: telemetry?.ekf_ok, icon: <Gauge size={17} /> },
    { title: 'Global position', detail: 'Estimator reports an acceptable global position.', value: telemetry?.global_position_ok, icon: <Signal size={17} /> },
    { title: 'Home position', detail: 'Home location is established and available.', value: telemetry?.home_position_ok, icon: <ShieldAlert size={17} /> },
  ];
  return <>
    <PageHeading eyebrow="Vehicle diagnostics" title="Drone health" description="Estimator, sensor, power and link quality from the active telemetry source." action={<StatusBadge tone={telemetry?.connected ? 'good' : 'critical'} dot>{telemetry?.connected ? 'Telemetry active' : 'No vehicle link'}</StatusBadge>} />
    <div className="mb-5 grid gap-5 lg:grid-cols-[.65fr_1.35fr]">
      <Panel className="flex items-center gap-6"><StatusRing score={telemetry?.drone_health_score ?? 100} label="Health" tone={(telemetry?.drone_health_score ?? 100) < 55 ? 'rose' : (telemetry?.drone_health_score ?? 100) < 80 ? 'amber' : 'mint'} /><div><h2 className="text-sm font-semibold text-white">Overall health</h2><p className="mt-1 text-xs text-slate-500">Derived from PX4 estimator, sensors, GNSS and battery state.</p><p className="mt-3 text-xs font-medium text-slate-300">{telemetry?.anomaly_count ?? 0} active finding{telemetry?.anomaly_count === 1 ? '' : 's'}</p></div></Panel>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
        <MetricCard label="Battery" value={telemetry?.battery_remaining_pct?.toFixed(0) ?? '—'} unit="%" icon={<Battery size={16} />} tone={(telemetry?.battery_remaining_pct ?? 100) < 20 ? 'rose' : 'amber'} />
        <MetricCard label="GPS satellites" value={telemetry?.gps_satellites ?? '—'} unit="sat" icon={<Signal size={16} />} tone="blue" />
        <MetricCard label="CPU load" value={telemetry?.cpu_load_pct?.toFixed(0) ?? '—'} unit="%" icon={<Cpu size={16} />} tone="blue" hint="Not exposed by MAVSDK telemetry stream" />
      </div>
    </div>
    <Panel title="Sensor and estimator checks" subtitle="Unavailable means the active vehicle does not report this measurement; it is not assumed healthy.">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{sensorItems.map((item) => <SensorCard key={item.title} {...item} />)}</div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2"><div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/50 p-3"><div><p className="text-xs font-medium text-slate-300">Navigation status</p><p className="mt-1 text-[10px] text-slate-500">GPS fix · {telemetry?.gps_fix_type || 'unknown'}</p></div>{telemetry?.gps_satellites != null && telemetry.gps_satellites >= 6 ? <Check size={17} className="text-accent" /> : <X size={17} className="text-amber-300" />}</div><div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/50 p-3"><div><p className="text-xs font-medium text-slate-300">Link quality</p><p className="mt-1 text-[10px] text-slate-500">Only shown when the autopilot reports it</p></div><span className="text-sm font-semibold text-white">{telemetry?.link_quality_pct != null ? `${telemetry.link_quality_pct.toFixed(0)}%` : '—'}</span></div></div>
    </Panel>
    <div className="mt-5 grid gap-5 lg:grid-cols-2"><Panel title="Health score trend" subtitle="Computed locally from available health checks"><TelemetryChart history={history} metric="drone_health_score" title="Health score" color="#64e4b6" unit="/100" height={220} /></Panel><Panel title="Battery trend" subtitle="Live telemetry only"><TelemetryChart history={history} metric="battery_remaining_pct" title="Remaining charge" color="#f3bd5b" unit="%" height={220} /></Panel></div>
  </>;
}
