/**
 * Low-confidence overlay: a 45°/135° hand-drawn-style "Lines" fill per the
 * dataviz skill's texture-fill spec, drawn on top of the score fill.
 *
 * Fading the color for low confidence is explicitly rejected by the product
 * spec (00_product_spec.md §3 / AGENT_BRIEFS.md STEP 2-D): a lighter shade
 * reads as "low score", not "low confidence", to a user glancing at the map.
 * The pattern is a second, independent channel.
 *
 * The skill's tone-on-tone guidance (a darker step of the *fill's own* ramp)
 * assumes one fixed fill color. Here the underlying fill is a continuous
 * sequential ramp (0-700), so no single ramp step stays legible against
 * every score color from near-white to near-black. Using primary ink at
 * partial opacity keeps the hatch visible across the whole domain instead.
 */

import type { Map as MapLibreMap } from "maplibre-gl";

export const HATCH_IMAGE_ID = "low-confidence-hatch";

/**
 * Paint-property expression for the hatch layer's `fill-opacity`.
 *
 * feature-state expressions are only legal inside `paint` properties in
 * MapLibre/Mapbox GL — NOT in a layer's `filter`. So instead of filtering
 * the hatch layer to low-confidence features, the layer is always "on" and
 * this expression zeroes its opacity for every feature that isn't low
 * confidence.
 */
export function hatchOpacityExpression(): unknown[] {
  return ["case", ["==", ["feature-state", "confidence_level"], "low"], 1, 0];
}

const INK = "11, 11, 11"; // chart chrome primary ink, rgb
const LINE_ALPHA = 0.4;

export function registerHatchPattern(map: MapLibreMap): void {
  if (map.hasImage(HATCH_IMAGE_ID)) return;

  const size = 12; // device-independent tile size before pixelRatio scaling
  const pixelRatio = 2;
  const px = size * pixelRatio;

  const canvas = document.createElement("canvas");
  canvas.width = px;
  canvas.height = px;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.clearRect(0, 0, px, px);
  ctx.strokeStyle = `rgba(${INK}, ${LINE_ALPHA})`;
  ctx.lineWidth = pixelRatio * 1.5;
  ctx.lineCap = "square";

  // 45° diagonal, tiled so it repeats seamlessly across the pattern image.
  ctx.beginPath();
  ctx.moveTo(0, px);
  ctx.lineTo(px, 0);
  ctx.moveTo(-px / 2, px / 2);
  ctx.lineTo(px / 2, -px / 2);
  ctx.moveTo(px / 2, px * 1.5);
  ctx.lineTo(px * 1.5, px / 2);
  ctx.stroke();

  const imageData = ctx.getImageData(0, 0, px, px);
  map.addImage(HATCH_IMAGE_ID, imageData, { pixelRatio });
}
