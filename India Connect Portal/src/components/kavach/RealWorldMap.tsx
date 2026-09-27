import { useEffect, useRef, useState } from "react";
import { bandColor, bandOf, MAP_LOCATIONS, type Band } from "@/lib/kavach-data";
import { IndiaMap } from "@/components/kavach/IndiaMap";
import type { DemoCorridor, DemoRefinery } from "@/lib/demo-state";
import type { GeoStateResponse } from "@/lib/api";
import type { RiskState } from "@/types/contract";

// Minimal local shape for the pieces of the Google Maps JS API this file
// actually calls — no @types/google.maps package is installed (the API is
// loaded dynamically via <script>, not imported), so this stands in for it
// rather than reaching for `any` throughout the file.
interface GMapOverlay {
  setMap(map: unknown): void;
}
interface GMarker extends GMapOverlay {
  addListener(event: string, handler: () => void): void;
  setIcon(icon: Record<string, unknown>): void;
  setPosition(pos: { lat: number; lng: number }): void;
}
interface GPolyline extends GMapOverlay {
  addListener(event: string, handler: () => void): void;
}
interface GInfoWindow {
  open(opts: { map: unknown; anchor: GMarker }): void;
  close(): void;
  setContent(html: string): void;
}
interface GMapsNamespace {
  Map: new (el: HTMLElement, opts: Record<string, unknown>) => unknown;
  Marker: new (opts: Record<string, unknown>) => GMarker;
  Polyline: new (opts: Record<string, unknown>) => GPolyline;
  InfoWindow: new (opts: Record<string, unknown>) => GInfoWindow;
  SymbolPath: { CIRCLE: unknown };
}

declare global {
  interface Window {
    // The one deliberate boundary `any`: a dynamically <script>-loaded
    // third-party global with no local type package installed. Narrowed to
    // GMapsNamespace at every use site below (`const g: GMapsNamespace =
    // window.google.maps`).
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    google: any;
    __kavachInitMap?: () => void;
  }
}

