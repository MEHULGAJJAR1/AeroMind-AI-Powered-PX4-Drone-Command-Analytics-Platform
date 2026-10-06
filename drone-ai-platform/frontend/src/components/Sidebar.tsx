import { Activity, Bell, BrainCircuit, ChevronLeft, ChevronRight, ClipboardList, Gauge, Map, MapPinned, Menu, Radio, Settings, Shield, X } from 'lucide-react';
import type { ReactNode } from 'react';
import type { Telemetry } from '../types';
import { StatusBadge } from './common';

export type PageId = 'overview' | 'live' | 'missions' | 'telemetry' | 'health' | 'analytics' | 'logs' | 'alerts' | 'settings' | 'system';

const items: { id: PageId; label: string; icon: ReactNode; section: string }[] = [
  { id: 'overview', label: 'Overview', icon: <Gauge size={17} />, section: 'OPERATIONS' },
  { id: 'live', label: 'Live flight', icon: <Radio size={17} />, section: 'OPERATIONS' },
  { id: 'missions', label: 'Mission planner', icon: <Map size={17} />, section: 'OPERATIONS' },
  { id: 'telemetry', label: 'Telemetry', icon: <Activity size={17} />, section: 'INTELLIGENCE' },
  { id: 'health', label: 'Drone health', icon: <Shield size={17} />, section: 'INTELLIGENCE' },
  { id: 'analytics', label: 'AI analytics', icon: <BrainCircuit size={17} />, section: 'INTELLIGENCE' },
  { id: 'logs', label: 'Flight logs', icon: <ClipboardList size={17} />, section: 'DATA' },
  { id: 'alerts', label: 'Alerts center', icon: <Bell size={17} />, section: 'DATA' },
  { id: 'settings', label: 'Settings', icon: <Settings size={17} />, section: 'SYSTEM' },
  { id: 'system', label: 'System status', icon: <MapPinned size={17} />, section: 'SYSTEM' },
];

export function Sidebar({ page, setPage, telemetry, open, onClose, collapsed, setCollapsed }: {
  page: PageId;
  setPage: (page: PageId) => void;
  telemetry: Telemetry | null;
  open: boolean;
  onClose: () => void;
  collapsed: boolean;
  setCollapsed: (value: boolean) => void;
}) {
  const grouped = items.reduce<Record<string, typeof items>>((acc, item) => {
    (acc[item.section] ||= []).push(item);
    return acc;
  }, {});
  return <>
    {open && <button className="fixed inset-0 z-40 bg-black/60 lg:hidden" aria-label="Close navigation" onClick={onClose} />}
    <aside className={`fixed inset-y-0 left-0 z-50 flex flex-col border-r border-slate-800 bg-[#0b121f] transition-all duration-200 lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'} ${collapsed ? 'w-[76px]' : 'w-[252px]'}`}>
      <div className={`flex h-[74px] items-center border-b border-slate-800 ${collapsed ? 'justify-center px-3' : 'justify-between px-5'}`}>
        <button onClick={() => { setPage('overview'); onClose(); }} className="flex min-w-0 items-center gap-3 text-left">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent text-slate-950 shadow-glow"><Radio size={19} strokeWidth={2.4} /></span>
          {!collapsed && <span className="min-w-0"><span className="block text-[14px] font-bold tracking-[0.08em] text-white">AEROMIND</span><span className="mt-0.5 block text-[9px] font-semibold uppercase tracking-[0.22em] text-slate-500">Drone operations</span></span>}
        </button>
        {!collapsed && <button className="icon-button lg:hidden" onClick={onClose} aria-label="Close sidebar"><X size={17} /></button>}
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-5">
        {Object.entries(grouped).map(([section, links]) => <div key={section} className="mb-6">
          {!collapsed && <p className="mb-2 px-3 text-[9px] font-bold tracking-[0.2em] text-slate-600">{section}</p>}
          <div className="space-y-1">{links.map((item) => <button key={item.id} title={collapsed ? item.label : undefined} onClick={() => { setPage(item.id); onClose(); }} className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs font-medium transition ${page === item.id ? 'bg-accent/10 text-accent shadow-[inset_2px_0_0_#64e4b6]' : 'text-slate-400 hover:bg-slate-800/70 hover:text-slate-100'} ${collapsed ? 'justify-center px-2' : ''}`}>
            <span className={page === item.id ? 'text-accent' : 'text-slate-500 group-hover:text-slate-200'}>{item.icon}</span>{!collapsed && <span>{item.label}</span>}
            {!collapsed && item.id === 'alerts' && (telemetry?.anomaly_count || 0) > 0 && <span className="ml-auto rounded-full bg-rose-400/15 px-1.5 py-0.5 text-[9px] text-rose-300">{telemetry?.anomaly_count}</span>}
          </button>)}</div>
        </div>)}
      </nav>
      <div className={`border-t border-slate-800 p-3 ${collapsed ? 'flex justify-center' : ''}`}>
        {!collapsed ? <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <div className="mb-2 flex items-center justify-between"><span className="text-[10px] font-semibold text-slate-400">VEHICLE LINK</span><span className={`h-1.5 w-1.5 rounded-full ${telemetry?.connected ? 'bg-accent shadow-[0_0_8px_#64e4b6]' : 'bg-rose-400'}`} /></div>
          <StatusBadge tone={telemetry?.source === 'mock' ? 'warning' : telemetry?.connected ? 'good' : 'critical'} dot>{telemetry?.source === 'mock' ? 'Simulated' : telemetry?.connected ? 'PX4 online' : 'Offline'}</StatusBadge>
          <p className="mt-2 truncate text-[10px] text-slate-600">{telemetry?.flight_mode || 'Waiting for link'}</p>
        </div> : <div title={telemetry?.connected ? 'Vehicle connected' : 'Vehicle offline'} className={`h-2.5 w-2.5 rounded-full ${telemetry?.connected ? 'bg-accent' : 'bg-rose-400'}`} />}
        <button className={`mt-3 hidden w-full items-center justify-center gap-2 rounded-lg py-2 text-[10px] text-slate-500 hover:bg-slate-800 hover:text-slate-200 lg:flex ${collapsed ? 'px-0' : ''}`} onClick={() => setCollapsed(!collapsed)}>{collapsed ? <ChevronRight size={14} /> : <><ChevronLeft size={14} />Collapse menu</>}</button>
      </div>
    </aside>
  </>;
}

export function MobileMenuButton({ onClick }: { onClick: () => void }) {
  return <button className="icon-button lg:hidden" aria-label="Open navigation" onClick={onClick}><Menu size={19} /></button>;
}
