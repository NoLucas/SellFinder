/**
 * opportunity_score (0-100) → fill color, on a FIXED scale — not normalized
 * to the current run's min/max. Two runs with the same score must render the
 * same color so maps are comparable across products/regions/time.
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

export const SCORE_DOMAIN: readonly [number, number] = [0, 100];

/** Color for a region that has no joined score yet (tile loaded, scores not). */
export const NO_DATA_FILL = "#e1e0d9"; // chart chrome gridline/hairline token

/** Plain hex lookup for legend swatches / non-map UI (React, canvas, etc). */
export function scoreToFillColor(score: number): string {
  const clamped = Math.min(SCORE_DOMAIN[1], Math.max(SCORE_DOMAIN[0], score));
  const stepCount = SEQUENTIAL_BLUE_STEPS.length;
  const t = (clamped - SCORE_DOMAIN[0]) / (SCORE_DOMAIN[1] - SCORE_DOMAIN[0]);
  const index = Math.round(t * (stepCount - 1));
  return SEQUENTIAL_BLUE_STEPS[index] ?? NO_DATA_FILL;
}

/**
 * MapLibre `fill-color` expression, keyed off feature-state (the join target
 * for setFeatureState, not a tile property) so scores can be re-joined
 * without re-fetching tiles. `["feature-state", "score"]` is `null` for
 * regions setFeatureState hasn't reached yet, hence the `case` guard.
 */
export function scoreFillExpression(): unknown[] {
  const stops = SEQUENTIAL_BLUE_STEPS.flatMap((hex, i) => {
    const score = SCORE_DOMAIN[0] + (i / (SEQUENTIAL_BLUE_STEPS.length - 1)) * (SCORE_DOMAIN[1] - SCORE_DOMAIN[0]);
    return [score, hex];
  });

  return [
    "case",
    ["==", ["feature-state", "score"], null],
    NO_DATA_FILL,
    ["interpolate", ["linear"], ["feature-state", "score"], ...stops],
  ];
}
