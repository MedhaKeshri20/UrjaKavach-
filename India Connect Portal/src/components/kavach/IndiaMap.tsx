import { useState } from "react";
import { bandColor } from "@/lib/kavach-data";
import type { DemoCorridor, DemoRefinery } from "@/lib/demo-state";

// Highly stylized "operational theater" map. Not geographically precise —
// designed to communicate corridors → refineries at a glance.
// Coords are on a 100 x 100 viewBox.

// Real corridor ids (backend/seed/corridors.json) — updated for live-data
// use as RealWorldMap's offline fallback (spec.md Phase 7). This component
// has no other caller, so there's no demo-id usage left to preserve here.
const CHOKEPOINTS = [
  { id: "hormuz", label: "Hormuz", x: 12, y: 42 },
  { id: "atlantic", label: "Atlantic", x: 4, y: 54 },
  { id: "suez_cape", label: "Suez / Cape", x: 8, y: 26 },
  { id: "malacca", label: "Malacca", x: 88, y: 66 },
];

const INDIA_PATH =
  "M40,40 L55,38 L62,44 L64,52 L60,60 L64,68 L58,76 L52,82 L46,80 L42,72 L38,64 L36,54 L38,46 Z";

export function IndiaMap({
  corridors,
  refineries,
  onCorridor,
  activeCorridor,
}: {
  corridors: DemoCorridor[];
  refineries: DemoRefinery[];
  onCorridor?: (id: string) => void;
  activeCorridor?: string;
}) {
  const [hover, setHover] = useState<string | null>(null);

  return (
    <div className="relative w-full overflow-hidden panel grid-bg">
      <div className="absolute inset-0 pointer-events-none">
        <div
          className="absolute -top-1/2 -left-1/3 w-2/3 h-full rounded-full opacity-20 blur-3xl"
          style={{ background: "var(--gradient-primary)" }}
        />
      </div>
      <svg viewBox="0 0 100 100" className="relative w-full h-full aspect-[16/10]">
        {/* India silhouette */}
        <path
          d={INDIA_PATH}
          fill="oklch(0.22 0.05 260 / 0.6)"
          stroke="var(--cyan)"
          strokeOpacity="0.35"
          strokeWidth="0.3"
        />

        {/* Corridors */}
        {corridors.map((c) => {
          const active = activeCorridor === c.id || hover === c.id;
          const color = bandColor[c.band];
          const [x1, y1] = c.from;
          const [x2, y2] = c.to;
          const mx = (x1 + x2) / 2 + (y2 - y1) * 0.15;
          const my = (y1 + y2) / 2 - (x2 - x1) * 0.15;
          const path = `M${x1},${y1} Q${mx},${my} ${x2},${y2}`;
          return (
            <g
              key={c.id}
              onMouseEnter={() => setHover(c.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onCorridor?.(c.id)}
              style={{ cursor: "pointer" }}
            >
              <path
                d={path}
                fill="none"
                stroke={color}
                strokeOpacity={active ? 0.9 : 0.55}
                strokeWidth={active ? 0.9 : 0.5}
                strokeDasharray="1.2 0.6"
              />
              <path
                d={path}
                fill="none"
                stroke={color}
                strokeOpacity={0.15}
                strokeWidth={active ? 3 : 2}
              />
            </g>
          );
        })}

        {/* Chokepoints */}
        {CHOKEPOINTS.map((cp) => {
          const c = corridors.find((x) => x.id === cp.id);
          const color = c ? bandColor[c.band] : "var(--muted-foreground)";
          return (
            <g key={cp.id}>
              <circle cx={cp.x} cy={cp.y} r={1.4} fill={color} />
              <circle
                cx={cp.x}
                cy={cp.y}
                r={1.4}
                fill={color}
                className="animate-pulse-ring"
                style={{ transformOrigin: `${cp.x}px ${cp.y}px` }}
                opacity={0.5}
              />
              <text
                x={cp.x + 2.3}
                y={cp.y + 0.5}
                fontSize="2.2"
                fill="var(--foreground)"
                opacity="0.75"
                className="font-mono"
              >
                {cp.label}
              </text>
            </g>
          );
        })}

        {/* Refineries */}
        {refineries.map((r) => (
          <g key={r.id}>
            <rect
              x={r.pos[0] - 0.9}
              y={r.pos[1] - 0.9}
              width={1.8}
              height={1.8}
              fill="var(--cyan)"
              opacity={0.9}
            />
            <text
              x={r.pos[0] + 1.6}
              y={r.pos[1] + 0.6}
              fontSize="1.8"
              fill="var(--cyan)"
              opacity="0.9"
              className="font-mono"
            >
              {r.city}
            </text>
          </g>
        ))}
      </svg>

      {/* Legend */}
      <div className="absolute bottom-3 left-3 flex gap-3 text-[10px] font-mono uppercase tracking-widest text-muted-foreground bg-background/50 backdrop-blur-sm px-3 py-1.5 rounded-md border border-border">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full" style={{ background: "var(--alert-low)" }} />
          stable
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full" style={{ background: "var(--alert-med)" }} />
          watch
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full" style={{ background: "var(--alert-high)" }} />
          elevated
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full" style={{ background: "var(--alert-crit)" }} />
          critical
        </span>
      </div>

      <div className="absolute top-3 right-3 flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        LIVE FEED · AIS + OSINT
      </div>
    </div>
  );
}
