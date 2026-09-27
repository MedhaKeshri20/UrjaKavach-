// Static-ish map config (corridor geometry, refinery coordinates, the AIS
// tanker-track replay set) from GET /geo/state. Fetched once — this data is
// seed-config-level and doesn't change per signal. The live, per-signal half
// of the same endpoint (`geo.at_risk_tanker_ids`/`dark_tanker_ids`/
// `affected_refinery_ids`) already arrives on the WS-pushed RiskState as
// `state.geo` (verified identical to `/geo/state`'s own `geo` field on the
// backend — see tests/test_api.py's test_geo_state_matches_live_state_geo),
// so callers should read that directly rather than this hook's own `geo`.

import { useEffect, useState } from "react";
import { api, ApiError, type GeoStateResponse } from "@/lib/api";

export function useGeoState() {
  const [geoConfig, setGeoConfig] = useState<GeoStateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getGeoState()
      .then((res) => {
        if (cancelled) return;
        setGeoConfig(res);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load geo config");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { geoConfig, error };
}
