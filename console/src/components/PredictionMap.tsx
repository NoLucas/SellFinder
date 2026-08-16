"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol as PMTilesProtocol } from "pmtiles";

import { authTransformRequest, getBasemapManifest, getRegionScores } from "@/lib/api/client";
import { resolveRegionDetail, type RegionDetailResult } from "@/lib/api/regionDetail";
import type { RegionLevel, RegionScoresPayload } from "@/lib/api/types";
import { NO_DATA_FILL, scoreFillExpression, type ScoreDomain } from "@/lib/color/scoreScale";
import { HATCH_IMAGE_ID, hatchOpacityExpression, registerHatchPattern } from "@/lib/map/hatchPattern";
import { computeInitialViewport } from "@/lib/map/initialViewport";
import { isRegionIdInScope, OUT_OF_SCOPE_FILL, withRegionScopeGuard } from "@/lib/map/regionScope";

// Registered once at module scope — addProtocol is global to maplibre-gl,
// re-registering per mount/unmount would just thrash the same handler.
let pmtilesRegistered = false;
function ensurePmtilesProtocol() {
  if (pmtilesRegistered) return;
  const protocol = new PMTilesProtocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  pmtilesRegistered = true;
}

const SOURCE_ID = "predictions";
const FILL_LAYER_ID = "region-fill";
const OUTLINE_LAYER_ID = "region-outline";
const HATCH_LAYER_ID = "region-hatch";

/**
 * D-14 (orchestrator/DECISIONS.md): level is a user choice, never an
 * automatic switch on zoom. This is the full fixed set the picker offers —
 * `custom_catchment` isn't in it because it has no boundary level to pick,
 * it's tenant-drawn geometry (handled as its own branch in `bootstrap`).
 */
const PICKABLE_LEVELS: { value: RegionLevel; label: string }[] = [
  { value: "sido", label: "시도" },
  { value: "sigungu", label: "시군구" },
  { value: "adm_dong", label: "행정동" },
];

export interface PredictionMapProps {
  runId: string;
  authToken: string;
  /** Prefix codes from the session's token (ADR-003 D-16); empty = full access. Display-only — the server is the real enforcement point. */
  regionScope: readonly string[];
  productId?: string;
  channel?: string;
  /** Called only when a region is clicked and its detail finishes loading. */
  onRegionSelect?: (result: RegionDetailResult) => void;
  /** Called when a click lands on a region outside regionScope — never routed through resolveRegionDetail (that would risk showing the sample fixture in place of a region the user isn't cleared to see). */
  onOutOfScope?: (regionId: string) => void;
  onError?: (message: string) => void;
}

type LoadState = "loading" | "ready" | "error";

