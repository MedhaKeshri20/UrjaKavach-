// One WebSocket-backed hook holding the shared, real RiskState. Every live
// panel reads from it, so a single injected signal animates the whole app at
// once (the cascade money-shot — see PLAN.md's "one signal, one sweep"
// standing rule). Hydrates over REST first, auto-reconnects.
//
// Deliberately does NOT fall back to demo-state.ts on disconnect (spec.md §1
// non-negotiable: never render fabricated data with the same visual
// treatment as live data). When there's no real snapshot yet — or the
// connection drops before one ever arrived — `state` stays `null` and
// callers must render their own honest empty/offline state, not silently
// substitute mock numbers. Once a real snapshot has been received, it's kept
// on screen (clearly marked via `status === "offline"`) rather than being
// replaced by anything invented.

import { useEffect, useRef, useState } from "react";
import type { RiskState } from "@/types/contract";

export type ConnStatus = "connecting" | "live" | "offline";

const API_BASE = import.meta.env.VITE_API_URL || "/api";

function wsUrl(): string {
  const override = import.meta.env.VITE_WS_URL;
  if (override) return override;
  if (typeof window === "undefined") return "ws://localhost:8000/ws/state";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  // Default to the backend dev port; override with VITE_WS_URL in prod.
  return `${proto}//${window.location.hostname}:8000/ws/state`;
}

export function useRiskState() {
  const [state, setState] = useState<RiskState | null>(null);
  const [status, setStatus] = useState<ConnStatus>("connecting");
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedRef = useRef(false);

  useEffect(() => {
    closedRef.current = false;

    // REST hydrate so the UI has the current real state before the socket
    // even opens (and stays correct if the WS never connects at all).
    fetch(`${API_BASE}/state`, { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<RiskState>) : null))
      .then((s) => s && setState(s))
      .catch(() => {
        // Leave `state` as-is (null on first load). No mock substitute.
      });

    const connect = () => {
      let socket: WebSocket;
      try {
        socket = new WebSocket(wsUrl());
      } catch {
        setStatus("offline");
        scheduleRetry();
        return;
      }
      socketRef.current = socket;
      setStatus("connecting");

      socket.onopen = () => setStatus("live");
      socket.onmessage = (event) => {
        try {
          // Enforce the contract shape on incoming frames — the backend
          // always pushes a full snapshot, never a diff (contract.py).
          setState(JSON.parse(event.data) as RiskState);
        } catch (error) {
          console.error("Contract parse error on WS frame:", error);
        }
      };
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        setStatus("offline");
        // Keep whatever the last good snapshot was (possibly still null) —
        // never substitute a mock. Callers render the "offline" status
        // themselves (e.g. a "last known state — reconnecting" badge).
        if (!closedRef.current) scheduleRetry();
      };
    };

    const scheduleRetry = () => {
      if (closedRef.current) return;
      retryRef.current = setTimeout(connect, 1500);
    };

    connect();

    return () => {
      closedRef.current = true;
      if (retryRef.current) clearTimeout(retryRef.current);
      socketRef.current?.close();
    };
  }, []);

  return { state, status };
}
