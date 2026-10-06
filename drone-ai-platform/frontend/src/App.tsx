import { lazy, Suspense, useState } from 'react';
import { Bell, LogOut, Radio, RefreshCw, UserRound } from 'lucide-react';
import { useAuth } from './context/AuthContext';
import { useTelemetry } from './hooks/useTelemetry';
import { LoginScreen } from './components/LoginScreen';
import { MobileMenuButton, PageId, Sidebar } from './components/Sidebar';
import { StatusBadge } from './components/common';

const OverviewPage = lazy(() => import('./pages/OverviewPage').then((module) => ({ default: module.OverviewPage })));
const LiveFlightPage = lazy(() => import('./pages/LiveFlightPage').then((module) => ({ default: module.LiveFlightPage })));
const MissionPlannerPage = lazy(() => import('./pages/MissionPlannerPage').then((module) => ({ default: module.MissionPlannerPage })));
const TelemetryPage = lazy(() => import('./pages/TelemetryPage').then((module) => ({ default: module.TelemetryPage })));
const DroneHealthPage = lazy(() => import('./pages/DroneHealthPage').then((module) => ({ default: module.DroneHealthPage })));
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage').then((module) => ({ default: module.AnalyticsPage })));
const FlightLogsPage = lazy(() => import('./pages/FlightLogsPage').then((module) => ({ default: module.FlightLogsPage })));
const AlertsPage = lazy(() => import('./pages/AlertsPage').then((module) => ({ default: module.AlertsPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((module) => ({ default: module.SettingsPage })));
const SystemStatusPage = lazy(() => import('./pages/SystemStatusPage').then((module) => ({ default: module.SystemStatusPage })));

const titles: Record<PageId, string> = {
  overview: 'Overview', live: 'Live flight', missions: 'Mission planner', telemetry: 'Telemetry', health: 'Drone health',
  analytics: 'AI analytics', logs: 'Flight logs', alerts: 'Alerts center', settings: 'Settings', system: 'System status',
};

export function App() {
  const { user, ready, logout } = useAuth();
  const [page, setPage] = useState<PageId>('overview');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const { telemetry, history, socketConnected, error, refresh } = useTelemetry(Boolean(user));

  if (!ready) return <div className="flex min-h-screen items-center justify-center bg-ink text-xs text-slate-500"><span className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-slate-700 border-t-accent" />Checking secure session…</div>;
  if (!user) return <LoginScreen />;

  const renderPage = () => {
    switch (page) {
      case 'overview': return <OverviewPage telemetry={telemetry} history={history} socketConnected={socketConnected} onNavigate={setPage} />;
      case 'live': return <LiveFlightPage telemetry={telemetry} history={history} socketConnected={socketConnected} onRefresh={refresh} />;
      case 'missions': return <MissionPlannerPage telemetry={telemetry} />;
      case 'telemetry': return <TelemetryPage telemetry={telemetry} history={history} socketConnected={socketConnected} />;
      case 'health': return <DroneHealthPage telemetry={telemetry} history={history} />;
      case 'analytics': return <AnalyticsPage telemetry={telemetry} history={history} />;
      case 'logs': return <FlightLogsPage />;
      case 'alerts': return <AlertsPage />;
      case 'settings': return <SettingsPage telemetry={telemetry} user={user} />;
      case 'system': return <SystemStatusPage telemetry={telemetry} socketConnected={socketConnected} />;
    }
  };

  return <div className="min-h-screen bg-ink">
    <Sidebar page={page} setPage={setPage} telemetry={telemetry} open={mobileOpen} onClose={() => setMobileOpen(false)} collapsed={collapsed} setCollapsed={setCollapsed} />
    <div className={`min-h-screen transition-all duration-200 ${collapsed ? 'lg:pl-[76px]' : 'lg:pl-[252px]'}`}>
      <header className="sticky top-0 z-30 flex h-[74px] items-center justify-between border-b border-slate-800/90 bg-[#080d17]/90 px-4 backdrop-blur-xl md:px-7">
        <div className="flex min-w-0 items-center gap-3"><MobileMenuButton onClick={() => setMobileOpen(true)} /><div className="min-w-0"><p className="truncate text-[10px] font-semibold uppercase tracking-[0.17em] text-slate-500">AeroMind <span className="mx-1 text-slate-700">/</span> {titles[page]}</p><div className="mt-1 flex items-center gap-2"><h2 className="truncate text-sm font-semibold text-white">{telemetry?.source === 'mock' ? 'Simulation workspace' : 'Flight operations'}</h2>{telemetry?.source === 'mock' && <span className="rounded bg-amber-400/10 px-1.5 py-0.5 text-[8px] font-bold tracking-wider text-amber-300">DEMO</span>}</div></div></div>
        <div className="flex items-center gap-2 sm:gap-4">
          <div className="hidden items-center gap-2 sm:flex"><span className={`h-1.5 w-1.5 rounded-full ${socketConnected ? 'bg-accent shadow-[0_0_8px_#64e4b6]' : 'bg-amber-300'}`} /><span className="text-[10px] text-slate-500">{socketConnected ? 'Stream live' : telemetry?.connected ? 'API fallback' : 'Link offline'}</span></div>
          <StatusBadge tone={telemetry?.source === 'mock' ? 'warning' : telemetry?.connected ? 'good' : 'critical'} dot>{telemetry?.source === 'mock' ? 'Mock' : telemetry?.connected ? 'PX4 online' : 'Offline'}</StatusBadge>
          <div className="hidden h-7 w-px bg-slate-800 sm:block" />
          <div className="hidden max-w-40 items-center gap-2 md:flex"><span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-800 text-slate-300"><UserRound size={14} /></span><span className="truncate text-[10px] text-slate-400">{user.email}</span></div>
          <button onClick={() => void refresh()} className="icon-button hidden sm:inline-flex" aria-label="Refresh telemetry"><RefreshCw size={15} /></button>
          <button className="icon-button relative" aria-label="Open alerts" onClick={() => setPage('alerts')}><Bell size={16} />{(telemetry?.anomaly_count || 0) > 0 && <span className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-rose-400" />}</button>
          <button className="icon-button" onClick={logout} title="Sign out" aria-label="Sign out"><LogOut size={16} /></button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1600px] px-4 pb-10 pt-6 md:px-7 md:pt-8">
        {error && <div role="status" className="mb-4 flex items-center gap-2 rounded-lg border border-amber-400/15 bg-amber-400/[0.045] px-3 py-2 text-[11px] text-amber-200/80"><Radio size={13} />API telemetry unavailable: {error}. Retrying automatically.</div>}
        <Suspense fallback={<div className="panel flex min-h-48 items-center justify-center gap-2 text-xs text-slate-500"><span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-700 border-t-accent" />Loading workspace…</div>}>{renderPage()}</Suspense>
        <footer className="mt-10 flex flex-col justify-between gap-2 border-t border-slate-800/70 pt-4 text-[9px] text-slate-600 sm:flex-row"><span>AEROMIND · PX4 companion operations platform</span><span>Flight-control authority remains with PX4 and the operator.</span></footer>
      </main>
    </div>
  </div>;
}
