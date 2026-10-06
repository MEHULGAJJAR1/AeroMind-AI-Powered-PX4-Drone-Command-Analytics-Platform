import { useState } from 'react';
import { ArrowRight, Eye, EyeOff, LockKeyhole, Radio, ShieldCheck, Sparkles } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export function LoginScreen() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (mode === 'login') await login(email, password);
      else await register(email, password);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Authentication failed');
    } finally {
      setBusy(false);
    }
  };

  return <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#080d17] px-4 py-10">
    <div className="pointer-events-none absolute -left-40 top-0 h-[500px] w-[500px] rounded-full bg-emerald-400/[0.055] blur-[120px]" />
    <div className="pointer-events-none absolute -bottom-40 right-0 h-[500px] w-[500px] rounded-full bg-blue-500/[0.06] blur-[120px]" />
    <div className="relative grid w-full max-w-5xl overflow-hidden rounded-[26px] border border-slate-800 bg-[#0d1522] shadow-2xl shadow-black/40 lg:grid-cols-[1.05fr_.95fr]">
      <section className="relative hidden min-h-[620px] flex-col justify-between overflow-hidden border-r border-slate-800 bg-gradient-to-br from-[#132739] via-[#0d1b2a] to-[#0b121e] p-10 lg:flex">
        <div className="absolute -right-24 top-24 h-72 w-72 rounded-full border border-accent/10" /><div className="absolute -right-14 top-34 h-52 w-52 rounded-full border border-accent/10" /><div className="absolute right-20 top-52 h-24 w-24 rounded-full border border-accent/20" />
        <div className="relative flex items-center gap-3"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent text-slate-950"><Radio size={22} /></span><span><span className="block text-sm font-bold tracking-[0.14em] text-white">AEROMIND</span><span className="text-[9px] font-semibold uppercase tracking-[0.2em] text-slate-500">Flight intelligence platform</span></span></div>
        <div className="relative max-w-md">
          <span className="mb-5 inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/[0.07] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent"><Sparkles size={12} />PX4-aware operations</span>
          <h1 className="text-4xl font-semibold leading-[1.15] tracking-tight text-white">A clearer view of every flight.</h1>
          <p className="mt-5 text-sm leading-7 text-slate-400">Live vehicle telemetry, safe mission workflows and explainable flight-risk analytics in one operations workspace.</p>
          <div className="mt-9 space-y-4">{[['01', 'Stream telemetry', 'WebSocket updates with offline fallback'], ['02', 'Plan with confidence', 'Validate and upload PX4 missions'], ['03', 'Learn from each flight', 'History, health scores and explainable alerts']].map(([number, title, body]) => <div key={number} className="flex items-start gap-3"><span className="font-mono text-[10px] text-accent/80">{number}</span><span><span className="block text-xs font-semibold text-slate-200">{title}</span><span className="mt-0.5 block text-[11px] text-slate-500">{body}</span></span></div>)}</div>
        </div>
        <div className="relative flex items-center gap-2 text-[10px] text-slate-600"><ShieldCheck size={13} />Local-first data · Operator and admin roles · JWT protected</div>
      </section>
      <section className="flex min-h-[620px] flex-col justify-center px-6 py-10 sm:px-12">
        <div className="mb-8 lg:hidden"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-slate-950"><Radio size={20} /></span><p className="mt-3 text-sm font-bold tracking-[0.14em] text-white">AEROMIND</p></div>
        <div className="mb-8"><p className="mb-2 text-[10px] font-bold uppercase tracking-[0.2em] text-accent">Secure operator access</p><h2 className="text-2xl font-semibold text-white">{mode === 'login' ? 'Welcome back' : 'Create operator account'}</h2><p className="mt-2 text-sm text-slate-500">{mode === 'login' ? 'Sign in to access your vehicle operations.' : 'New accounts receive operator permissions.'}</p></div>
        <form onSubmit={(event) => void submit(event)} className="space-y-4">
          <div><label className="field-label" htmlFor="email">Email address</label><input id="email" className="field" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="operator@organization.com" required /></div>
          <div><label className="field-label" htmlFor="password">Password</label><div className="relative"><LockKeyhole className="pointer-events-none absolute left-3 top-3 text-slate-600" size={16} /><input id="password" className="field pl-10 pr-11" type={showPassword ? 'text' : 'password'} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={10} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={mode === 'register' ? 'At least 10 characters' : 'Enter your password'} required /><button type="button" className="icon-button absolute right-2 top-1.5" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></div>
          {error && <div role="alert" className="rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2.5 text-xs text-rose-200">{error}</div>}
          <button className="button-primary mt-2 w-full py-3" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}{!busy && <ArrowRight size={15} />}</button>
        </form>
        <p className="mt-6 text-center text-xs text-slate-500">{mode === 'login' ? 'New to AeroMind?' : 'Already registered?'} <button className="font-semibold text-accent hover:text-emerald-200" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}>{mode === 'login' ? 'Create an account' : 'Sign in'}</button></p>
        <div className="mt-8 rounded-xl border border-slate-800 bg-slate-900/40 p-3 text-[10px] leading-5 text-slate-600"><ShieldCheck size={13} className="mr-1.5 inline text-slate-500" />No demo credentials are configured. Register an operator or sign in with an administrator provisioned by your deployment.</div>
      </section>
    </div>
  </main>;
}
