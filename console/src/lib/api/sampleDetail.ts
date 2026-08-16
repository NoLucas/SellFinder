/**
 * DISPATCH-2 D-1 scaffold (orchestrator/DISPATCH-2.md §6): C-2 (job worker
 * calls B's predict_batch) hasn't shipped yet, so GET /predictions/{run_id}/
 * regions/{region_id} doesn't exist server-side. This is a single hardcoded
 * fixture — NOT a generator, NOT invented per-click — so RegionDetailPanel
 * has something real-shaped to render while wiring up.
 *
 * The 8 factor_keys, their order, and the evidence-writing rules (cite an
 * actual value + a benchmark, never a causal claim) follow
 * shared/contracts/05_scoring_spec.md §1 and §6 exactly — this is what the
 * REAL data will look like, not a looser placeholder shape.
 *
 * log_contribution values sum to ln(2.14) ≈ 0.7608, matching this fixture's
 * own opportunity_score/base_volume relationship, so the panel's "합이
 * 맞아야 한다" invariant (§1) has something non-trivial to fail against if
 * a future edit breaks it — this is fixture data, not a live invariant
 * check (that belongs in intelligence's test suite, not here).
 *
 * Swap point: console/src/lib/api/regionDetail.ts is what decides whether
 * this fixture or the real API response is used. Do not import this file
 * from PredictionMap.tsx directly.
 */

import type { Factor, PredictionDetail } from "./types";

const SAMPLE_FACTORS: Factor[] = [
  {
    key: "addressable_demand",
    label: "수요 규모",
    log_contribution: 0.262,
    display_effect: "×1.30",
    evidence: "20~30대 인구 15.2만명, 주간활동인구비 1.34 (동종 지역 평균 1.05)",
  },
  {
    key: "category_penetration",
    label: "카테고리 침투율",
    log_contribution: 0.182,
    display_effect: "×1.20",
    evidence: "RTD커피 카테고리 소비지수 138 (전국 평균 100)",
  },
  {
    key: "product_affinity",
    label: "제품 적합도",
    log_contribution: 0.095,
    display_effect: "×1.10",
    evidence: "제품 가격대·용량 프로파일과 지역 1인가구 비율(41.2%) 적합도 상위 20%",
  },
  {
    key: "price_acceptance",
    label: "가격 수용도",
    log_contribution: 0.041,
    display_effect: "×1.04",
    evidence: "지역 소득 5분위 중 4분위, 아파트가격지수 108 (전국 100)",
  },
  {
    key: "competition",
    label: "경쟁 강도",
    log_contribution: -0.105,
    display_effect: "×0.90",
    evidence: "동일 카테고리 점포수 34개/㎢, 자사 점유율 없음 — 경쟁 밀도 상위 30%",
  },
  {
    key: "channel_availability",
    label: "채널 접근성",
    log_contribution: 0.077,
    display_effect: "×1.08",
    evidence: "편의점 채널 점포수 128개, 온라인 주문밀도 지수 112 (전국 100)",
  },
  {
    key: "seasonality",
    label: "계절성",
    log_contribution: 0.02,
    display_effect: "×1.02",
    evidence: "예측 구간(7~8월) 계절 지수 1.02 (연중 평균 1.00)",
  },
  {
    key: "tenant_calibration",
    label: "자사 실적 보정",
    log_contribution: 0.189,
    display_effect: "×1.21",
    evidence: "인근 유사 프로파일 자사 매장 4곳 대비 잔차 보정 +21% (comparable_region_count=18)",
  },
];

/**
 * Builds the fixture for a specific run/region so clicking different map
 * features doesn't show a mismatched region_name — everything BESIDES the
 * ids is fixed sample data (factors, evidence, confidence).
 */
export function buildSampleDetail(runId: string, regionId: string): PredictionDetail {
  return {
    run_id: runId,
    product_id: "prd_sample",
    region_id: regionId,
    region_name: `지역 ${regionId} (예시)`,
    channel: "offline",
    opportunity_score: 82.4,
    rank: 3,
    expected_revenue_krw: { p10: 18_400_000, p50: 31_200_000, p90: 52_600_000 },
    confidence: { level: "medium", data_coverage: 0.71, comparable_region_count: 18 },
    factors: SAMPLE_FACTORS,
    comparable_regions: [
      { region_id: "41135", name: "수원시 팔달구", similarity: 0.88, actual_revenue_krw: 29_800_000 },
      { region_id: "11650", name: "서초구", similarity: 0.81, actual_revenue_krw: 34_100_000 },
    ],
    cannibalization: null,
    risks: ["동일 카테고리 경쟁 밀도가 상위 30%로, 초기 점유율 확보에 시간이 걸릴 수 있습니다."],
    data_freshness: [{ source: "sbiz_202601", as_of: "2026-01-01" }],
  };
}
