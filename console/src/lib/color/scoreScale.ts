/**
 * opportunity_score → fill color, on a scale fixed to the run's own
 * `score_range` (GET /predictions/{run_id}/scores, ADR-001-map-tiles.md) —
 * never recomputed from whatever regions happen to be in view. ADR-001 is
 * explicit about why: if the client derived min/max from its own data, the
 * scale would shift every time a filter (channel, objective, product)
 * changes the visible set, and colors would stop being comparable across
 * views of the same run.
 *
 * Ramp is the dataviz skill's validated sequential "blue" hue
 * (references/palette.md, steps 100→700), reused verbatim. It is a single
 * hue light→dark with no new hues introduced, so it doesn't need a fresh
 * CVD-pair validation run — that check is for categorical palettes.
 */

const SEQUENTIAL_BLUE_STEPS = [
  "#cde2fb", // 100
  "#b7d3f6", // 150
  "#9ec5f4", // 200
  "#86b6ef", // 250
  "#6da7ec", // 300
  "#5598e7", // 350
  "#3987e5", // 400
  "#2a78d6", // 450
  "#256abf", // 500
  "#1c5cab", // 550
  "#184f95", // 600
  "#104281", // 650
  "#0d366b", // 700
] as const;

export type ScoreDomain = readonly [min: number, max: number];

/** Color for a region that has no joined score yet (tile loaded, scores not). */
export const NO_DATA_FILL = "#e1e0d9"; // chart chrome gridline/hairline token

/** Guards against a degenerate (min === max) domain, which breaks a linear interpolation. */
function widenIfDegenerate([min, max]: ScoreDomain): ScoreDomain {
  return max > min ? [min, max] : [min, min + 1];
}

/** Plain hex lookup for legend swatches / non-map UI (React, canvas, etc). */
export function scoreToFillColor(score: number, domain: ScoreDomain): string {
  const [min, max] = widenIfDegenerate(domain);
  const clamped = Math.min(max, Math.max(min, score));
  const stepCount = SEQUENTIAL_BLUE_STEPS.length;
  const t = (clamped - min) / (max - min);
  const index = Math.round(t * (stepCount - 1));
  return SEQUENTIAL_BLUE_STEPS[index] ?? NO_DATA_FILL;
}

/**
 * MapLibre `fill-color` expression, keyed off feature-state (the join target
 * for setFeatureState, not a tile property) so scores can be re-joined
 * without re-fetching tiles. `["feature-state", "score"]` is `null` for
 * regions setFeatureState hasn't reached yet, hence the `case` guard.
 *
 * `domain` is a run's `score_range` from GET /predictions/{run_id}/scores —
 * always pass that, never a client-computed min/max (see file-level comment).
 */
export function scoreFillExpression(domain: ScoreDomain): unknown[] {
  const [min, max] = widenIfDegenerate(domain);
  const stops = SEQUENTIAL_BLUE_STEPS.flatMap((hex, i) => {
    const score = min + (i / (SEQUENTIAL_BLUE_STEPS.length - 1)) * (max - min);
    return [score, hex];
  });

  return [
    "case",
    ["==", ["feature-state", "score"], null],
    NO_DATA_FILL,
    ["interpolate", ["linear"], ["feature-state", "score"], ...stops],
  ];
}
