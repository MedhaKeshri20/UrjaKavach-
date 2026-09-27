# Multi-stage build. TanStack Start's nitro output (node-server preset, set
# in vite.config.ts) is self-contained after `npm run build` — no
# node_modules needed in the runtime stage.
#
# node:22-slim, not 20: several @tanstack/react-start-* deps declare
# engines >=22.12.0.
FROM node:22-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
# `npm install`, not `npm ci`: the committed lock file was resolved on
# Windows and is missing a Linux-only optional-dependency entry
# (lru-cache@11.5.2, pulled in transitively for this platform), which makes
# `npm ci`'s strict lockfile-match fail cross-platform. `npm install`
# reconciles it instead of hard-failing.
RUN npm install

COPY . .

# Vite's envDefine step inlines VITE_* vars into the client bundle at BUILD
# time (see src/hooks/useRiskState.ts, src/lib/api.ts) -- there is no runtime
# proxy in the built server (the vite.config.ts dev proxy only exists under
# `vite dev`). These MUST be reachable from the *browser*, not from inside
# the Docker network -- point them at wherever the backend is actually
# published (defaults match this repo's docker-compose.yml).
ARG VITE_API_URL=http://localhost:8000
ARG VITE_WS_URL=ws://localhost:8000/ws/state
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL

# Google Maps JS API browser key for RealWorldMap.tsx (src/components/kavach/
# RealWorldMap.tsx). Unset => loadGoogleMaps() rejects and the map silently
# falls back to the static IndiaMap SVG. Must also be restricted by HTTP
# referrer in Google Cloud Console to whatever origin this image is served
# from, or Google renders its own "can't load Maps correctly" error instead.
ARG VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_BROWSER_KEY=
ARG VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_TRACKING_ID=
ENV VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_BROWSER_KEY=$VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_BROWSER_KEY
ENV VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_TRACKING_ID=$VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_TRACKING_ID

RUN npm run build

FROM node:22-slim AS runtime
WORKDIR /app

COPY --from=build /app/.output ./.output

ENV NODE_ENV=production \
    PORT=8080 \
    HOST=0.0.0.0

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "fetch('http://localhost:8080/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", ".output/server/index.mjs"]