let mapsLoader: Promise<void> | null = null;
function loadGoogleMaps(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("SSR"));
  if (window.google?.maps) return Promise.resolve();
  if (mapsLoader) return mapsLoader;

  const key = import.meta.env.VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_BROWSER_KEY;
  const channel = import.meta.env.VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_TRACKING_ID;
  if (!key) return Promise.reject(new Error("Missing Google Maps browser key"));

  mapsLoader = new Promise<void>((resolve, reject) => {
    window.__kavachInitMap = () => resolve();
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${key}&loading=async&callback=__kavachInitMap${channel ? `&channel=${channel}` : ""}`;
    s.async = true;
    s.defer = true;
    s.onerror = () => reject(new Error("Failed to load Google Maps"));
    document.head.appendChild(s);
  });
  return mapsLoader;
}

// Dark "command center" map style
const DARK_STYLE = [
  { elementType: "geometry", stylers: [{ color: "#0f1626" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0a0e1a" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#7a8ba8" }] },
  { featureType: "administrative", elementType: "geometry", stylers: [{ color: "#1f2a44" }] },
  {
    featureType: "administrative.country",
    elementType: "geometry.stroke",
    stylers: [{ color: "#3a4a6a" }],
  },
  {
    featureType: "administrative.locality",
    elementType: "labels.text.fill",
    stylers: [{ color: "#9fb0cc" }],
  },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "road", stylers: [{ visibility: "off" }] },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
  { featureType: "landscape", elementType: "geometry", stylers: [{ color: "#152036" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#050a18" }] },
  { featureType: "water", elementType: "labels.text.fill", stylers: [{ color: "#4a6a9c" }] },
];

// Muted grey for a corridor with no live score yet — distinct from "low"
// (green) so "no data" is never visually presented as "stable".
const UNSCORED_COLOR = "#5b6b8c";

function bandHex(band: Band | null): string {
  if (!band) return UNSCORED_COLOR;
  switch (band) {
    case "critical":
      return "#e94560";
    case "high":
      return "#ff8a3c";
    case "medium":
      return "#f0c04a";
    default:
      return "#4ade80";
  }
}

const TANKER_STEP_MS = 2000;
const PULSE_INTERVAL_MS = 600;

function tankerIcon(g: GMapsNamespace, isDark: boolean, pulsed: boolean) {
  return {
    path: g.SymbolPath.CIRCLE,
    scale: isDark && pulsed ? 7 : isDark ? 5.5 : 4,
    fillColor: isDark ? "#e94560" : "#7fdcff",
    fillOpacity: isDark ? (pulsed ? 1 : 0.8) : 0.85,
    strokeColor: isDark ? "#ffffff" : "#0a0e1a",
    strokeWeight: isDark ? 2 : 1,
  };
}

function refineryIcon(affected: boolean, pulsed: boolean) {
  return {
    path: "M 0,-8 8,0 0,8 -8,0 z",
    fillColor: affected ? "#e94560" : "#7fdcff",
    fillOpacity: affected ? (pulsed ? 1 : 0.8) : 0.95,
    strokeColor: "#0a0e1a",
    strokeWeight: 1.5,
    scale: affected && pulsed ? 1.35 : 1,
  };
}

// Adapts live corridor/refinery config into IndiaMap's demo-shaped props
// (spec.md Phase 7 decision #1: IndiaMap.tsx is kept as-is, wired in as the
// offline fallback rather than rebuilt). IndiaMap doesn't render
// `confidence`/`headlines` at all, so those are left as harmless empty
// placeholders, never presented to the user.
function toIndiaMapData(
  geoConfig: GeoStateResponse | null,
  corridorRisk: RiskState["corridor_risk"] | undefined,
): { corridors: DemoCorridor[]; refineries: DemoRefinery[] } {
  const locations = MAP_LOCATIONS as Record<string, [number, number]>;
  const corridors: DemoCorridor[] = (geoConfig?.corridors ?? []).map((c) => {
    const live = corridorRisk?.[c.id];
    const score = live?.score ?? 0;
    return {
      id: c.id,
      name: c.name,
      from: locations[c.id] ?? [50, 50],
      to: locations.jamnagar,
      score,
      band: live ? bandOf(score) : "low",
      confidence: 0,
      headlines: [],
    };
  });
  const refineries: DemoRefinery[] = (geoConfig?.refineries ?? []).map((r) => ({
    id: r.id,
    name: r.name,
    city: r.name,
    pos: locations[r.id] ?? [50, 50],
    capacity_kbd: Math.round(r.capacity_bpd / 1000),
    grade: "mixed",
    stress_pct: 0,
  }));
  return { corridors, refineries };
}

export function RealWorldMap({
  activeCorridor,
  onSelectCorridor,
  corridorRisk,
  geo,
  geoConfig,
}: {
  activeCorridor?: string;
  onSelectCorridor?: (id: string) => void;
  corridorRisk?: RiskState["corridor_risk"];
  geo?: RiskState["geo"] | null;
  geoConfig: GeoStateResponse | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<unknown>(null);
  const corridorOverlaysRef = useRef<GMapOverlay[]>([]);
  const refineryMarkersRef = useRef<Record<string, GMarker>>({});
  const tankerMarkersRef = useRef<Record<string, GMarker>>({});
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errMsg, setErrMsg] = useState<string>("");
  const [stepIndex, setStepIndex] = useState(0);
  const [pulseOn, setPulseOn] = useState(false);

  const darkTankerIds = new Set(geo?.dark_tanker_ids ?? []);
  const affectedRefineryIds = new Set(geo?.affected_refinery_ids ?? []);

  useEffect(() => {
    let cancelled = false;
    loadGoogleMaps()
      .then(() => {
        if (cancelled || !containerRef.current) return;
        const g: GMapsNamespace = window.google.maps;
        const map = new g.Map(containerRef.current, {
          center: { lat: 17, lng: 68 },
          zoom: 4,
          disableDefaultUI: true,
          zoomControl: true,
          gestureHandling: "greedy",
          backgroundColor: "#05070d",
          styles: DARK_STYLE,
          restriction: {
            latLngBounds: { north: 45, south: -15, east: 115, west: 25 },
            strictBounds: false,
          },
        });
        mapRef.current = map;
        setStatus("ready");
      })
      .catch((e) => {
        console.error(e);
        setErrMsg(e.message || "Map failed to load");
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Corridor polylines — real geometry from /geo/state, colored by live
  // corridor_risk (grey when a corridor has no live score yet).
  useEffect(() => {
    if (status !== "ready" || !mapRef.current || !geoConfig) return;
    const g: GMapsNamespace = window.google.maps;
    const map = mapRef.current;

    corridorOverlaysRef.current.forEach((o) => o.setMap(null));
    corridorOverlaysRef.current = [];

    for (const c of geoConfig.corridors) {
      const coords = c.geometry?.coordinates ?? [];
      if (coords.length < 2) continue;
      const path = coords.map(([lng, lat]) => ({ lat, lng }));
      const live = corridorRisk?.[c.id];
      const isActive = c.id === activeCorridor;
      const color = bandHex(live ? bandOf(live.score) : null);

      const glow = new g.Polyline({
        path,
        geodesic: true,
        strokeColor: color,
        strokeOpacity: isActive ? 0.35 : 0.18,
        strokeWeight: isActive ? 14 : 8,
        map,
        clickable: false,
      });
      const line = new g.Polyline({
        path,
        geodesic: true,
        strokeColor: color,
        strokeOpacity: isActive ? 1 : 0.85,
        strokeWeight: isActive ? 4 : 2.5,
        icons: [
          {
            icon: { path: "M 0,-1 0,1", strokeOpacity: 1, strokeWeight: 2, scale: 3 },
            offset: "0",
            repeat: "18px",
          },
        ],
        map,
      });
      line.addListener("click", () => onSelectCorridor?.(c.id));
      corridorOverlaysRef.current.push(glow, line);

      const start = path[0];
      const chokeMarker = new g.Marker({
        position: start,
        map,
        title: c.name,
        icon: {
          path: g.SymbolPath.CIRCLE,
          scale: isActive ? 10 : 7,
          fillColor: color,
          fillOpacity: 0.9,
          strokeColor: "#ffffff",
          strokeWeight: 1.5,
        },
      });
      chokeMarker.addListener("click", () => onSelectCorridor?.(c.id));

      const info = new g.InfoWindow({
        content: live
          ? `
          <div style="font-family:'JetBrains Mono',monospace;color:#0f172a;min-width:180px;">
            <div style="font-weight:700;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;">${c.name}</div>
            <div style="margin-top:4px;font-size:11px;">Score: <b style="color:${color}">${live.score}</b> · ${bandOf(live.score).toUpperCase()}</div>
            <div style="margin-top:2px;font-size:11px;">Confidence: ${live.confidence.toUpperCase()}</div>
          </div>`
          : `
          <div style="font-family:'JetBrains Mono',monospace;color:#0f172a;min-width:180px;">
            <div style="font-weight:700;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;">${c.name}</div>
            <div style="margin-top:4px;font-size:11px;font-style:italic;">No live scoring yet</div>
          </div>`,
      });
      chokeMarker.addListener("mouseover", () => info.open({ map, anchor: chokeMarker }));
      chokeMarker.addListener("mouseout", () => info.close());
      corridorOverlaysRef.current.push(chokeMarker);
    }
  }, [status, activeCorridor, onSelectCorridor, corridorRisk, geoConfig]);

  // Refinery markers — created once per geoConfig load; icon (affected /
  // pulsing) is updated by a separate effect so a signal doesn't recreate
  // every marker on the map.
  useEffect(() => {
    if (status !== "ready" || !mapRef.current || !geoConfig) return;
    const g: GMapsNamespace = window.google.maps;
    const map = mapRef.current;

    Object.values(refineryMarkersRef.current).forEach((m) => m.setMap(null));
    refineryMarkersRef.current = {};

    for (const r of geoConfig.refineries) {
      const marker = new g.Marker({
        position: { lat: r.lat, lng: r.lon },
        map,
        title: `${r.name} · ${Math.round(r.capacity_bpd / 1000)} kbd`,
        icon: refineryIcon(false, false),
        label: {
          text: r.name,
          color: "#c8d6f0",
          fontSize: "10px",
          fontFamily: "JetBrains Mono, monospace",
          className: "translate-y-4",
        },
      });
      const iw = new g.InfoWindow({
        content: `
          <div style="font-family:'JetBrains Mono',monospace;color:#0f172a;min-width:180px;">
            <div style="font-weight:700;font-size:12px;text-transform:uppercase;letter-spacing:0.08em;">${r.name}</div>
            <div style="margin-top:4px;font-size:11px;">Capacity: <b>${Math.round(r.capacity_bpd / 1000)} kbd</b></div>
          </div>`,
      });
      marker.addListener("mouseover", () => iw.open({ map, anchor: marker }));
      marker.addListener("mouseout", () => iw.close());
      refineryMarkersRef.current[r.id] = marker;
    }
    return () => {
      Object.values(refineryMarkersRef.current).forEach((m) => m.setMap(null));
      refineryMarkersRef.current = {};
    };
  }, [status, geoConfig]);

  // Pulse affected refineries (F10's knowledge-graph highlight) without
  // recreating any marker.
  useEffect(() => {
    for (const [id, marker] of Object.entries(refineryMarkersRef.current)) {
      const affected = affectedRefineryIds.has(id);
      marker.setIcon(refineryIcon(affected, affected && pulseOn));
    }
    // affectedRefineryIds is rebuilt every render from `geo` — compare via
    // its own JSON, not object identity, to avoid an infinite render loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(geo?.affected_refinery_ids ?? []), pulseOn]);

  // Tanker markers — created once per geoConfig load, positioned at each
  // track's first point; the animation effects below move/recolor them.
  useEffect(() => {
    if (status !== "ready" || !mapRef.current || !geoConfig) return;
    const g: GMapsNamespace = window.google.maps;
    const map = mapRef.current;

    Object.values(tankerMarkersRef.current).forEach((m) => m.setMap(null));
    tankerMarkersRef.current = {};

    for (const t of geoConfig.tankers) {
      const first = t.track[0];
      if (!first) continue;
      const marker = new g.Marker({
        position: { lat: first.lat, lng: first.lon },
        map,
        title: t.id,
        icon: tankerIcon(g, false, false),
      });
      const iw = new g.InfoWindow({ content: "" });
      marker.addListener("mouseover", () => {
        const isDark = darkTankerIds.has(t.id);
        iw.setContent(`
          <div style="font-family:'JetBrains Mono',monospace;color:#0f172a;min-width:160px;">
            <div style="font-weight:700;font-size:11px;text-transform:uppercase;">${t.id}</div>
            <div style="margin-top:2px;font-size:11px;">Corridor: ${t.corridor_id}</div>
            ${isDark ? `<div style="margin-top:2px;font-size:11px;color:#e94560;font-weight:700;">TRANSPONDER ANOMALY</div>` : ""}
          </div>`);
        iw.open({ map, anchor: marker });
      });
      marker.addListener("mouseout", () => iw.close());
      tankerMarkersRef.current[t.id] = marker;
    }
    return () => {
      Object.values(tankerMarkersRef.current).forEach((m) => m.setMap(null));
      tankerMarkersRef.current = {};
    };
    // darkTankerIds is derived fresh each render from `geo`; only geoConfig/
    // status should recreate the marker set itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, geoConfig]);

  // Step the replay forward on an interval (spec.md Phase 7: "step through
  // points on an interval, not a physics simulation").
  useEffect(() => {
    if (status !== "ready" || !geoConfig) return;
    const id = setInterval(() => setStepIndex((i) => i + 1), TANKER_STEP_MS);
    return () => clearInterval(id);
  }, [status, geoConfig]);

  useEffect(() => {
    if (!geoConfig) return;
    for (const t of geoConfig.tankers) {
      const marker = tankerMarkersRef.current[t.id];
      if (!marker || t.track.length === 0) continue;
      const point = t.track[stepIndex % t.track.length];
      marker.setPosition({ lat: point.lat, lng: point.lon });
    }
  }, [stepIndex, geoConfig]);

  // Dark-ship pulsing warning style (F18 — the one "real ML" beat), recolors
  // in place whenever the flagged set changes or the shared pulse ticks.
  useEffect(() => {
    const g = window.google?.maps;
    if (!g) return;
    for (const [id, marker] of Object.entries(tankerMarkersRef.current)) {
      const isDark = darkTankerIds.has(id);
      marker.setIcon(tankerIcon(g, isDark, isDark && pulseOn));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(geo?.dark_tanker_ids ?? []), pulseOn, status]);

  // One shared pulse ticker driving both the dark-tanker and
  // affected-refinery warning animations.
  useEffect(() => {
    const id = setInterval(() => setPulseOn((p) => !p), PULSE_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  if (status === "error") {
    const { corridors, refineries } = toIndiaMapData(geoConfig, corridorRisk);
    return (
      <div className="relative w-full h-full min-h-[420px]">
        <div className="absolute top-3 right-3 z-10 panel px-3 py-1.5 flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-destructive">
          <WifiOffDot /> Offline fallback · {errMsg}
        </div>
        <IndiaMap
          corridors={corridors}
          refineries={refineries}
          activeCorridor={activeCorridor}
          onCorridor={onSelectCorridor}
        />
      </div>
    );
  }

  return (
    <div className="relative w-full h-full min-h-[420px] rounded-lg overflow-hidden border border-border bg-[#05070d]">
      <div ref={containerRef} className="absolute inset-0" />

      {status === "loading" && (
        <div className="absolute inset-0 flex items-center justify-center text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
          Loading operational theatre…
        </div>
      )}

      {/* Legend */}
      <div className="absolute top-3 left-3 panel px-3 py-2 text-[10px] font-mono uppercase tracking-widest space-y-1">
        <div className="text-muted-foreground mb-1">Corridor risk</div>
        {(["critical", "high", "medium", "low"] as const).map((b) => (
          <div key={b} className="flex items-center gap-2">
            <span className="w-3 h-[3px]" style={{ background: bandHex(b) }} />
            <span style={{ color: bandColor[b] }}>{b}</span>
          </div>
        ))}
        <div className="pt-1 mt-1 border-t border-border flex items-center gap-2">
          <span className="w-2 h-2 rotate-45 bg-cyan" />
          <span>Refinery</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rotate-45" style={{ background: "#e94560" }} />
          <span style={{ color: "#e94560" }}>Affected refinery</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: "#e94560" }} />
          <span style={{ color: "#e94560" }}>Dark tanker</span>
        </div>
      </div>

      {/* Live badge */}
      <div className="absolute top-3 right-3 panel px-3 py-1.5 flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        Live · AIS + Watch agent
      </div>
    </div>
  );
}

function WifiOffDot() {
  return <span className="w-1.5 h-1.5 rounded-full bg-destructive" />;
}
