"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { authTransformRequest, getRegionDetail, getRunManifest, listAllRegionScores } from "@/lib/api/client";
import type { PredictionDetail, RegionScore } from "@/lib/api/types";
import { NO_DATA_FILL, scoreFillExpression } from "@/lib/color/scoreScale";
import { HATCH_IMAGE_ID, hatchOpacityExpression, registerHatchPattern } from "@/lib/map/hatchPattern";

const SOURCE_ID = "predictions";
// Assumed vector-tile source-layer name — 04_api_contract.yaml documents the
// tile endpoint's *properties* (opportunity_score, confidence_level) but not
// its source-layer name. Flagged in console/RECONCILIATION.md for backend
// to confirm; change this one constant if it turns out to differ.
const SOURCE_LAYER = "regions";
const FILL_LAYER_ID = "region-fill";
const OUTLINE_LAYER_ID = "region-outline";
const HATCH_LAYER_ID = "region-hatch";

export interface PredictionMapProps {
  runId: string;
  authToken: string;
  /** Called only when a region is clicked and its detail finishes loading. */
  onRegionSelect?: (detail: PredictionDetail) => void;
  onError?: (message: string) => void;
}

type LoadState = "loading" | "ready" | "error";

export default function PredictionMap({ runId, authToken, onRegionSelect, onError }: PredictionMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
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
    mapRef.current = map;

    map.on("load", () => {
      void bootstrap();
    });

    async function bootstrap() {
      setLoadState("loading");
      try {
        // 1) manifest → tile URL, gated on the run actually being ready.
        const manifest = await getRunManifest(runId, authToken);
        if (cancelled) return;
        if (manifest.status !== "succeeded") {
          setLoadState("error");
          onError?.(`prediction run ${runId} is '${manifest.status}', not renderable yet`);
          return;
        }

        map.addSource(SOURCE_ID, {
          type: "vector",
          tiles: [manifest.tileUrlTemplate],
          promoteId: { [SOURCE_LAYER]: "region_id" },
        });

        map.addLayer({
          id: FILL_LAYER_ID,
          type: "fill",
          source: SOURCE_ID,
          "source-layer": SOURCE_LAYER,
          paint: {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            "fill-color": scoreFillExpression() as any,
            "fill-opacity": 0.85,
          },
        });

        map.addLayer({
          id: OUTLINE_LAYER_ID,
          type: "line",
          source: SOURCE_ID,
          "source-layer": SOURCE_LAYER,
          paint: { "line-color": "rgba(11, 11, 11, 0.15)", "line-width": 0.5 },
        });

        registerHatchPattern(map);
        map.addLayer({
          id: HATCH_LAYER_ID,
          type: "fill",
          source: SOURCE_ID,
          "source-layer": SOURCE_LAYER,
          paint: {
            "fill-pattern": HATCH_IMAGE_ID,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            "fill-opacity": hatchOpacityExpression() as any,
          },
        });

        // 2) scores → feature-state join. Kept independent of tile geometry
        // so re-running/refreshing scores never re-fetches vector tiles.
        const scores: RegionScore[] = await listAllRegionScores(runId, authToken);
        if (cancelled) return;

        for (const region of scores) {
          map.setFeatureState(
            { source: SOURCE_ID, sourceLayer: SOURCE_LAYER, id: region.region_id },
            { score: region.opportunity_score, confidence_level: region.confidence.level },
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

    // 3) detail + factor breakdown fetched ONLY on click — never on hover,
    // never eagerly for the whole viewport.
    map.on("click", FILL_LAYER_ID, (e) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const regionId = String(feature.properties?.region_id ?? feature.id ?? "");
      if (!regionId) return;

      setSelectedRegionId(regionId);
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
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, authToken]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      {loadState === "loading" && <MapOverlay text="예측 결과를 불러오는 중..." />}
      {loadState === "error" && <MapOverlay text="지도를 불러오지 못했습니다." tone="error" />}
      <ScoreLegend />
      {selectedRegionId && <span data-testid="selected-region" hidden>{selectedRegionId}</span>}
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
function ScoreLegend() {
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
        <span style={{ color: "#52514e" }}>opportunity_score 0 → 100</span>
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
