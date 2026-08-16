/**
 * DISPATCH-2 §6 5차 (ADR-003 §1 / D-16): `region_scope` is a set of
 * region_id PREFIX codes ("41" matches "41135"); empty = full access. The
 * server is the real enforcement point (ADR-003 §4 — every query/export/
 * tile path must apply it) — this module is display-only. Its job is
 * narrower but still real: an out-of-scope region and a genuinely
 * score-less region both end up absent from `scoresPayload.scores`, and
 * without this, the client can't tell them apart, so it CANNOT be honest
 * about which one a blank region is. "권한 밖" and "데이터 없음" are
 * different states and must render differently.
 */

export function isRegionIdInScope(regionId: string, regionScope: readonly string[]): boolean {
  return regionScope.length === 0 || regionScope.some((prefix) => regionId.startsWith(prefix));
}

/** Muted cool slate — deliberately NOT scoreScale.ts's NO_DATA_FILL (a warm beige), so "no permission" can never be mistaken for "no data" at a glance. */
export const OUT_OF_SCOPE_FILL = "#c3c8d4";

/**
 * MapLibre boolean expression: true when the feature's `region_id`
 * property starts with one of `regionScope`'s prefixes. `slice` on a
 * string is part of the GL style spec (not array-only), so this needs no
 * custom string-matching plugin.
 */
export function regionScopeMatchExpression(regionScope: readonly string[]): unknown {
  if (regionScope.length === 0) return true;
  return [
    "any",
    ...regionScope.map((prefix) => [
      "==",
      ["slice", ["to-string", ["get", "region_id"]], 0, prefix.length],
      prefix,
    ]),
  ];
}

/**
 * Wraps a score fill-color expression (scoreFillExpression's output) with
 * an out-of-scope guard evaluated FIRST — an out-of-scope region has no
 * score either (the server should never send one), so without this guard
 * it would silently fall through to the same NO_DATA_FILL as a genuinely
 * unscored in-scope region. Kept separate from scoreScale.ts on purpose:
 * that module's tests/contract stay score-only, this concern is orthogonal.
 */
export function withRegionScopeGuard(scoreExpr: unknown[], regionScope: readonly string[]): unknown[] {
  if (regionScope.length === 0) return scoreExpr;
  return ["case", ["!", regionScopeMatchExpression(regionScope)], OUT_OF_SCOPE_FILL, scoreExpr];
}
