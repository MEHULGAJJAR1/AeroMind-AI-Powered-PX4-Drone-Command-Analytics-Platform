import { useState } from 'react';
import { Anchor, ArrowDownToLine, ArrowUpFromLine, LocateFixed, PlaneTakeoff, ShieldCheck, Zap } from 'lucide-react';
import { api } from '../services/api';
import type { Telemetry } from '../types';
import { ConfirmDialog } from './ConfirmDialog';
import { StatusBadge } from './common';

type SupportedMode = 'HOLD' | 'LAND' | 'RETURN_TO_LAUNCH';
type ControlAction = { command: string; label: string; icon?: React.ReactNode; danger: boolean; hint: string; mode?: SupportedMode };

const actions: ControlAction[] = [
  { command: 'arm', label: 'Arm vehicle', icon: <Zap size={16} />, danger: false, hint: 'Run preflight checks and arm PX4.' },
  { command: 'takeoff', label: 'Take off', icon: <PlaneTakeoff size={16} />, danger: false, hint: 'Climb to the configured 5 m takeoff altitude.' },
  { command: 'hold', label: 'Hold position', icon: <Anchor size={16} />, danger: false, hint: 'Command PX4 to hold its current position.' },
  { command: 'rtl', label: 'Return to launch', icon: <LocateFixed size={16} />, danger: true, hint: 'Return to the configured PX4 home position.' },
  { command: 'land', label: 'Land', icon: <ArrowDownToLine size={16} />, danger: true, hint: 'Command PX4 to land at its current location.' },
  { command: 'disarm', label: 'Disarm', icon: <ArrowUpFromLine size={16} />, danger: true, hint: 'Disarm is rejected by the backend while airborne.' },
];

export function FlightControls({ telemetry, onRefresh }: { telemetry: Telemetry | null; onRefresh?: () => void }) {
  const [pending, setPending] = useState<ControlAction | null>(null);
  const [selectedMode, setSelectedMode] = useState<SupportedMode>('HOLD');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const canControl = telemetry?.source === 'px4' && telemetry.connected;

  const confirm = async () => {
    if (!pending) return;
    setBusy(true);
    setMessage(null);
    try {
      const extra = pending.command === 'takeoff' ? { takeoff_altitude_m: 5 } : pending.mode ? { mode: pending.mode } : {};
      const result = await api.command(pending.command, extra);
      setMessage({ text: result.message, error: false });
      onRefresh?.();
    } catch (failure) {
      setMessage({ text: failure instanceof Error ? failure.message : 'Command failed', error: true });
    } finally {
      setBusy(false);
      setPending(null);
    }
  };

  return <div>
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <div><h3 className="text-sm font-semibold text-white">Vehicle controls</h3><p className="mt-1 text-[11px] text-slate-500">Operator commands are validated again by the API.</p></div>
      <StatusBadge tone={canControl ? 'good' : 'warning'} dot>{canControl ? 'PX4 control enabled' : 'Controls locked'}</StatusBadge>
    </div>
    {!canControl && <div className="mb-4 rounded-xl border border-amber-400/15 bg-amber-400/[0.06] p-3 text-xs leading-5 text-amber-200/80"><ShieldCheck size={14} className="mr-1.5 inline" />Commands are disabled in simulated, offline, or disconnected mode. Connect a real PX4 vehicle to enable control.</div>}
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {actions.map((action) => <button key={action.command} disabled={!canControl || busy} onClick={() => setPending(action)} className={`flex min-h-[76px] flex-col items-start justify-between rounded-xl border px-3 py-3 text-left transition ${action.danger ? 'border-rose-400/15 bg-rose-400/[0.045] text-rose-200 hover:border-rose-400/35 hover:bg-rose-400/10' : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-accent/35 hover:bg-accent/[0.06]'}`}>
        <span className={action.danger ? 'text-rose-300' : 'text-accent'}>{action.icon}</span>
        <span className="text-[11px] font-semibold">{action.label}</span>
      </button>)}
    </div>
    <div className="mt-3 flex flex-wrap items-end gap-2 rounded-xl border border-slate-800 bg-slate-900/35 p-3">
      <label className="min-w-0 flex-1"><span className="field-label">Supported flight mode</span><select className="field !py-2.5" disabled={!canControl || busy} value={selectedMode} onChange={(event) => setSelectedMode(event.target.value as SupportedMode)}><option value="HOLD">Hold position</option><option value="RETURN_TO_LAUNCH">Return to launch</option><option value="LAND">Land</option></select></label>
      <button className={selectedMode === 'HOLD' ? 'button-secondary' : 'button-danger'} disabled={!canControl || busy} onClick={() => setPending({ command: 'set_mode', mode: selectedMode, label: `Set ${selectedMode.replaceAll('_', ' ').toLowerCase()} mode`, danger: selectedMode !== 'HOLD', hint: `Request the PX4 ${selectedMode.replaceAll('_', ' ')} mode.` })}>Set mode</button>
    </div>
    {message && <p role="status" className={`mt-3 rounded-lg px-3 py-2 text-xs ${message.error ? 'bg-rose-400/10 text-rose-200' : 'bg-emerald-400/10 text-emerald-200'}`}>{message.text}</p>}
    {pending && <ConfirmDialog title={`Confirm ${pending.label.toLowerCase()}`} message={`${pending.hint} This request is sent to PX4 only after confirmation, then checked against the current vehicle state.`} confirmLabel={pending.label} busy={busy} onCancel={() => setPending(null)} onConfirm={() => void confirm()} />}
  </div>;
}
