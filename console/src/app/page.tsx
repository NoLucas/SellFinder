"use client";

import { useState } from "react";
import PredictionMap from "@/components/PredictionMap";
import RegionDetailPanel from "@/components/RegionDetailPanel";
import type { PredictionDetail } from "@/lib/api/types";

/**
 * First vertical slice of the map view (AGENT_BRIEFS.md STEP 2-D, screen 1).
 * runId/token are query-string inputs for now — real auth/run-selection UI
 * is blocked on /backend's login + run-list endpoints (open question in
 * console/RECONCILIATION.md §6), so this keeps the map testable without them.
 */
export default function ConsolePage() {
  const [runId, setRunId] = useState("run_01J8XM2");
  const [authToken, setAuthToken] = useState("");
  const [detail, setDetail] = useState<PredictionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <header
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          padding: "8px 12px",
          borderBottom: "1px solid rgba(11, 11, 11, 0.10)",
        }}
      >
        <strong style={{ fontSize: 14 }}>SellFinder</strong>
        <input
          value={runId}
          onChange={(e) => setRunId(e.target.value)}
          placeholder="run_id"
          style={{ fontSize: 12, padding: "4px 6px" }}
        />
        <input
          value={authToken}
          onChange={(e) => setAuthToken(e.target.value)}
          placeholder="bearer token (dev only)"
          style={{ fontSize: 12, padding: "4px 6px", width: 220 }}
        />
        {error && <span style={{ fontSize: 12, color: "#d03b3b" }}>{error}</span>}
      </header>

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, position: "relative" }}>
          {authToken ? (
            <PredictionMap
              key={`${runId}:${authToken}`}
              runId={runId}
              authToken={authToken}
              onRegionSelect={setDetail}
              onError={setError}
            />
          ) : (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#898781" }}>
              토큰을 입력하면 지도가 로드됩니다.
            </div>
          )}
        </div>
        <RegionDetailPanel detail={detail} />
      </div>
    </div>
  );
}
