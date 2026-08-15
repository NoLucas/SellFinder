// VF 5.6a - does C's ACTUAL response payload type-check against D's parser types?
// Imports D's contract-derived types verbatim; imports C's samples verbatim.
import scoresSample from "../../backend/samples/scores.json";
import manifestSample from "../../backend/samples/manifest.json";
import type { RegionScoresPayload, BasemapManifest } from "../../console/src/lib/api/types";

// If C's payload does not satisfy D's parser type, these lines fail to compile.
const scores: RegionScoresPayload = scoresSample as unknown as RegionScoresPayload;
const manifest: BasemapManifest = manifestSample as unknown as BasemapManifest;

// Structural check WITHOUT the escape-hatch cast: this is the real test.
const scoresStrict: RegionScoresPayload = scoresSample;
const manifestStrict: BasemapManifest = manifestSample;

export { scores, manifest, scoresStrict, manifestStrict };
