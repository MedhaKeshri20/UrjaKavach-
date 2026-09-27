import { bandColor, bandLabel, type Band } from "@/lib/kavach-data";

export function RiskGauge({ score, band, size = 240 }: { score: number; band: Band; size?: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  const r = 42;
  const c = 2 * Math.PI * r;
  const dash = (clamped / 100) * c;
  const color = bandColor[band];

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient id="gaugeGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={color} />
            <stop offset="100%" stopColor="var(--cyan-glow)" />
          </linearGradient>
          <filter id="gaugeGlow">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--grid-line)" strokeWidth="6" />
        <circle
          cx="50" cy="50" r={r}
          fill="none"
          stroke="url(#gaugeGrad)"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
          filter="url(#gaugeGlow)"
          style={{ transition: "stroke-dasharray 900ms cubic-bezier(0.2,0.7,0.3,1)" }}
        />
        {/* tick marks */}
        {Array.from({ length: 40 }).map((_, i) => {
          const a = (i / 40) * 2 * Math.PI;
          const x1 = 50 + Math.cos(a) * 48;
          const y1 = 50 + Math.sin(a) * 48;
          const x2 = 50 + Math.cos(a) * 50;
          const y2 = 50 + Math.sin(a) * 50;
          return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--grid-line)" strokeWidth="0.4" />;
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="font-mono text-6xl font-semibold tracking-tighter" style={{ color }}>
          {clamped}
        </div>
        <div className="mt-1 text-[10px] font-semibold tracking-[0.3em]" style={{ color }}>
          {bandLabel[band]}
        </div>
        <div className="mt-1 text-[10px] uppercase tracking-widest text-muted-foreground">National risk</div>
      </div>
    </div>
  );
}
