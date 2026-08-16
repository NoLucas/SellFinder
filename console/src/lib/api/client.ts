import type {
  BasemapManifest,
  PredictionDetail,
  RegionLevel,
  RegionScore,
  RegionScorePage,
  RegionScoresPayload,
  RunSummary,
} from "./types";

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

async function throwApiError(res: Response): Promise<never> {
  const body = (await res.json().catch(() => null)) as { error?: { code: string; message: string; request_id: string } } | null;
  throw new ApiError(
    body?.error?.message ?? res.statusText,
    body?.error?.code ?? "UNKNOWN",
    body?.error?.request_id ?? "unknown",
    res.status,
  );
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
  if (!res.ok) return throwApiError(res);
  return res.json() as Promise<T>;
}

/** For endpoints that issue a token in the first place — no Authorization header to send yet. */
async function postJSONUnauthenticated<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) return throwApiError(res);
  return res.json() as Promise<T>;
}

/** GET /predictions/{run_id} — status/summary, not the map data path itself. */
export function getRunSummary(runId: string, token: string): Promise<RunSummary> {
  return fetchJSON<RunSummary>(`/predictions/${runId}`, token);
}

/**
 * GET /basemap/regions/manifest (ADR-001-map-tiles.md). Static + cacheable,
 * tenant-agnostic.
 *
 * For the run's OWN region_level, always pass the `boundary_vintage` the
 * scores payload reports, never "latest" — a reopened run's regions must be
 * painted against the boundary they were scored on, not one that has since
 * moved (redistricting). `vintage` is only omittable (contract default:
 * latest) when browsing a level the run wasn't scored at (D-14 level
 * picker) — there is no stored vintage to protect in that case.
 */
export function getBasemapManifest(
  level: RegionLevel,
  vintage: string | undefined,
  token: string,
): Promise<BasemapManifest> {
  const params = new URLSearchParams({ level });
  if (vintage) params.set("vintage", vintage);
  return fetchJSON<BasemapManifest>(`/basemap/regions/manifest?${params.toString()}`, token);
}

/**
 * GET /predictions/{run_id}/scores (ADR-001-map-tiles.md) — the map's score
 * source. Deliberately not paginated (documented exception to the API's
 * cursor-pagination rule): the map needs every region at once. Do not call
 * listAllRegionScores() for map rendering — that endpoint is for the
 * region-list/table view and carries revenue, which this one intentionally
 * omits.
 */
export function getRegionScores(
  runId: string,
  token: string,
  query: { productId?: string; channel?: string } = {},
): Promise<RegionScoresPayload> {
  const params = new URLSearchParams();
  if (query.productId) params.set("product_id", query.productId);
  if (query.channel) params.set("channel", query.channel);
  const qs = params.toString();
  return fetchJSON<RegionScoresPayload>(`/predictions/${runId}/scores${qs ? `?${qs}` : ""}`, token);
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

export interface DevTokenRequest {
  tenantId: string;
  role?: string;
  regionScope?: string[];
}

export interface DevTokenResponse {
  accessToken: string;
}

/**
 * POST /v1/dev/token (ADR-003 "개발 중 임시 조치"). Registered by backend
 * only when SELLFINDER_ENV=development — a 404 here in a real deployment
 * means the dev escape hatch correctly doesn't exist, not a bug to route
 * around. Stand-in for the real magic-link verify call (LoginPanel.tsx is
 * the swap point once that endpoint exists, not this function).
 */
export async function requestDevToken({ tenantId, role = "analyst", regionScope = [] }: DevTokenRequest): Promise<DevTokenResponse> {
  const res = await postJSONUnauthenticated<{ access_token: string }>("/dev/token", {
    tenant_id: tenantId,
    role,
    region_scope: regionScope,
  });
  return { accessToken: res.access_token };
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
