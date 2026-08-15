/**
 * Hand-derived from shared/contracts/04_api_contract.yaml (v0.2.0).
 * Only the subset consumed by the map view + region detail panel.
 * Do not diverge from the contract — if a field is missing here, add it
 * from the contract rather than inventing a shape.
 */

export type ConfidenceLevel = "low" | "medium" | "high";

export type FactorKey =
  | "addressable_demand"
  | "category_penetration"
  | "product_affinity"
  | "price_acceptance"
  | "competition"
  | "channel_availability"
  | "seasonality"
  | "tenant_calibration";

export interface MoneyRange {
  p10: number;
  p50: number;
  p90: number;
}

export interface Confidence {
  level: ConfidenceLevel;
  data_coverage: number;
  backtest_wmape?: number | null;
  comparable_region_count?: number;
}

export interface Factor {
  key: FactorKey;
  label: string;
  log_contribution: number;
  display_effect?: string;
  value?: number;
  benchmark?: number;
  evidence: string;
}

/** One row of GET /predictions/{run_id}/regions — powers the map join. */
export interface RegionScore {
  region_id: string;
  region_name: string;
  rank: number;
  opportunity_score: number;
  score_percentile: number;
  /** null when data_tier=T0 — never render a guessed amount. */
  expected_revenue_krw: MoneyRange | null;
  confidence: Pick<Confidence, "level" | "data_coverage">;
}

export interface RegionScorePage {
  data: RegionScore[];
  next_cursor: string | null;
}

export interface ComparableRegion {
  region_id: string;
  name: string;
  similarity: number;
  actual_revenue_krw?: number;
  note?: string;
}

export interface Cannibalization {
  nearby_own_stores: number;
  estimated_uplift_ratio: number;
  note?: string;
}

export interface DataFreshnessEntry {
  source: string;
  as_of: string;
}

/** GET /predictions/{run_id}/regions/{region_id} — fetched only on click. */
export interface PredictionDetail {
  run_id: string;
  product_id: string;
  region_id: string;
  region_name: string;
  channel: string;
  opportunity_score: number;
  rank: number;
  expected_revenue_krw: MoneyRange | null;
  expected_units?: MoneyRange | null;
  expected_profit_krw?: { p50: number } | null;
  confidence: Confidence;
  factors: Factor[];
  comparable_regions?: ComparableRegion[];
  cannibalization: Cannibalization | null;
  risks?: string[];
  data_freshness?: DataFreshnessEntry[];
}

export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type DataTier = "T0" | "T1" | "T2";

/**
 * GET /predictions/{run_id}. Acts as the "manifest" gate for the map: only
 * register the vector tile source once status === 'succeeded'. The contract
 * has no separate tile-manifest endpoint, so the tile URL template is
 * derived here from the documented pattern
 * (/predictions/{run_id}/tiles/{z}/{x}/{y}.mvt) rather than returned by the
 * API. Flagged in console/RECONCILIATION.md as worth confirming with backend
 * if a real TileJSON manifest endpoint ever gets added.
 */
export interface RunManifest {
  run_id: string;
  status: RunStatus;
  region_count: number;
  model_version: string;
  feature_as_of: string;
  data_tier: DataTier;
  tileUrlTemplate: string;
  summary?: {
    top_region: { region_id: string; name: string; opportunity_score: number };
    score_distribution: { p25: number; p50: number; p75: number };
    low_confidence_region_count: number;
  };
  warnings?: string[];
  expires_at?: string;
}
