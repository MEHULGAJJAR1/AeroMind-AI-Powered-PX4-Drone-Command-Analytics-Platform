export function StatusRing({ score, label, tone = 'mint', size = 'lg' }: { score: number; label: string; tone?: 'mint' | 'blue' | 'amber' | 'rose'; size?: 'sm' | 'lg' }) {
  const color = tone === 'mint' ? '#64e4b6' : tone === 'blue' ? '#67a4ff' : tone === 'amber' ? '#fbbf24' : '#fb7185';
  const dimension = size === 'lg' ? 'h-32 w-32' : 'h-24 w-24';
  const textSize = size === 'lg' ? 'text-3xl' : 'text-2xl';
  const value = Math.max(0, Math.min(100, score || 0));
  return <div className={`relative flex ${dimension} shrink-0 items-center justify-center rounded-full`} style={{ background: `conic-gradient(${color} ${value * 3.6}deg, #263246 ${value * 3.6}deg)` }}>
    <div className="absolute inset-[7px] rounded-full bg-[#101827]" />
    <div className="relative text-center"><div className={`${textSize} font-semibold tabular-nums text-white`}>{Math.round(value)}</div><div className="mt-0.5 text-[9px] font-semibold uppercase tracking-[0.15em] text-slate-500">{label}</div></div>
  </div>;
}
