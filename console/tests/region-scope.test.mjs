/**
 * D-16 (orchestrator DISPATCH-2 §6 5차, ADR-003 §1): region_scope is a
 * prefix-match allowlist; empty = full access. This tests the REAL
 * production module (src/lib/map/regionScope.ts) that PredictionMap.tsx's
 * click guard and fill-color expression both call — not a reimplementation.
 *
 * The core property under test: an out-of-scope region and a genuinely
 * score-less in-scope region must be DISTINGUISHABLE, both in the click
 * guard (isRegionIdInScope) and in the paint expression (the guard must
 * short-circuit BEFORE the NO_DATA_FILL branch, not after).
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  isRegionIdInScope,
  OUT_OF_SCOPE_FILL,
  regionScopeMatchExpression,
  withRegionScopeGuard,
} from "../src/lib/map/regionScope.ts";
import { NO_DATA_FILL, scoreFillExpression } from "../src/lib/color/scoreScale.ts";

test("isRegionIdInScope: empty scope is full access, non-empty scope is prefix-match only", () => {
  assert.equal(isRegionIdInScope("41135", []), true);
  assert.equal(isRegionIdInScope("41135", ["41"]), true);
  assert.equal(isRegionIdInScope("41135", ["11"]), false);
  assert.equal(isRegionIdInScope("41135", ["11", "41"]), true, "any matching prefix is enough");
  assert.equal(isRegionIdInScope("11650", ["41"]), false);
});

test("regionScopeMatchExpression: empty scope compiles to the literal `true` (no guard needed)", () => {
  assert.equal(regionScopeMatchExpression([]), true);
});

test("regionScopeMatchExpression: non-empty scope produces an 'any' of prefix slice-equality checks", () => {
  const expr = regionScopeMatchExpression(["41", "11"]);
  assert.deepEqual(expr, [
    "any",
    ["==", ["slice", ["to-string", ["get", "region_id"]], 0, 2], "41"],
    ["==", ["slice", ["to-string", ["get", "region_id"]], 0, 2], "11"],
  ]);
});

test("withRegionScopeGuard: empty scope returns the score expression completely unchanged", () => {
  const scoreExpr = scoreFillExpression([0, 100]);
  assert.equal(withRegionScopeGuard(scoreExpr, []), scoreExpr);
});

test("withRegionScopeGuard: non-empty scope wraps with an out-of-scope branch evaluated BEFORE the score expression", () => {
  const scoreExpr = scoreFillExpression([0, 100]);
  const guarded = withRegionScopeGuard(scoreExpr, ["41"]);

  assert.equal(guarded[0], "case");
  assert.deepEqual(guarded[1], ["!", regionScopeMatchExpression(["41"])]);
  assert.equal(guarded[2], OUT_OF_SCOPE_FILL);
  assert.equal(guarded[3], scoreExpr, "the nested else-branch is the ORIGINAL score expression, untouched");
});

test("OUT_OF_SCOPE_FILL is a distinct color from NO_DATA_FILL — 권한 밖 must never look like 데이터 없음", () => {
  assert.notEqual(OUT_OF_SCOPE_FILL, NO_DATA_FILL);
});
