"use client";

import type { ReactNode } from "react";
import type { PredictionDetail } from "@/lib/api/types";
import { formatRevenueDisplay } from "@/lib/format/revenue";

/**
 * Minimal first pass — full waterfall/comparable-region layout is tracked
 * separately in console/RECONCILIATION.md (§5 item 3). This exists so
 * PredictionMap's click handler has somewhere to render its result.
 *
 * DISPATCH-2 D-1 (05_scoring_spec.md §1/§6): renders exactly the `factors`
 * array it's given — 8 keys, labels, evidence — and invents nothing beyond
 * it. `isSample` says whether that array is real (from C-2) or the
 * console/src/lib/api/sampleDetail.ts scaffold fixture; the banner below
 * is how that honesty carries through to the screen, not just the code.
 *
 * `restrictedRegionId` (D-16): a click outside the session's region_scope
 * never reaches `detail` at all (PredictionMap.tsx short-circuits before
 * calling resolveRegionDetail) — it's a third, distinct state from both
 * "nothing selected yet" and "showing sample/real detail". "권한 밖" and
 * "데이터 없음" must not collapse into the same message.
 */
export default function RegionDetailPanel({
  detail,
  isSample = false,
  restrictedRegionId = null,
}: {
  detail: PredictionDetail | null;
  isSample?: boolean;
  restrictedRegionId?: string | null;
}) {
  if (restrictedRegionId) {
    return (
      <PanelShell>
        <div
          style={{
            fontSize: 13,
            color: "#1c4a7a",
            background: "#e8f0fa",
            border: "1px solid rgba(28, 74, 122, 0.2)",
            borderRadius: 4,
            padding: "10px 12px",
          }}
        >
          <strong>지역 {restrictedRegionId}은(는) 이 계정의 접근 범위 밖입니다.</strong>
          <p style={{ margin: "6px 0 0", fontSize: 12, color: "#3a5f85" }}>
            데이터가 없는 것이 아니라 권한이 없는 것입니다. 지역 범위 확장이 필요하면 관리자에게
            요청하세요.
          </p>
        </div>
      </PanelShell>
    );
  }

  if (!detail) {
    return <PanelShell>지도에서 지역을 클릭하면 상세 내역이 표시됩니다.</PanelShell>;
  }

  return (
    <PanelShell>
      {isSample && (
        <div
          style={{
            fontSize: 11,
            color: "#8a6d1a",
            background: "#fbf3da",
            border: "1px solid rgba(138, 109, 26, 0.25)",
            borderRadius: 4,
            padding: "4px 8px",
            marginBottom: 10,
          }}
        >
          예시 데이터입니다 — 실제 예측이 아닙니다 (backend의 예측 생성 경로가 아직 연결되지 않았습니다).
        </div>
      )}
      <h2 style={{ margin: 0, fontSize: 16 }}>{detail.region_name}</h2>
      <p style={{ margin: "2px 0 12px", color: "#52514e", fontSize: 13 }}>
        opportunity_score {detail.opportunity_score.toFixed(1)} · #{detail.rank} · 신뢰도 {detail.confidence.level}
      </p>

      <RevenueBlock detail={detail} />

      <h3 style={{ fontSize: 13, margin: "16px 0 6px" }}>요인 분해 (8개)</h3>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
        {detail.factors.map((f) => (
          <li key={f.key} style={{ marginBottom: 6 }}>
            <strong>{f.label}</strong> {f.display_effect ?? ""}
            <div style={{ color: "#52514e" }}>{f.evidence}</div>
          </li>
        ))}
      </ul>

      {detail.cannibalization === null ? (
        <p style={{ fontSize: 12, color: "#898781", marginTop: 12 }}>
          기존 매장 정보를 등록하면 잠식 위험을 계산할 수 있습니다.
        </p>
      ) : (
        <p style={{ fontSize: 12, color: "#52514e", marginTop: 12 }}>
          인근 자사 매장 {detail.cannibalization.nearby_own_stores}곳 · 예상 순증율{" "}
          {(detail.cannibalization.estimated_uplift_ratio * 100).toFixed(0)}%
        </p>
      )}

      {detail.risks && detail.risks.length > 0 && (
        <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12, color: "#52514e" }}>
          {detail.risks.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </PanelShell>
  );
}

function RevenueBlock({ detail }: { detail: PredictionDetail }) {
  const display = formatRevenueDisplay(detail.expected_revenue_krw);
  if (display.kind === "unavailable") {
    return <p style={{ fontSize: 13, color: "#52514e" }}>{display.message}</p>;
  }
  return (
    <p style={{ fontSize: 13 }}>
      예상 매출 <strong>{display.p50Label}</strong>
      <span style={{ color: "#898781" }}> ({display.rangeLabel})</span>
    </p>
  );
}

function PanelShell({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        width: 320,
        height: "100%",
        overflowY: "auto",
        padding: 16,
        borderLeft: "1px solid rgba(11, 11, 11, 0.10)",
        background: "#fcfcfb",
        color: "#0b0b0b",
        boxSizing: "border-box",
      }}
    >
      {children}
    </div>
  );
}
