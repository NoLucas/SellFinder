/**
 * DISPATCH-2 D-2 (orchestrator/DISPATCH-2.md §6, 05_scoring_spec.md §2):
 * `expected_revenue_krw === null` means data_tier=T0 (no tenant sales data).
 * The UI must show "상대적 유망도 랭킹" + an upload nudge in the amount's
 * place — never `0`, never `-`. Extracted out of RegionDetailPanel.tsx as a
 * pure function specifically so console/tests/revenue-display.test.mjs can
 * assert this without a DOM/React test harness.
 */

import type { MoneyRange } from "@/lib/api/types";

const KRW = new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 });

export type RevenueDisplay =
  | { kind: "unavailable"; message: string }
  | { kind: "range"; p50Label: string; rangeLabel: string };

/** T0's required UI copy (05_scoring_spec.md §2 table, "상대적 유망도 랭킹"). */
export const T0_UPLOAD_NUDGE =
  "자사 판매 데이터를 업로드하면 매출 추정을 제공합니다. 지금은 상대적 유망도 랭킹만 참고하세요.";

export function formatRevenueDisplay(expectedRevenueKrw: MoneyRange | null): RevenueDisplay {
  if (expectedRevenueKrw === null) {
    return { kind: "unavailable", message: T0_UPLOAD_NUDGE };
  }
  const { p10, p50, p90 } = expectedRevenueKrw;
  return {
    kind: "range",
    p50Label: KRW.format(p50),
    rangeLabel: `${KRW.format(p10)} ~ ${KRW.format(p90)}`,
  };
}
