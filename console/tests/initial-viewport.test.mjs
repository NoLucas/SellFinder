/**
 * D-16 (orchestrator DISPATCH-2 §6 5차): a region_scope-restricted user
 * must not open the map to a blank screen they have to pan away from.
 * Tests the real production module (src/lib/map/initialViewport.ts).
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { computeInitialViewport, DEFAULT_VIEWPORT } from "../src/lib/map/initialViewport.ts";

test("empty region_scope (full access) uses the whole-Korea default viewport", () => {
  assert.deepEqual(computeInitialViewport([]), DEFAULT_VIEWPORT);
});

test("a single recognized sido prefix frames that province, not all of Korea", () => {
  const viewport = computeInitialViewport(["41"]);
  assert.notDeepEqual(viewport, DEFAULT_VIEWPORT);
  assert.ok(viewport.zoom > DEFAULT_VIEWPORT.zoom, "a single-province scope should be zoomed in further than the whole-country default");
});

test("a longer (sigungu-length) prefix still resolves via its sido's first 2 digits", () => {
  // 41135 = 경기도 성남시 분당구 — same viewport as scope=["41"]
  assert.deepEqual(computeInitialViewport(["41135"]), computeInitialViewport(["41"]));
});

test("multiple recognized prefixes average their centers and zoom out from the tightest one", () => {
  const seoul = computeInitialViewport(["11"]);
  const busan = computeInitialViewport(["26"]);
  const combined = computeInitialViewport(["11", "26"]);

  assert.notDeepEqual(combined, seoul);
  assert.notDeepEqual(combined, busan);
  assert.ok(combined.zoom < Math.min(seoul.zoom, busan.zoom), "combining two provinces must zoom out, not in");
});

test("an unrecognized prefix never guesses — falls back to the whole-Korea default", () => {
  assert.deepEqual(computeInitialViewport(["99"]), DEFAULT_VIEWPORT);
});
