/**
 * D-2 (orchestrator/DISPATCH.md §4) — join pipeline test, run by Node's
 * built-in test runner (`node --test`, ships with Node itself; no new
 * devDependency). Node 24 natively type-strips `.ts` on import, so this
 * exercises D's REAL production module (`scoreScale.ts`) rather than a
 * reimplementation of it.
 *
 * Path covered: samples (JSON) -> schema-driven parser -> setFeatureState
 * key generation (promoteId + MapLibre's getId) -> fill expression. Mirrors
 * PredictionMap.tsx lines ~100-154 exactly; `getId` below is MapLibre's
 * FeatureIndex.getId copied verbatim, same as verification/fixtures/
 * vf_56_join.mjs (the reference implementation DISPATCH.md points at) —
 * per ADR-005 / D-20, this join logic itself does not change.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { scoreFillExpression, NO_DATA_FILL } from "../src/lib/color/scoreScale.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "..", ".."); // repo root — console/ is read/write, everything else read-only
const readJSON = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));

// --- MapLibre FeatureIndex.getId, verbatim (see vf_56_join.mjs header comment for source lines) ---
function getId(feature, sourceLayerId, promoteId) {
  let id = feature.id;
  if (promoteId) {
    const propName = typeof promoteId === "string" ? promoteId : promoteId[sourceLayerId];
    id = feature.properties[propName];
    if (typeof id === "boolean") id = Number(id);
  }
  return id;
}

// --- PredictionMap.tsx's own join logic, verbatim (schema-driven indices + String(id) keying) ---
function buildFeatureState(scoresPayload) {
  const idIdx = scoresPayload.schema.indexOf("region_id");
  const scoreIdx = scoresPayload.schema.indexOf("opportunity_score");
  const confIdx = scoresPayload.schema.indexOf("confidence_level");
  const featureState = new Map();
  for (const row of scoresPayload.scores) {
    featureState.set(String(row[idIdx]), { score: row[scoreIdx], confidence_level: row[confIdx] });
  }
  return featureState;
}

test("parser: real backend/samples/scores.json -> setFeatureState map keyed by String(region_id)", () => {
  const scores = readJSON("backend/samples/scores.json");
  const state = buildFeatureState(scores);

  assert.equal(state.size, scores.scores.length, "one feature-state entry per score row");
  for (const row of scores.scores) {
    const [regionId, score, confidence] = row;
    assert.ok(state.has(String(regionId)), `missing key for region_id ${regionId}`);
    assert.deepEqual(state.get(String(regionId)), { score, confidence_level: confidence });
  }
});

test("join: promoteId (from real manifest) resolves every feature on a correctly-shaped tile (ADR-005 target)", () => {
  const scores = readJSON("backend/samples/scores.json");
  const manifest = readJSON("backend/samples/manifest.json");
  const featureState = buildFeatureState(scores);

  // ADR-005: region_id must sit in tile `properties`, as a literal string.
  // This models what A's fixed .pmtiles output is required to look like —
  // it is deliberately NOT verification/fixtures/a_tile_features.json
  // (A's pre-fix output, see the next test) so this test stays a stable
  // regression guard on D's own join code, independent of A/C's rollout.
  const correctTileFeatures = scores.scores.map(([regionId], i) => ({
    layer: manifest.source_layer,
    id: 1000 + i, // native MVT id present but NOT the join key (ADR-005 pt.3)
    properties: { region_id: regionId, name: `region-${i}` },
  }));

  const promoteId = { [manifest.source_layer]: manifest.feature_id_property };
  let matched = 0;
  for (const f of correctTileFeatures) {
    const promoted = getId(f, manifest.source_layer, promoteId);
    if (featureState.has(String(promoted))) matched++;
  }

  assert.equal(matched, correctTileFeatures.length, "every correctly-shaped tile feature must resolve to a score");
});

test("join: today's real A tile fixture (pre-ADR-005-fix) still yields zero matches — VF-003 / D-5 gate, not a bug in D", () => {
  const scores = readJSON("backend/samples/scores.json");
  const manifest = readJSON("backend/samples/manifest.json");
  const featureState = buildFeatureState(scores);
  const realTileFeatures = readJSON("verification/fixtures/a_tile_features.json");

  const promoteId = { [manifest.source_layer]: manifest.feature_id_property };
  let matched = 0;
  for (const f of realTileFeatures) {
    const promoted = getId(f, manifest.source_layer, promoteId);
    if (featureState.has(String(promoted))) matched++;
  }

  // This assertion doubles as the D-5 readiness check DISPATCH.md asked to
  // poll for via `node verification/fixtures/vf_56_join.mjs`. Once A ships
  // region_id-in-properties tiles (and C points the manifest at them), this
  // starts failing with matched > 0 — that failure is the signal to start
  // D-5 (full-artifact integration), not a regression to fix here.
  assert.equal(
    matched,
    0,
    `expected 0/${realTileFeatures.length} against A's pre-fix tile fixture, got ${matched} — ` +
      `if this changed, A/C shipped the ADR-005 fix; proceed to D-5, do not "fix" this test`,
  );
});

test("fill expression: real scoreScale.ts wires NO_DATA_FILL as the null-state fallback and spans the real score_range", () => {
  const scores = readJSON("backend/samples/scores.json");
  const expr = scoreFillExpression([scores.score_range.min, scores.score_range.max]);

  assert.equal(expr[0], "case");
  assert.deepEqual(expr[1], ["==", ["feature-state", "score"], null]);
  assert.equal(expr[2], NO_DATA_FILL);

  const interpolate = expr[3];
  assert.equal(interpolate[0], "interpolate");
  const stops = interpolate.slice(3);
  assert.equal(stops[0], scores.score_range.min, "first stop must be the run's actual score_range.min");
  assert.equal(stops[stops.length - 2], scores.score_range.max, "last stop must be the run's actual score_range.max");
});
