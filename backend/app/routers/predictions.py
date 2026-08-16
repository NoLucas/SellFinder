import base64
import uuid
from dataclasses import dataclass

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

    Only ever called from _build_views() below - VF-013 was this same
    function being computed correctly but a *different* piece of code
    (the revenue_desc sort key) reading the raw RegionScore field instead
    of this one's output. The fix isn't "remember to redact here too" at
    every call site; it's that there is now only one call site."""
    if run.data_tier == "T0":
        return None
    p10 = privacy.redact(r.expected_revenue_p10, r.coverage_flag, region_id=r.region_id, field="expected_revenue_p10")
    p50 = privacy.redact(r.expected_revenue_p50, r.coverage_flag, region_id=r.region_id, field="expected_revenue_p50")
    p90 = privacy.redact(r.expected_revenue_p90, r.coverage_flag, region_id=r.region_id, field="expected_revenue_p90")
    if p50 is None:
        return None
    return ExpectedRevenue(p10=p10, p50=p50, p90=p90)


@dataclass(frozen=True)
class _RegionView:
    """The redacted/clamped view (VF-005, VF-010, VF-013). Every field here
    is already safe to sort on, filter on, paginate, serialize, or (later)
    export - nothing downstream of _build_views() may read a
    prediction_store.RegionScore directly again. That's the whole fix:
    not "redact at each call site" but "there is only one call site, and
    everything after it only ever sees this view." A new consumer (a future
    /regions/{region_id} detail endpoint, an xlsx/csv export) that iterates
    _build_views()'s output inherits every guarantee below for free -  one
    that reaches into run.regions itself does not, by construction, compile
    against this module's intended shape."""

    region_id: str
    region_name: str
    rank: int
    opportunity_score: float
    score_percentile: float
    expected_revenue_krw: ExpectedRevenue | None  # already T0/suppressed-redacted
    confidence_level: str  # already T0-ceiling-clamped
    data_coverage: float


def _build_views(run: prediction_store.PredictionRun) -> list[_RegionView]:
    """The single choke point every /predictions/{run_id}/* response builds
    from. sort/filter/paginate all operate on this list, never on
    run.regions - see _RegionView's docstring for why that ordering is the
    actual fix, not an implementation detail."""
    return [
        _RegionView(
            region_id=r.region_id,
            region_name=r.region_name,
            rank=r.rank,
            opportunity_score=r.opportunity_score,
            score_percentile=r.score_percentile,
            expected_revenue_krw=_expected_revenue_for(r, run),
            confidence_level=_confidence_for_tier(r.confidence_level, run.data_tier),
            data_coverage=r.data_coverage,
        )
        for r in run.regions
    ]


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

    # Everything below this line reads _RegionView only, never
    # prediction_store.RegionScore / run.regions directly (VF-013: the old
    # code redacted correctly for the response but sorted on the raw
    # field - two code paths reading two different things). min_confidence
    # filters on the *displayed* confidence_level (already T0-clamped) for
    # the same reason: filtering on the raw value would let a query select
    # regions whose displayed confidence doesn't actually meet the
    # threshold requested.
    views = _build_views(run)

    if min_confidence:
        threshold = _CONFIDENCE_ORDER[min_confidence]
        views = [v for v in views if _CONFIDENCE_ORDER[v.confidence_level] >= threshold]

    if sort in ("revenue_desc", "profit_desc"):
        # No unit_cost data yet to separate profit from revenue (mock store) —
        # both sort by expected revenue until /intelligence provides profit.
        views.sort(
            key=lambda v: v.expected_revenue_krw.p50 if v.expected_revenue_krw else -1,
            reverse=True,
        )
    else:
        views.sort(key=lambda v: v.opportunity_score, reverse=True)

    offset = _decode_cursor(cursor)
    page = views[offset : offset + limit]
    next_offset = offset + limit
    next_cursor = _encode_cursor(next_offset) if next_offset < len(views) else None

    data = [
        RegionScoreItem(
            region_id=v.region_id,
            region_name=v.region_name,
            rank=v.rank,
            opportunity_score=v.opportunity_score,
            score_percentile=v.score_percentile,
            expected_revenue_krw=v.expected_revenue_krw,
            confidence=RegionScoreConfidence(level=v.confidence_level, data_coverage=v.data_coverage),
        )
        for v in page
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

    # Same _build_views() choke point as /regions - confidence_level here
    # is already T0-clamped, not the raw stored value (VF-013's fix applies
    # to both endpoints, not just the one it was first found on).
    views = sorted(_build_views(run), key=lambda v: v.opportunity_score, reverse=True)
    scores = [[v.region_id, v.opportunity_score, v.confidence_level] for v in views]

    values = sorted(v.opportunity_score for v in views)
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
