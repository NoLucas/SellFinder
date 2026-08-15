"use client";

import type { ReactNode } from "react";
import type { PredictionDetail } from "@/lib/api/types";

const KRW = new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 });

/**
 * Minimal first pass — full waterfall/comparable-region layout is tracked
 * separately in console/RECONCILIATION.md (§5 item 3). This exists so
 * PredictionMap's click handler has somewhere to render its result.
 *
 * Honesty rule (00_product_spec.md §4.2 / 05_scoring_spec.md §2): a null
 * expected_revenue_krw means data_tier=T0 — never show 0 or a dash in its
 * place, always the upload-data nudge, and only the relative ranking.
 */
export default function RegionDetailPanel({ detail }: { detail: PredictionDetail | null }) {
  if (!detail) {
    return <PanelShell>지도에서 지역을 클릭하면 상세 내역이 표시됩니다.</PanelShell>;
  }

  return (
    <PanelShell>
      <h2 style={{ margin: 0, fontSize: 16 }}>{detail.region_name}</h2>
      <p style={{ margin: "2px 0 12px", color: "#52514e", fontSize: 13 }}>
        opportunity_score {detail.opportunity_score.toFixed(1)} · #{detail.rank} · 신뢰도 {detail.confidence.level}
      </p>

      <RevenueBlock detail={detail} />

      <h3 style={{ fontSize: 13, margin: "16px 0 6px" }}>요인 분해</h3>
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
  if (detail.expected_revenue_krw === null) {
    return (
      <p style={{ fontSize: 13, color: "#52514e" }}>
        자사 판매 데이터를 업로드하면 매출 추정을 제공합니다. 지금은 상대 랭킹만 참고하세요.
      </p>
    );
  }
  const { p10, p50, p90 } = detail.expected_revenue_krw;
  return (
    <p style={{ fontSize: 13 }}>
      예상 매출 <strong>{KRW.format(p50)}</strong>
      <span style={{ color: "#898781" }}> ({KRW.format(p10)} ~ {KRW.format(p90)})</span>
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
