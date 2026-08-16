/**
 * D-2 (orchestrator/DISPATCH.md §4, revised by DISPATCH 2차) — join pipeline
 * test, run by Node's built-in test runner (`node --test`). No reimplemented
 * stand-ins: this decodes A's REAL committed `.pmtiles` fixture (via
 * `pmtiles` + `@mapbox/vector-tile` + `pbf` — all already project
 * dependencies, `@mapbox/vector-tile`/`pbf` pinned as devDependencies since
 * this file is the first thing to import them directly) and runs it through
 * `scoreScale.ts`, the real production color module.
 *
 * Path covered: samples (JSON) -> schema-driven parser -> setFeatureState
 * key generation (promoteId + MapLibre's getId, copied verbatim — same
 * source verification/fixtures/vf_56_join.mjs used) -> fill expression.
 * Mirrors PredictionMap.tsx's join logic exactly; per ADR-005/D-20 that
 * logic itself does not change here.
 *
 * `resolveManifest()` is the single injection point DISPATCH's 2nd note
 * asked for: it prefers backend/samples/manifest.json once C repoints it at
 * this run's own level+vintage, and falls back to
 * data-platform/fixtures/manifest-fixture.json — today's actual integration
 * path — until then. `tile_url` is never hardcoded: the local file is
 * resolved from the manifest's own `tile_url` basename.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PMTiles } from "pmtiles";
import { VectorTile } from "@mapbox/vector-tile";
import Pbf from "pbf";

import { scoreFillExpression, NO_DATA_FILL } from "../src/lib/color/scoreScale.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, "..", ".."); // repo root — console/ is read/write, everything else read-only
const readJSON = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));

// --- MapLibre FeatureIndex.getId, verbatim ---
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

/**
 * Single injection point for "which manifest describes the tile source".
 * Prefers backend/samples/manifest.json — the shape D's real client code
 * actually fetches — but only once it agrees with this run's own
 * level/vintage. Today (DISPATCH 2차) it still advertises adm_dong /
 * 2026-01-01 against scores.json's sigungu / fixture, so this falls back
 * to A's fixture manifest, the real current integration path. No code
 * change is needed here once C fixes it — this function just starts
 * returning the backend one.
 */
function resolveManifest(scoresPayload) {
  const backendManifest = readJSON("backend/samples/manifest.json");
  if (
    backendManifest.level === scoresPayload.region_level &&
    backendManifest.boundary_vintage === scoresPayload.boundary_vintage
  ) {
    return { manifest: backendManifest, manifestPath: "backend/samples/manifest.json" };
  }
  const fixtureManifest = readJSON("data-platform/fixtures/manifest-fixture.json");
  return { manifest: fixtureManifest, manifestPath: "data-platform/fixtures/manifest-fixture.json" };
}

/**
 * Local bytes for `manifest.tile_url` — never a hardcoded filename. A
 * publishes committed fixtures under data-platform/fixtures/ and gitignored
 * local builds under data-platform/output/tiles/ (ADR-002/D-11); a real CDN
 * URL isn't fetched here, only its basename is used to find the same file
 * locally (mirrors what C's dev server does when serving `/artifacts/`).
 */
function resolveLocalTilePath(manifest) {
  const basename = path.basename(manifest.tile_url);
  const candidates = [
    path.join(ROOT, "data-platform", "fixtures", basename),
    path.join(ROOT, "data-platform", "output", "tiles", basename),
  ];
  const found = candidates.find((p) => fs.existsSync(p));
  if (!found) {
    throw new Error(
      `manifest.tile_url=${manifest.tile_url} -> basename "${basename}" not found locally in: ${candidates.join(", ")}`,
    );
  }
  return found;
}

class NodeFileSource {
  constructor(filePath) {
    this.filePath = filePath;
  }
  getKey() {
    return this.filePath;
  }
  async getBytes(offset, length) {
    const handle = await fsp.open(this.filePath, "r");
    try {
      const buf = Buffer.alloc(length);
      await handle.read(buf, 0, length, offset);
      return { data: buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) };
    } finally {
      await handle.close();
    }
  }
}

/**
 * Decodes the first non-empty tile for `sourceLayer`, scanning the archive's
 * own header zoom range low-to-high (same brute-force approach as
 * verification/fixtures/vf_56_tile_probe.py). Fixture archives are small
 * (<5MB, single low-zoom tile covering all of Korea) so this stays fast.
 */
async function readFirstTileFeatures(tilePath, sourceLayer) {
  const pm = new PMTiles(new NodeFileSource(tilePath));
  const header = await pm.getHeader();
  for (let z = header.minZoom; z <= header.maxZoom; z++) {
    const n = 2 ** z;
    for (let x = 0; x < n; x++) {
      for (let y = 0; y < n; y++) {
        const res = await pm.getZxy(z, x, y);
        if (!res) continue;
        const tile = new VectorTile(new Pbf(new Uint8Array(res.data)));
        const layer = tile.layers[sourceLayer];
        if (!layer || layer.length === 0) continue;
        const features = [];
        for (let i = 0; i < layer.length; i++) {
          const f = layer.feature(i);
          features.push({ id: f.id, properties: f.properties });
        }
        return { z, x, y, features };
      }
    }
  }
  throw new Error(`no non-empty tile found for layer "${sourceLayer}" in ${tilePath} (zoom ${header.minZoom}-${header.maxZoom})`);
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

test("join: A's real committed .pmtiles fixture matches C's real scores.json, end to end (ADR-005 / D-5 readiness)", async () => {
  const scores = readJSON("backend/samples/scores.json");
  const { manifest, manifestPath } = resolveManifest(scores);
  const tilePath = resolveLocalTilePath(manifest);
  const featureState = buildFeatureState(scores);

  const { z, x, y, features } = await readFirstTileFeatures(tilePath, manifest.source_layer);
  assert.ok(features.length > 0, `tile z${z}/${x}/${y} in ${tilePath} has no features in layer "${manifest.source_layer}"`);

  const promoteId = { [manifest.source_layer]: manifest.feature_id_property };
  let matched = 0;
  for (const f of features) {
    const promoted = getId(f, manifest.source_layer, promoteId);
    if (featureState.has(String(promoted))) matched++;
  }

  // Real regression guard, not a synthetic stand-in: if A's tile stops
  // carrying region_id in properties, or someone reverts D's promoteId join
  // (D-1/ADR-005), matched drops below scores.length and this fails — that
  // failure IS VF-009 closing the gap the verifier found.
  assert.equal(
    matched,
    scores.scores.length,
    `expected all ${scores.scores.length} scored regions to match against ${manifestPath} ` +
      `(tile_url=${manifest.tile_url}, resolved locally to ${tilePath}), got ${matched}/${features.length} tile features`,
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
