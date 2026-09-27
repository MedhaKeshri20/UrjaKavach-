// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// Dev-only proxy so the browser's REST calls to /api/* stay same-origin (no
// CORS needed) — mirrors frontend/next.config.ts's rewrite. The backend's
// own CORS is wildcard-open by default anyway (backend/config.py), so this
// isn't strictly required for correctness, just parity/consistency. Override
// the target with BACKEND_URL when the backend runs somewhere other than
// localhost:8000. This env var is server-side only (not VITE_-prefixed) —
// never exposed to the browser bundle.
const backend = process.env.BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  // Overrides the wrapped config's cloudflare-module default: this app is
  // deployed as a plain Node server (Docker), not Cloudflare Workers.
  // Produces .output/server/index.mjs, run via `node .output/server/index.mjs`.
  nitro: {
    preset: "node-server",
  },
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  vite: {
    server: {
      proxy: {
        "/api": {
          target: backend,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  },
});