export default function PredictionMap({
  runId,
  authToken,
  regionScope,
  productId,
  channel,
  onRegionSelect,
  onOutOfScope,
  onError,
}: PredictionMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [scoreDomain, setScoreDomain] = useState<ScoreDomain>([0, 100]);
  const [scoresPayload, setScoresPayload] = useState<RegionScoresPayload | null>(null);
  // D-14: level is a user choice, never derived from zoom. Seeded from the
  // run's own region_level once scores resolve; the picker below can only
  // change it via an explicit click — no zoom listener writes to this.
  const [level, setLevel] = useState<RegionLevel | null>(null);

  // Mount: create the map once, fetch this run's scores, and — for the
  // custom_catchment case only — paint directly (it has no boundary level
  // to pick, so it never goes through the level-driven effect below).
  useEffect(() => {
    if (!containerRef.current) return;
    ensurePmtilesProtocol();
    let cancelled = false;

    // D-16: a region_scope-restricted user shouldn't open the map to a
    // screen of out-of-scope grey they have to pan away from manually.
    const { center, zoom } = computeInitialViewport(regionScope);
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {},
        layers: [{ id: "background", type: "background", paint: { "background-color": "#f9f9f7" } }],
      },
      center,
      zoom,
      transformRequest: authTransformRequest(authToken),
    });
    mapRef.current = map;

    map.on("load", () => {
      void bootstrap();
    });

    async function bootstrap() {
      setLoadState("loading");
      try {
        // scores → region_level, boundary_vintage, and the fixed score_range
        // this run's color scale must use.
        const payload: RegionScoresPayload = await getRegionScores(runId, authToken, { productId, channel });
        if (cancelled) return;
        setScoreDomain([payload.score_range.min, payload.score_range.max]);
        setScoresPayload(payload);

        if (payload.region_level === "custom_catchment" && payload.custom_geometries) {
          // Tenant-defined catchments: too few, too tenant-specific for a
          // shared pmtiles archive — inlined as GeoJSON instead (ADR-001).
          // No level picker applies here, so this is painted directly
          // rather than through the [level] effect.
          map.addSource(SOURCE_ID, {
            type: "geojson",
            data: payload.custom_geometries,
            promoteId: "region_id",
          });
          addScoreLayers(map, undefined, [payload.score_range.min, payload.score_range.max], regionScope);
          joinScores(map, undefined, payload);
          setLoadState("ready");
        } else {
          // Vector-tile levels are painted by the [level] effect (it also
          // handles the initial paint — setting `level` here triggers it).
          setLevel(payload.region_level);
        }
      } catch (err) {
        if (cancelled) return;
        setLoadState("error");
        onError?.(err instanceof Error ? err.message : "failed to load prediction map");
      }
    }

    map.on("mouseenter", FILL_LAYER_ID, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", FILL_LAYER_ID, () => {
      map.getCanvas().style.cursor = "";
    });

    // detail + factor breakdown fetched ONLY on click — never on hover,
    // never eagerly for the whole viewport.
    map.on("click", FILL_LAYER_ID, (e) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const regionId = String(feature.properties?.region_id ?? feature.id ?? "");
      if (!regionId) return;

      // D-16: never call resolveRegionDetail for an out-of-scope region —
      // its real detail call will 404/403 (server not built yet either
      // way) and fall back to the sample fixture, which would show made-up
      // data for a region this user isn't cleared to see. Short-circuit
      // client-side with the honest reason instead.
      if (!isRegionIdInScope(regionId, regionScope)) {
        onOutOfScope?.(regionId);
        return;
      }

      resolveRegionDetail(runId, regionId, authToken)
        .then((result) => {
          if (!cancelled) onRegionSelect?.(result);
        })
        .catch((err) => {
          // resolveRegionDetail only rejects if even the sample fixture
          // path throws, which means a bug in this file, not a network/API
          // failure — those are already caught and turned into isSample.
          if (!cancelled) onError?.(err instanceof Error ? err.message : "failed to load region detail");
        });
    });

    return () => {
      cancelled = true;
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, authToken, regionScope, productId, channel]);

  // Level-driven paint: runs once for the run's own level (right after
  // bootstrap sets it) and again whenever the picker sets a different one.
  // Swaps the vector source/layers for `level`'s manifest; the score join
  // uses the SAME scoresPayload every time (scores aren't re-fetched per
  // level — the run has exactly one region_level). Levels other than the
  // run's own naturally render all-NO_DATA (scoreFillExpression's existing
  // null-state guard), which is an honest "no prediction at this level" —
  // not a special case to branch on.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !level || !scoresPayload || scoresPayload.region_level === "custom_catchment") return;
    let cancelled = false;

    async function paint() {
      if (!map || !scoresPayload) return;
      setLoadState("loading");
      try {
        const isRunLevel = level === scoresPayload.region_level;
        // Only the run's own level carries a `boundary_vintage` worth
        // pinning (see getBasemapManifest doc comment) — other levels are
        // pure basemap browsing, so "latest" (vintage omitted) is fine.
        const manifest = await getBasemapManifest(
          level as RegionLevel,
          isRunLevel ? scoresPayload.boundary_vintage : undefined,
          authToken,
        );
        if (cancelled) return;

        removeLayerIfPresent(map, HATCH_LAYER_ID);
        removeLayerIfPresent(map, OUTLINE_LAYER_ID);
        removeLayerIfPresent(map, FILL_LAYER_ID);
        if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);

        map.addSource(SOURCE_ID, {
          type: "vector",
          url: `pmtiles://${manifest.tile_url}`,
          promoteId: { [manifest.source_layer]: manifest.feature_id_property },
          minzoom: manifest.minzoom,
          maxzoom: manifest.maxzoom,
        });
        addScoreLayers(map, manifest.source_layer, [scoresPayload.score_range.min, scoresPayload.score_range.max], regionScope);
        joinScores(map, manifest.source_layer, scoresPayload);

        setLoadState("ready");
      } catch (err) {
        if (cancelled) return;
        setLoadState("error");
        onError?.(err instanceof Error ? err.message : "failed to load prediction map");
      }
    }

    void paint();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, scoresPayload, authToken, regionScope]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      {loadState === "loading" && <MapOverlay text="예측 결과를 불러오는 중..." />}
      {loadState === "error" && <MapOverlay text="지도를 불러오지 못했습니다." tone="error" />}
      {scoresPayload && scoresPayload.region_level !== "custom_catchment" && level && (
        <LevelPicker
          selected={level}
          runLevel={scoresPayload.region_level}
          onSelect={setLevel}
        />
      )}
      <ScoreLegend domain={scoreDomain} showOutOfScope={regionScope.length > 0} />
    </div>
  );
}

