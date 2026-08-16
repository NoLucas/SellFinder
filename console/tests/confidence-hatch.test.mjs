/**
 * D-3 (orchestrator/DISPATCH-2.md §6, ADR-001): confidence='low' must be
 * distinguishable by a HATCH PATTERN, never by dimming/lightening the fill
 * color — a lighter shade of the same sequential ramp reads as "low score"
 * to a glancing user, not "low confidence" (hatchPattern.ts's own file
 * comment states this rationale). This is a real regression guard: it
 * fails if either expression starts reading the OTHER feature-state key.
 *
 * Imports the real production modules (scoreScale.ts, hatchPattern.ts) —
 * not reimplementations — and inspects the actual MapLibre expression
 * trees they build.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { scoreFillExpression } from "../src/lib/color/scoreScale.ts";
import { hatchOpacityExpression } from "../src/lib/map/hatchPattern.ts";

function containsKey(expr, key) {
  return JSON.stringify(expr).includes(JSON.stringify(key));
}

test("fill-color expression (region-fill layer) never reads confidence_level", () => {
  const expr = scoreFillExpression([0, 100]);
  assert.ok(containsKey(expr, "score"), "sanity: fill color must at least depend on score");
  assert.ok(
    !containsKey(expr, "confidence_level"),
    "fill-color must not branch on confidence_level — that would make low confidence look like a low score, not a pattern",
  );
});

test("hatch fill-opacity expression (region-hatch layer) reads ONLY confidence_level, gated on 'low', never on score", () => {
  const expr = hatchOpacityExpression();

  assert.deepEqual(expr, ["case", ["==", ["feature-state", "confidence_level"], "low"], 1, 0]);
  assert.ok(containsKey(expr, "confidence_level"));
  assert.ok(!containsKey(expr, ["feature-state", "score"]), "hatch visibility must not depend on score — it's a second, independent channel");
});

test("the two channels are structurally independent: fill color and hatch opacity read disjoint feature-state keys", () => {
  const fill = scoreFillExpression([0, 100]);
  const hatch = hatchOpacityExpression();

  assert.ok(containsKey(fill, ["feature-state", "score"]));
  assert.ok(!containsKey(fill, ["feature-state", "confidence_level"]));
  assert.ok(containsKey(hatch, ["feature-state", "confidence_level"]));
  assert.ok(!containsKey(hatch, ["feature-state", "score"]));
});
