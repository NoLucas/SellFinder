import type { PredictionDetail, RegionScore, RegionScorePage, RunManifest } from "./types";

/**
 * shared/contracts/04_api_contract.yaml `servers[0].url`. Overridable per env
 * so local/staging can point elsewhere without touching contract-derived code.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://api.sellfinder.kr/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly requestId: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchJSON<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { error?: { code: string; message: string; request_id: string } } | null;
    throw new ApiError(
      body?.error?.message ?? res.statusText,
      body?.error?.code ?? "UNKNOWN",
      body?.error?.request_id ?? "unknown",
      res.status,
    );
  }
  return res.json() as Promise<T>;
}

/**
 * Reads the run summary and gates the map on it: only 'succeeded' runs have
 * renderable tiles. See the doc comment on RunManifest for why the tile URL
 * template is computed here instead of read from the response.
 */
export async function getRunManifest(runId: string, token: string): Promise<RunManifest> {
  const summary = await fetchJSON<Omit<RunManifest, "tileUrlTemplate">>(`/predictions/${runId}`, token);
  return {
    ...summary,
    tileUrlTemplate: `${API_BASE}/predictions/${runId}/tiles/{z}/{x}/{y}.mvt`,
  };
}

export interface RegionScoreQuery {
  sort?: "score_desc" | "revenue_desc" | "profit_desc";
  minConfidence?: "low" | "medium" | "high";
}

/**
 * Walks GET /predictions/{run_id}/regions cursor pagination to completion
 * and returns the full score array — this is the "scores" side of the map
 * join, kept separate from tile geometry so scores can refresh without
 * re-fetching vector tiles.
 */
export async function listAllRegionScores(
  runId: string,
  token: string,
  query: RegionScoreQuery = {},
): Promise<RegionScore[]> {
  const scores: RegionScore[] = [];
  let cursor: string | null = null;

  do {
    const params = new URLSearchParams({ limit: "1000" });
    if (query.sort) params.set("sort", query.sort);
    if (query.minConfidence) params.set("min_confidence", query.minConfidence);
    if (cursor) params.set("cursor", cursor);

    const page: RegionScorePage = await fetchJSON<RegionScorePage>(
      `/predictions/${runId}/regions?${params.toString()}`,
      token,
    );
    scores.push(...page.data);
    cursor = page.next_cursor;
  } while (cursor);

  return scores;
}

/** GET /predictions/{run_id}/regions/{region_id} — only called on map click. */
export function getRegionDetail(runId: string, regionId: string, token: string): Promise<PredictionDetail> {
  return fetchJSON<PredictionDetail>(`/predictions/${runId}/regions/${regionId}`, token);
}

/**
 * MapLibre `transformRequest`: attaches the bearer token to tile/API
 * requests without putting it in the tile URL (query-string tokens end up
 * in browser history, proxy logs, and cached tile URLs — a header does
 * not). Only applied to our own API host.
 */
export function authTransformRequest(token: string) {
  return (url: string) => {
    if (url.startsWith(API_BASE)) {
      return { url, headers: { Authorization: `Bearer ${token}` } };
    }
    return { url };
  };
}
