import { AlertTriangle, X } from 'lucide-react';

export function ConfirmDialog({ title, message, confirmLabel = 'Confirm command', busy = false, onCancel, onConfirm }: {
  title: string;
  message: string;
  confirmLabel?: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}>
    <div role="dialog" aria-modal="true" aria-labelledby="confirm-title" className="w-full max-w-md rounded-2xl border border-slate-700 bg-[#101827] p-6 shadow-2xl shadow-black/40">
      <div className="mb-5 flex items-start justify-between">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-400/10 text-amber-300"><AlertTriangle size={21} /></div>
        <button className="icon-button" aria-label="Close confirmation" onClick={onCancel}><X size={18} /></button>
      </div>
      <h2 id="confirm-title" className="text-lg font-semibold text-white">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-slate-400">{message}</p>
      <div className="mt-6 flex justify-end gap-2">
        <button className="button-secondary" disabled={busy} onClick={onCancel}>Cancel</button>
        <button className="button-danger" disabled={busy} onClick={onConfirm}>{busy ? 'Sending…' : confirmLabel}</button>
      </div>
    </div>
  </div>;
}
