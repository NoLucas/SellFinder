"use client";

import { useState } from "react";
import LoginPanel, { type Session } from "@/components/LoginPanel";
import PredictionMap from "@/components/PredictionMap";
import RegionDetailPanel from "@/components/RegionDetailPanel";
import type { RegionDetailResult } from "@/lib/api/regionDetail";
import type { PredictionDetail } from "@/lib/api/types";

/**
 * First vertical slice of the map view (AGENT_BRIEFS.md STEP 2-D, screen 1).
 * run_id is still a plain input — real run-selection UI is blocked on
 * /backend's run-list endpoint (console/RECONCILIATION.md §6). Auth is no
 * longer a raw token field: see LoginPanel.tsx (DISPATCH-2 D-4).
 */
export default function ConsolePage() {
  const [runId, setRunId] = useState("run_01J8XM2");
  // ADR-003 §5 / D-17: session lives in React state only (lost on refresh)
  // — do NOT persist it to localStorage/sessionStorage. Real persistence is
  // httpOnly cookie + refresh, blocked on /backend's login endpoint
  // (console/RECONCILIATION.md §8).
  const [session, setSession] = useState<Session | null>(null);
  const [detail, setDetail] = useState<PredictionDetail | null>(null);
  const [isSampleDetail, setIsSampleDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleRegionSelect({ detail, isSample }: RegionDetailResult) {
    setDetail(detail);
    setIsSampleDetail(isSample);
  }

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
        {session && (
          <>
            <input
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
              placeholder="run_id"
              style={{ fontSize: 12, padding: "4px 6px" }}
            />
            <span style={{ fontSize: 12, color: "#52514e" }}>
              {session.tenantId} · {session.role}
            </span>
            {/* region_scope reflected in the UI, not just held silently (ADR-003 §5 / D-16) */}
            <span
              style={{ fontSize: 12, color: "#52514e" }}
              title="region_scope — 접근 가능 지역 코드 접두사"
            >
              {session.regionScope.length > 0 ? `범위: ${session.regionScope.join(", ")}` : "전체 지역"}
            </span>
            <button type="button" onClick={() => setSession(null)} style={{ fontSize: 12, marginLeft: "auto" }}>
              로그아웃
            </button>
          </>
        )}
        {error && <span style={{ fontSize: 12, color: "#d03b3b" }}>{error}</span>}
      </header>

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, position: "relative" }}>
          {session ? (
            <PredictionMap
              key={`${runId}:${session.token}`}
              runId={runId}
              authToken={session.token}
              onRegionSelect={handleRegionSelect}
              onError={setError}
            />
          ) : (
            <LoginPanel onAuthenticated={setSession} />
          )}
        </div>
        <RegionDetailPanel detail={detail} isSample={isSampleDetail} />
      </div>
    </div>
  );
}
