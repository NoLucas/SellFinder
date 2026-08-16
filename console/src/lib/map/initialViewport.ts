/**
 * DISPATCH-2 §6 5차 (ADR-003/D-16): "범위가 좁은 사용자가 지도를 처음 열었을
 * 때 빈 화면을 보지 않도록 초기 뷰포트를 그 범위에 맞춰라." A `region_scope`
 * user whose whole territory is one province shouldn't have to manually pan
 * there past a screen of out-of-scope grey.
 *
 * The centers/zooms below are coarse, well-known public sido-level
 * geography (not model output, not invented data) used ONLY to frame the
 * initial camera — never for scoring, joining, or anything data-bearing.
 * `region_scope` prefixes can be longer than 2 digits (sigungu, adm_dong),
 * but Korean administrative codes are hierarchical: the first 2 digits are
 * always the sido, so slicing to 2 chars is a safe, lossless lookup key
 * regardless of the prefix's actual granularity.
 */

export interface Viewport {
  center: [number, number];
  zoom: number;
}

/** Whole-Korea framing — unchanged from PredictionMap.tsx's prior hardcoded default. */
export const DEFAULT_VIEWPORT: Viewport = { center: [127.8, 36.5], zoom: 6.3 };

const SIDO_VIEWPORT_BY_CODE: Record<string, Viewport> = {
  "11": { center: [126.98, 37.57], zoom: 10 }, // 서울특별시
  "26": { center: [129.08, 35.18], zoom: 10 }, // 부산광역시
  "27": { center: [128.6, 35.87], zoom: 10 }, // 대구광역시
  "28": { center: [126.7, 37.46], zoom: 9.5 }, // 인천광역시
  "29": { center: [126.85, 35.16], zoom: 10 }, // 광주광역시
  "30": { center: [127.38, 36.35], zoom: 10 }, // 대전광역시
  "31": { center: [129.31, 35.54], zoom: 10 }, // 울산광역시
  "36": { center: [127.29, 36.48], zoom: 10.5 }, // 세종특별자치시
  "41": { center: [127.15, 37.41], zoom: 8 }, // 경기도
  "42": { center: [128.2, 37.85], zoom: 7.5 }, // 강원특별자치도
  "43": { center: [127.7, 36.8], zoom: 8 }, // 충청북도
  "44": { center: [126.8, 36.6], zoom: 8 }, // 충청남도
  "45": { center: [127.15, 35.72], zoom: 8 }, // 전북특별자치도
  "46": { center: [126.99, 34.85], zoom: 7.5 }, // 전라남도
  "47": { center: [128.9, 36.4], zoom: 7.5 }, // 경상북도
  "48": { center: [128.2, 35.26], zoom: 8 }, // 경상남도
  "50": { center: [126.53, 33.38], zoom: 9.5 }, // 제주특별자치도
};

/**
 * Empty scope (full access) or every prefix unrecognized -> DEFAULT_VIEWPORT
 * (never guess further than the known sido table). One matched sido ->
 * that sido's own framing. Multiple -> centroid of the matches, zoomed out
 * one step from the tightest of them so the combined area is more likely
 * to fit — a heuristic for "not blank on first paint", not precise framing.
 */
export function computeInitialViewport(regionScope: readonly string[]): Viewport {
  if (regionScope.length === 0) return DEFAULT_VIEWPORT;

  const matches = regionScope
    .map((prefix) => SIDO_VIEWPORT_BY_CODE[prefix.slice(0, 2)])
    .filter((v): v is Viewport => v !== undefined);
  const [only] = matches;
  if (matches.length === 1 && only) return only;
  if (matches.length === 0) return DEFAULT_VIEWPORT;

  const lon = matches.reduce((sum, m) => sum + m.center[0], 0) / matches.length;
  const lat = matches.reduce((sum, m) => sum + m.center[1], 0) / matches.length;
  const tightestZoom = Math.min(...matches.map((m) => m.zoom));
  return { center: [lon, lat], zoom: Math.max(tightestZoom - 1, 5) };
}
