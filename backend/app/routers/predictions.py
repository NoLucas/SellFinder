import base64
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.schemas import (
    ExpectedRevenue,
    PredictionCreateResponse,
    PredictionRequest,
    RegionScoreConfidence,
    RegionScoreItem,
    RegionScoresResponse,
)
from app.security import get_tenant_id
from app.services import job_runner, prediction_store, privacy

router = APIRouter(tags=["predictions"])

# Not yet real - a fixed placeholder until job sizing is a real thing to
# estimate (DISPATCH-2 C-1 scope is "returns 202 without waiting", not job
# duration estimation).
_ESTIMATED_SECONDS_PLACEHOLDER = 30


def _generate_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}

# 05_scoring_spec.md §2: T0 (no first-party sales data) has confidence.level
# capped at "medium" — same rule as the expected_revenue_krw null rule
# (D-03), just for confidence instead of money.
_T0_CONFIDENCE_CEILING = "medium"


def _confidence_for_tier(level: str, data_tier: str) -> str:
    if data_tier == "T0" and _CONFIDENCE_ORDER[level] > _CONFIDENCE_ORDER[_T0_CONFIDENCE_CEILING]:
        return _T0_CONFIDENCE_CEILING
    return level


def _expected_revenue_for(
    r: prediction_store.RegionScore, run: prediction_store.PredictionRun
) -> ExpectedRevenue | None:
    """Two independent reasons to null this, not one (VF-005 is exactly what
    happens when only one of two required checks gets implemented — T0's
    money was blocked but confidence wasn't):
      - data_tier == "T0" (D-03): no first-party sales, no honest estimate.
      - coverage_flag == "suppressed" (06_governance.md §2.3, VF-010): the
        cell backing this region's estimate is below the k-anonymity
        threshold. privacy.redact() is the one place that check happens so
        a future call site (region detail, xlsx/csv export) inherits it
        automatically instead of re-implementing its own check.
    """
    if run.data_tier == "T0":
        return None
    p10 = privacy.redact(r.expected_revenue_p10, r.coverage_flag, region_id=r.region_id, field="expected_revenue_p10")
    p50 = privacy.redact(r.expected_revenue_p50, r.coverage_flag, region_id=r.region_id, field="expected_revenue_p50")
    p90 = privacy.redact(r.expected_revenue_p90, r.coverage_flag, region_id=r.region_id, field="expected_revenue_p90")
    if p50 is None:
        return None
    return ExpectedRevenue(p10=p10, p50=p50, p90=p90)


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


