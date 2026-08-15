/**
 * VF 5.6c - end-to-end join: C's real /scores + C's real /basemap manifest
 * + A's real .pmtiles features, run through D's ACTUAL logic.
 *
 * D's code used verbatim:
 *   - PredictionMap.tsx promoteId + setFeatureState join (lines 100, 143-150)
 *   - scoreScale.ts scoreFillExpression / NO_DATA_FILL
 * MapLibre's getId() copied verbatim from
 *   console/node_modules/maplibre-gl/dist/maplibre-gl-dev.js:31486-31495
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const R = path.resolve(here, "..", "..");
const read = (p) => JSON.parse(fs.readFileSync(path.join(R, p), "utf8"));

const scores   = read("backend/samples/scores.json");
const manifest = read("backend/samples/manifest.json");
const tileFeatures = read("verification/fixtures/a_tile_features.json");

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

// --- D's PredictionMap.tsx, verbatim ---
const promoteId = { [manifest.source_layer]: manifest.feature_id_property };
const idIdx    = scores.schema.indexOf("region_id");
const scoreIdx = scores.schema.indexOf("opportunity_score");
const confIdx  = scores.schema.indexOf("confidence_level");

// MapLibre keys feature state by String(featureId)
// (maplibre-gl-dev.js:40589 `const feature = String(featureId)`), so int vs
// string ids are NOT a mismatch. Harness mirrors that coercion exactly.
const featureState = new Map();
for (const row of scores.scores) {
  featureState.set(String(row[idIdx]), { score: row[scoreIdx], confidence_level: row[confIdx] });
}

console.log(`manifest.feature_id_property = ${JSON.stringify(manifest.feature_id_property)}`);
console.log(`D promoteId                  = ${JSON.stringify(promoteId)}`);
console.log(`scores region_ids            = ${scores.scores.map(r => r[idIdx]).join(", ")}`);
console.log(`tile feature ids (A, real)   = ${tileFeatures.map(f => JSON.stringify(f.id)).join(", ")}`);
console.log(`tile feature properties keys = ${JSON.stringify(Object.keys(tileFeatures[0].properties))}`);
console.log("");

let matched = 0, promotedUndefined = 0;
for (const f of tileFeatures) {
  const promoted = getId(f, manifest.source_layer, promoteId);
  if (promoted === undefined) promotedUndefined++;
  const state = featureState.get(String(promoted));
  if (state) matched++;
  console.log(`  tile feature id=${JSON.stringify(f.id)} -> promoteId gives ${JSON.stringify(promoted)} -> featureState ${state ? "HIT" : "MISS"}`);
}

console.log("");
console.log(`features whose promoted id is undefined : ${promotedUndefined}/${tileFeatures.length}`);
console.log(`features that received a score          : ${matched}/${tileFeatures.length}`);

// D's own fill expression: what colour does an unmatched feature get?
const NO_DATA_FILL = "#e1e0d9";
console.log(`unmatched features render as            : ${NO_DATA_FILL} (scoreScale.ts NO_DATA_FILL)`);
console.log("");
console.log(matched === 0
  ? "RESULT: every region paints NO_DATA grey. No error thrown, no console warning - silent blank map."
  : `RESULT: ${matched} region(s) painted.`);

// Counterfactual: if promoteId were dropped (native MVT id used instead),
// would the join succeed? Isolates defect #1 from defect #2.
let cfMatched = 0;
for (const f of tileFeatures) {
  if (featureState.get(String(getId(f, manifest.source_layer, null)))) cfMatched++;
}
console.log("");
console.log("--- counterfactual: promoteId removed, native MVT feature id used ---");
console.log(`  matched: ${cfMatched}/${tileFeatures.length}`);
console.log(cfMatched === 0
  ? "  still 0 - a SECOND independent mismatch: C scores declare region_level=adm_dong but carry 5-digit sigungu codes (41135/11650/...), while A publishes only sido (11/26/...)."
  : "  join would succeed - promoteId is the sole defect.");
