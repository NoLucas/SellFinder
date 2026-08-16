/**
 * DISPATCH-2 D-1 (orchestrator/DISPATCH-2.md §6): single injection point for
 * "where does region detail data come from". C-2 (job worker calling B's
 * predict_batch) hasn't shipped, so GET /predictions/{run_id}/regions/
 * {region_id} doesn't exist server-side yet — every call fails today.
 *
 * This tries the real endpoint first and falls back to the sample fixture
 * on failure, so it starts serving real data automatically once C-2 ships
 * — no caller (PredictionMap.tsx) needs to change. `isSample` is returned
 * alongside the detail so the UI can say, honestly, when it's showing a
 * placeholder — including in the (rarer, post-C-2) case where the real
 * call fails for an unrelated reason. Never silently pass fixture data off
 * as real (05_scoring_spec.md §6 — don't invent values).
 */

import { getRegionDetail } from "./client";
import { buildSampleDetail } from "./sampleDetail";
import type { PredictionDetail } from "./types";

export interface RegionDetailResult {
  detail: PredictionDetail;
  isSample: boolean;
}

export async function resolveRegionDetail(runId: string, regionId: string, token: string): Promise<RegionDetailResult> {
  try {
    const detail = await getRegionDetail(runId, regionId, token);
    return { detail, isSample: false };
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn(
      `resolveRegionDetail: real endpoint failed for run=${runId} region=${regionId}, showing sample fixture instead (C-2 not shipped yet, or a transient error)`,
      err,
    );
    return { detail: buildSampleDetail(runId, regionId), isSample: true };
  }
}
