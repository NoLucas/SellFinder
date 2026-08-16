/**
 * D-2 (orchestrator/DISPATCH-2.md §6, 05_scoring_spec.md §2): T0 tenants
 * (data_tier=T0, expected_revenue_krw === null) must never see a fabricated
 * amount in the revenue slot — never "0", never "-". They get the exact UI
 * copy the contract specifies ("상대적 유망도 랭킹") plus an upload nudge.
 *
 * Imports the REAL production function (src/lib/format/revenue.ts) — the
 * one RegionDetailPanel.tsx actually calls — not a reimplementation.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { formatRevenueDisplay, T0_UPLOAD_NUDGE } from "../src/lib/format/revenue.ts";

test("T0 (null expected_revenue_krw): never renders as a numeric range, never literally '0' or '-'", () => {
  const display = formatRevenueDisplay(null);

  assert.equal(display.kind, "unavailable", "null revenue must take the unavailable branch, not the numeric one");
  assert.equal(display.message, T0_UPLOAD_NUDGE);
  assert.ok(display.message.includes("상대적 유망도 랭킹"), "must use the contract's exact T0 UI copy (05_scoring_spec.md §2)");
  assert.notEqual(display.message.trim(), "0");
  assert.notEqual(display.message.trim(), "-");
  assert.doesNotMatch(display.message, /^[\s0-]*$/, "message must be real copy, not a blank/zero/dash placeholder");
});

test("T1/T2 (populated expected_revenue_krw): renders the actual p10/p50/p90 range, not the T0 copy", () => {
  const display = formatRevenueDisplay({ p10: 18_400_000, p50: 31_200_000, p90: 52_600_000 });

  assert.equal(display.kind, "range");
  assert.ok(display.p50Label.includes("31,200,000") || /31,200,000/.test(display.p50Label), "p50 must reflect the actual value passed in, not a placeholder");
  assert.ok(display.rangeLabel.includes("~"), "range must show both p10 and p90, not just p50");
});
