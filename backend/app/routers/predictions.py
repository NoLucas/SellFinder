import base64

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas import (
    ExpectedRevenue,
    RegionScoreConfidence,
    RegionScoreItem,
    RegionScoresResponse,
)
from app.security import get_tenant_id
from app.services import prediction_store

router = APIRouter(tags=["predictions"])

_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CURSOR", "message": "cursor 값이 올바르지 않습니다."},
        ) from exc


@router.get(
    "/v1/predictions/{run_id}/regions",
    response_model=RegionScoresResponse,
    responses={404: {"description": "run_id를 찾을 수 없거나 다른 테넌트 소유입니다."}},
)
def get_prediction_regions(
    run_id: str,
    tenant_id: str = Depends(get_tenant_id),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    sort: str = Query(default="score_desc", pattern="^(score_desc|revenue_desc|profit_desc)$"),
    min_confidence: str | None = Query(default=None, pattern="^(low|medium|high)$"),
) -> RegionScoresResponse:
    run = prediction_store.get_run(run_id, tenant_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PREDICTION_RUN_NOT_FOUND",
                "message": f"run_id '{run_id}'를 찾을 수 없습니다.",
            },
        )

    regions = list(run.regions)
    if min_confidence:
        threshold = _CONFIDENCE_ORDER[min_confidence]
        regions = [r for r in regions if _CONFIDENCE_ORDER[r.confidence_level] >= threshold]

    if sort in ("revenue_desc", "profit_desc"):
        # No unit_cost data yet to separate profit from revenue (mock store) —
        # both sort by expected revenue until /intelligence provides profit.
        regions.sort(key=lambda r: r.expected_revenue_p50 or -1, reverse=True)
    else:
        regions.sort(key=lambda r: r.opportunity_score, reverse=True)

    offset = _decode_cursor(cursor)
    page = regions[offset : offset + limit]
    next_offset = offset + limit
    next_cursor = _encode_cursor(next_offset) if next_offset < len(regions) else None

    data = [
        RegionScoreItem(
            region_id=r.region_id,
            region_name=r.region_name,
            rank=r.rank,
            opportunity_score=r.opportunity_score,
            score_percentile=r.score_percentile,
            expected_revenue_krw=(
                None
                if run.data_tier == "T0" or r.expected_revenue_p50 is None
                else ExpectedRevenue(
                    p10=r.expected_revenue_p10, p50=r.expected_revenue_p50, p90=r.expected_revenue_p90
                )
            ),
            confidence=RegionScoreConfidence(level=r.confidence_level, data_coverage=r.data_coverage),
        )
        for r in page
    ]

    return RegionScoresResponse(data=data, next_cursor=next_cursor, boundary_vintage=run.boundary_vintage)