@router.post(
    "/v1/predictions",
    response_model=PredictionCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_prediction(
    body: PredictionRequest,
    tenant_id: str = Depends(get_tenant_id),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> PredictionCreateResponse:
    """00_product_spec.md Anti-goals: "예측 API를 동기 호출로 설계" is
    explicitly forbidden. This handler creates a queued run and hands the
    actual computation to app.services.job_runner on a background thread
    it does not wait for - by the time this function returns, the job has
    not run yet (tests/test_predictions_create.py asserts this with wall
    clock timing, not just by reading the code).

    `idempotency_key` (04_api_contract.yaml's IdempotencyKey parameter,
    "반드시 지킬 것" #4): "동일 키로 24시간 내 재요청 시 원 결과를 그대로
    반환한다" - scoped per tenant_id (a key string is only meaningful
    within the tenant that sent it, DISPATCH-2 C-3).

    T0/T1/T2 data_tier isn't in PredictionRequest (it depends on whether
    the tenant has uploaded tenant_sales, not on this request) and nothing
    in /backend tracks that yet, so every run is created as T1 - same
    placeholder default create_run() already used before this endpoint
    existed."""
    if idempotency_key:
        existing_run_id = prediction_store.find_run_id_for_idempotency_key(
            tenant_id, idempotency_key
        )
        if existing_run_id is not None:
            existing_run = prediction_store.get_run(existing_run_id, tenant_id)
            return PredictionCreateResponse(
                run_id=existing_run.run_id,
                status=existing_run.status,
                estimated_seconds=_ESTIMATED_SECONDS_PLACEHOLDER,
                data_tier=existing_run.data_tier,
            )

    run_id = _generate_run_id()
    prediction_store.create_queued_run(
        run_id=run_id,
        tenant_id=tenant_id,
        region_level=body.region_level,
        objective=body.objective,
        data_tier="T1",
    )
    if idempotency_key:
        prediction_store.remember_idempotency_key(tenant_id, idempotency_key, run_id)
    job_runner.submit_prediction_job(run_id, region_level=body.region_level, data_tier="T1")

    return PredictionCreateResponse(
        run_id=run_id,
        status="queued",
        estimated_seconds=_ESTIMATED_SECONDS_PLACEHOLDER,
        data_tier="T1",
    )


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

    # Computed once per region, before sorting: this is the value the client
    # actually sees (post-T0-null / post-privacy.redact()), and it has to be
    # the sort key too — sorting on the raw store field instead leaked a
    # suppressed region's relative magnitude through ranking position even
    # though expected_revenue_krw itself came back null (VF-013). Same
    # sentence VF-005 already taught: a rule enforced in only one of the
    # places a value can escape isn't enforced.
    revenue_by_region_id = {r.region_id: _expected_revenue_for(r, run) for r in regions}

    if sort in ("revenue_desc", "profit_desc"):
        # No unit_cost data yet to separate profit from revenue (mock store) —
        # both sort by expected revenue until /intelligence provides profit.
        def _revenue_sort_key(r: prediction_store.RegionScore) -> int:
            revenue = revenue_by_region_id[r.region_id]
            return revenue.p50 if revenue is not None else -1

        regions.sort(key=_revenue_sort_key, reverse=True)
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
            expected_revenue_krw=revenue_by_region_id[r.region_id],
            confidence=RegionScoreConfidence(
                level=_confidence_for_tier(r.confidence_level, run.data_tier),
                data_coverage=r.data_coverage,
            ),
        )
        for r in page
    ]

    return RegionScoresResponse(data=data, next_cursor=next_cursor)


@router.get(
    "/v1/predictions/{run_id}/scores",
    responses={404: {"description": "run_id를 찾을 수 없거나 다른 테넌트 소유입니다."}},
)
def get_prediction_scores(
    run_id: str,
    tenant_id: str = Depends(get_tenant_id),
    product_id: str | None = Query(default=None, description="다중 SKU run에서 하나 선택"),
    channel: str | None = Query(default=None),
) -> dict:
    """Lightweight map-rendering payload — the one exception to cursor
    pagination (the whole region set is returned in one call so the map can
    be painted in a single pass). Tuple array + schema, not an object array,
    to cut payload size on ~3,500 rows. Never carries expected_revenue_krw —
    the T0-null rule is enforced in exactly one place, the region-detail
    endpoint. Returned as a plain dict (not a pydantic model) because
    `schema` collides with BaseModel's own namespace.

    `product_id`/`channel` are accepted per contract but not yet applied —
    the mock store doesn't stratify demo regions by product/channel.
    """
    run = prediction_store.get_run(run_id, tenant_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PREDICTION_RUN_NOT_FOUND",
                "message": f"run_id '{run_id}'를 찾을 수 없습니다.",
            },
        )

    regions = sorted(run.regions, key=lambda r: r.opportunity_score, reverse=True)
    scores = [
        [r.region_id, r.opportunity_score, _confidence_for_tier(r.confidence_level, run.data_tier)]
        for r in regions
    ]

    values = sorted(r.opportunity_score for r in regions)
    score_range = {
        "min": values[0],
        "max": values[-1],
        "p50": values[len(values) // 2],
    }

    return {
        "run_id": run.run_id,
        "region_level": run.region_level,
        "boundary_vintage": run.boundary_vintage,
        "objective": run.objective,
        "data_tier": run.data_tier,
        "schema": ["region_id", "opportunity_score", "confidence_level"],
        "scores": scores,
        "score_range": score_range,
        # Only set for region_level="custom_catchment" — standard admin
        # boundaries always come from the manifest's .pmtiles, never inline.
        "custom_geometries": None,
    }
