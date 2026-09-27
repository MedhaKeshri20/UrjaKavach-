// Session-observed rolling buffer of Reserve.days_cover, built purely from
// real WS snapshots as they arrive via useRiskState(). This is deliberately
// NOT a historical time series — the backend has no days-of-cover history
// endpoint (spec.md §2 decision #5) — so it starts empty on every page load
// and only grows as real signals land during this browser session. Any UI
// that renders this must label it "session-observed", never as 30 days of
// history the way the old demo-state.ts's fabricated spr_series implied.

import { useEffect, useRef, useState } from "react";
import type { RiskState } from "@/types/contract";

export interface ReserveSample {
  ts: string;
  days_cover: number;
}

const MAX_SAMPLES = 60;

export function useReserveHistory(state: RiskState | null): ReserveSample[] {
  const [samples, setSamples] = useState<ReserveSample[]>([]);
  const lastTsRef = useRef<string | null>(null);

  useEffect(() => {
    if (!state?.reserve || state.updated_at === lastTsRef.current) return;
    lastTsRef.current = state.updated_at;
    const reserve = state.reserve;
    setSamples((prev) =>
      [...prev, { ts: state.updated_at, days_cover: reserve.days_cover }].slice(-MAX_SAMPLES),
    );
  }, [state]);

  return samples;
}
