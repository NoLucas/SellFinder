"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol as PMTilesProtocol } from "pmtiles";

import { authTransformRequest, getBasemapManifest, getRegionDetail, getRegionScores } from "@/lib/api/client";
import type { PredictionDetail, RegionScoresPayload } from "@/lib/api/types";
import { NO_DATA_FILL, scoreFillExpression, type ScoreDomain } from "@/lib/color/scoreScale";
import { HATCH_IMAGE_ID, hatchOpacityExpression, registerHatchPattern } from "@/lib/map/hatchPattern";

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

export interface PredictionMapProps {
  runId: string;
  authToken: string;
  productId?: string;
  channel?: string;
  /** Called only when a region is clicked and its detail finishes loading. */
  onRegionSelect?: (detail: PredictionDetail) => void;
  onError?: (message: string) => void;
}

type LoadState = "loading" | "ready" | "error";

export default function PredictionMap({ runId, authToken, productId, channel, onRegionSelect, onError }: PredictionMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [scoreDomain, setScoreDomain] = useState<ScoreDomain>([0, 100]);

  useEffect(() => {
    if (!containerRef.current) return;
    ensurePmtilesProtocol();
    let cancelled = false;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {},
        layers: [{ id: "background", type: "background", paint: { "background-color": "#f9f9f7" } }],
      },
      center: [127.8, 36.5], // Korea
      zoom: 6.3,
      transformRequest: authTransformRequest(authToken),
    });

    map.on("load", () => {
      void bootstrap();
    });

    // Set once bootstrap resolves which vector source-layer (pmtiles path)
    // or `undefined` (geojson custom_catchment path) the layers/join use.
    let sourceLayer: string | undefined;

    async function bootstrap() {
      setLoadState("loading");
      try {
        // 1) scores → region_level, boundary_vintage, and the fixed
        // score_range this run's color scale must use.
        const scoresPayload: RegionScoresPayload = await getRegionScores(runId, authToken, {
          productId,
          channel,
        });
        if (cancelled) return;
        setScoreDomain([scoresPayload.score_range.min, scoresPayload.score_range.max]);

        if (scoresPayload.region_level === "custom_catchment" && scoresPayload.custom_geometries) {
          // Tenant-defined catchments: too few, too tenant-specific for a
          // shared pmtiles archive — inlined as GeoJSON instead (ADR-001).
          sourceLayer = undefined;
          map.addSource(SOURCE_ID, {
            type: "geojson",
            data: scoresPayload.custom_geometries,
            promoteId: "region_id",
          });
        } else {
          // 2) manifest → the pmtiles archive for THIS run's boundary
          // vintage — never "latest" (see getBasemapManifest doc comment).
          const manifest = await getBasemapManifest(
            scoresPayload.region_level,
            scoresPayload.boundary_vintage,
            authToken,
          );
          if (cancelled) return;
          sourceLayer = manifest.source_layer;

          map.addSource(SOURCE_ID, {
            type: "vector",
            url: `pmtiles://${manifest.tile_url}`,
            promoteId: { [manifest.source_layer]: manifest.feature_id_property },
            minzoom: manifest.minzoom,
            maxzoom: manifest.maxzoom,
          });
        }

        map.addLayer({
          id: FILL_LAYER_ID,
          type: "fill",
          source: SOURCE_ID,
          ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
          paint: {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            "fill-color": scoreFillExpression([scoresPayload.score_range.min, scoresPayload.score_range.max]) as any,
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

        // 3) scores → feature-state join, driven by the response's own
        // `schema` so a field reorder doesn't silently mis-map columns.
        const idIdx = scoresPayload.schema.indexOf("region_id");
        const scoreIdx = scoresPayload.schema.indexOf("opportunity_score");
        const confIdx = scoresPayload.schema.indexOf("confidence_level");
        for (const row of scoresPayload.scores) {
          map.setFeatureState(
            { source: SOURCE_ID, sourceLayer, id: row[idIdx] },
            { score: row[scoreIdx], confidence_level: row[confIdx] },
          );
        }

        setLoadState("ready");
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

    // 4) detail + factor breakdown fetched ONLY on click — never on hover,
    // never eagerly for the whole viewport.
    map.on("click", FILL_LAYER_ID, (e) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const regionId = String(feature.properties?.region_id ?? feature.id ?? "");
      if (!regionId) return;

      getRegionDetail(runId, regionId, authToken)
        .then((detail) => {
          if (!cancelled) onRegionSelect?.(detail);
        })
        .catch((err) => {
          if (!cancelled) onError?.(err instanceof Error ? err.message : "failed to load region detail");
        });
    });

    return () => {
      cancelled = true;
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, authToken, productId, channel]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      {loadState === "loading" && <MapOverlay text="예측 결과를 불러오는 중..." />}
      {loadState === "error" && <MapOverlay text="지도를 불러오지 못했습니다." tone="error" />}
      <ScoreLegend domain={scoreDomain} />
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
function ScoreLegend({ domain }: { domain: ScoreDomain }) {
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
