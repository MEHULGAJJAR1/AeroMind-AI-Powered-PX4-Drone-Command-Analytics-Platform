import { useEffect, useState } from 'react';
import { Check, Copy, LockKeyhole, Radio, Save, ShieldCheck } from 'lucide-react';
import type { Telemetry, User } from '../types';
import { PageHeading, Panel, StatusBadge } from '../components/common';
import { api } from '../services/api';

const PREF_KEY = 'aeromind.preferences';
type Preferences = { coordinatePrecision: number; alertSound: boolean; compactTables: boolean };
const defaults: Preferences = { coordinatePrecision: 5, alertSound: false, compactTables: false };

export function SettingsPage({ telemetry, user }: { telemetry: Telemetry | null; user: User | null }) {
  const [prefs, setPrefs] = useState<Preferences>(() => {
    try { return { ...defaults, ...JSON.parse(window.localStorage.getItem(PREF_KEY) || '{}') }; } catch { return defaults; }
  });
  const [saved, setSaved] = useState(false);
  const [status, setStatus] = useState<{ configured_mode: string; control_enabled: boolean } | null>(null);
  useEffect(() => { api.droneStatus().then(setStatus).catch(() => undefined); }, []);
  const save = () => {
    window.localStorage.setItem(PREF_KEY, JSON.stringify(prefs));
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  };
  const copyEndpoint = async () => {
    await navigator.clipboard?.writeText(`${window.location.origin}/ws/telemetry`);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  };
  return <>
    <PageHeading eyebrow="Workspace configuration" title="Settings" description="Manage this browser's display preferences and review deployment-controlled connection settings." action={<StatusBadge tone="info"><LockKeyhole size={12} />Environment managed</StatusBadge>} />
    <div className="grid gap-5 xl:grid-cols-[1.15fr_.85fr]">
      <div className="space-y-5">
        <Panel title="Display preferences" subtitle="Saved locally in this browser profile; does not alter PX4 parameters.">
          <div className="space-y-5">
            <label className="flex items-center justify-between gap-4"><span><span className="block text-xs font-semibold text-slate-200">Coordinate precision</span><span className="mt-1 block text-[10px] text-slate-500">Number of decimal places shown in coordinate readouts.</span></span><select className="field !w-28" value={prefs.coordinatePrecision} onChange={(event) => setPrefs({ ...prefs, coordinatePrecision: Number(event.target.value) })}><option value={4}>4 places</option><option value={5}>5 places</option><option value={6}>6 places</option></select></label>
            <label className="flex items-center justify-between gap-4"><span><span className="block text-xs font-semibold text-slate-200">Alert sound</span><span className="mt-1 block text-[10px] text-slate-500">Preference stored for this browser. Audio playback is not enabled in this build.</span></span><input type="checkbox" checked={prefs.alertSound} onChange={(event) => setPrefs({ ...prefs, alertSound: event.target.checked })} className="h-4 w-4 accent-emerald-400" /></label>
            <label className="flex items-center justify-between gap-4"><span><span className="block text-xs font-semibold text-slate-200">Compact tables</span><span className="mt-1 block text-[10px] text-slate-500">Density preference for exported or future table views.</span></span><input type="checkbox" checked={prefs.compactTables} onChange={(event) => setPrefs({ ...prefs, compactTables: event.target.checked })} className="h-4 w-4 accent-emerald-400" /></label>
            <div className="flex justify-end"><button className="button-primary" onClick={save}><Save size={14} />{saved ? 'Saved' : 'Save preferences'}{saved && <Check size={14} />}</button></div>
          </div>
        </Panel>
        <Panel title="Connection configuration" subtitle="Set these values in the backend environment and restart the service.">
          <div className="space-y-3">{[
            ['Telemetry mode', status?.configured_mode || telemetry?.source || 'loading'],
            ['MAVLink endpoint', 'PX4_SYSTEM_ADDRESS · backend environment'],
            ['MAVSDK server', 'MAVSDK_SERVER_ADDRESS / MAVSDK_SERVER_PORT'],
            ['Database', 'DATABASE_URL · SQLite or PostgreSQL'],
            ['CORS allowlist', 'CORS_ORIGINS · comma-separated origins'],
          ].map(([label, value]) => <div key={label} className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/70 pb-3 last:border-0 last:pb-0"><span className="text-xs text-slate-400">{label}</span><code className="rounded bg-slate-900 px-2 py-1 text-[10px] text-slate-300">{value}</code></div>)}</div>
          <button className="button-secondary mt-4" onClick={() => void copyEndpoint()}><Copy size={13} />{saved ? 'Copied' : 'Copy WebSocket base URL'}</button>
        </Panel>
      </div>
      <div className="space-y-5">
        <Panel title="Account" subtitle="JWT-authenticated operator profile">
          <div className="flex items-center gap-3"><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent/10 text-sm font-bold text-accent">{user?.email?.slice(0, 1).toUpperCase() || 'A'}</div><div className="min-w-0"><p className="truncate text-sm font-semibold text-white">{user?.email}</p><p className="mt-1 text-[10px] text-slate-500">Role-based access</p></div><StatusBadge tone={user?.role === 'admin' ? 'info' : 'good'}>{user?.role || 'operator'}</StatusBadge></div>
          <div className="mt-5 rounded-xl border border-slate-800 bg-slate-900/40 p-3 text-[11px] leading-5 text-slate-500"><ShieldCheck size={13} className="mr-1.5 inline text-accent" />Access tokens are stored in this browser and attached to protected API requests. Sign out to remove the local token.</div>
        </Panel>
        <Panel title="Safety envelope" subtitle="Backend-enforced defaults; verify local operating rules">
          <div className="space-y-3">{[['Mission maximum altitude', '120 m AGL default'], ['Mission waypoint limit', '100 default'], ['Command permissions', 'Operator / admin'], ['Arming gate', 'Connected + healthy estimator + home position'], ['Disarm gate', 'Ground only; blocked while airborne']].map(([key, value]) => <div key={key} className="flex items-start justify-between gap-4 border-b border-slate-800/70 pb-2.5 last:border-0 last:pb-0"><span className="text-[11px] text-slate-500">{key}</span><span className="max-w-[60%] text-right text-[10px] text-slate-300">{value}</span></div>)}</div>
        </Panel>
        <Panel title="PX4 control" subtitle="AeroMind is a companion application, not a flight controller."><div className="flex items-start gap-2 rounded-lg border border-amber-400/15 bg-amber-400/[0.045] p-3 text-[10px] leading-5 text-amber-100/70"><Radio size={14} className="mt-0.5 shrink-0 text-amber-300" />PX4 parameters, failsafes, geofence and vehicle-specific limits remain authoritative. Never rely on application limits as a replacement for PX4 configuration or a safety case.</div></Panel>
      </div>
    </div>
  </>;
}