/** Fill/outline/hatch layers, shared by the custom_catchment and vector-tile paint paths. */
function addScoreLayers(
  map: maplibregl.Map,
  sourceLayer: string | undefined,
  domain: ScoreDomain,
  regionScope: readonly string[],
) {
  map.addLayer({
    id: FILL_LAYER_ID,
    type: "fill",
    source: SOURCE_ID,
    ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
    paint: {
      // D-16: out-of-scope regions never reach the score ramp / NO_DATA_FILL
      // branch — the guard is evaluated first (see regionScope.ts).
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      "fill-color": withRegionScopeGuard(scoreFillExpression(domain), regionScope) as any,
      "fill-opacity": 0.85,
    },
  });

  map.addLayer({
    id: OUTLINE_LAYER_ID,
    type: "line",
    source: SOURCE_ID,
    ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
    paint: { "line-color": "rgba(11, 11, 11, 0.15)", "line-width": 0.5 },
  });

  registerHatchPattern(map);
  map.addLayer({
    id: HATCH_LAYER_ID,
    type: "fill",
    source: SOURCE_ID,
    ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
    paint: {
      "fill-pattern": HATCH_IMAGE_ID,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      "fill-opacity": hatchOpacityExpression() as any,
    },
  });
}

/** scores → feature-state join, driven by the response's own `schema` so a field reorder doesn't silently mis-map columns. */
function joinScores(map: maplibregl.Map, sourceLayer: string | undefined, payload: RegionScoresPayload) {
  const idIdx = payload.schema.indexOf("region_id");
  const scoreIdx = payload.schema.indexOf("opportunity_score");
  const confIdx = payload.schema.indexOf("confidence_level");
  for (const row of payload.scores) {
    map.setFeatureState(
      { source: SOURCE_ID, sourceLayer, id: row[idIdx] },
      { score: row[scoreIdx], confidence_level: row[confIdx] },
    );
  }
}

function removeLayerIfPresent(map: maplibregl.Map, id: string) {
  if (map.getLayer(id)) map.removeLayer(id);
}

/** D-14 level picker — sido/sigungu/adm_dong, user-selected only. Never wired to a zoom event. */
function LevelPicker({
  selected,
  runLevel,
  onSelect,
}: {
  selected: RegionLevel;
  runLevel: RegionLevel;
  onSelect: (level: RegionLevel) => void;
}) {
  return (
    <div
      style={{
        position: "absolute",
        right: 12,
        top: 12,
        display: "flex",
        gap: 4,
        background: "#fcfcfb",
        border: "1px solid rgba(11, 11, 11, 0.10)",
        borderRadius: 6,
        padding: 4,
      }}
    >
      {PICKABLE_LEVELS.map(({ value, label }) => (
        <button
          key={value}
          type="button"
          onClick={() => onSelect(value)}
          title={value === runLevel ? "이번 예측이 계산된 레벨" : "경계만 표시됩니다 (이 레벨엔 예측 없음)"}
          style={{
            fontSize: 12,
            padding: "4px 8px",
            borderRadius: 4,
            border: "1px solid rgba(11, 11, 11, 0.10)",
            background: value === selected ? "#0b0b0b" : "transparent",
            color: value === selected ? "#fcfcfb" : "#0b0b0b",
            cursor: "pointer",
          }}
        >
          {label}
          {value === runLevel ? " •" : ""}
        </button>
      ))}
    </div>
  );
}

function MapOverlay({ text, tone = "muted" }: { text: string; tone?: "muted" | "error" }) {
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(249, 249, 247, 0.7)",
        color: tone === "error" ? "#d03b3b" : "#52514e",
        fontSize: 14,
        pointerEvents: "none",
      }}
    >
      {text}
    </div>
  );
}

/** Sequential scale key + the low-confidence pattern swatch — color is never the only channel. */
function ScoreLegend({ domain, showOutOfScope }: { domain: ScoreDomain; showOutOfScope: boolean }) {
  return (
    <div
      style={{
        position: "absolute",
        left: 12,
        bottom: 12,
        background: "#fcfcfb",
        border: "1px solid rgba(11, 11, 11, 0.10)",
        borderRadius: 6,
        padding: "8px 10px",
        fontSize: 12,
        color: "#0b0b0b",
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <div
          aria-hidden
          style={{
            width: 96,
            height: 10,
            borderRadius: 2,
            background: `linear-gradient(90deg, ${NO_DATA_FILL} 0%, #cde2fb 8%, #3987e5 50%, #0d366b 100%)`,
          }}
        />
        <span style={{ color: "#52514e" }}>
          opportunity_score {domain[0].toFixed(0)} → {domain[1].toFixed(0)}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <HatchSwatch />
        <span style={{ color: "#52514e" }}>신뢰도 낮음 (confidence: low)</span>
      </div>
      {showOutOfScope && (
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div aria-hidden style={{ width: 16, height: 16, borderRadius: 2, background: OUT_OF_SCOPE_FILL }} />
          <span style={{ color: "#52514e" }}>권한 범위 밖 (데이터 없음과 다름)</span>
        </div>
      )}
    </div>
  );
}

function HatchSwatch() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <rect width="16" height="16" fill="#86b6ef" />
      <g stroke="rgba(11,11,11,0.4)" strokeWidth="1.5">
        <line x1="0" y1="16" x2="16" y2="0" />
        <line x1="-4" y1="4" x2="4" y2="-4" />
        <line x1="12" y1="20" x2="20" y2="12" />
      </g>
    </svg>
  );
}
