"""In-memory prediction_run + region-score store.

Placeholder until a real datastore exists — this is the store half of the
mock async job pipeline (app.services.job_runner is the worker half,
DISPATCH-2 C-1/C-2). `create_run` (synchronous, immediately-populated) is
the original demo-seeding entry point and still exists for tests that seed
a fully-formed run without going through the HTTP job flow.
`create_queued_run`/`complete_run`/`fail_run` are the three-state (queued ->
succeeded|failed) primitives POST /v1/predictions actually uses — a run
starts with empty `regions` and only gets them once the background job
calls `complete_run`, never inline in the request handler
(00_product_spec.md Anti-goals: "예측 API를 동기 호출로 설계" 금지).

There is no more hardcoded demo score table here (DISPATCH-2 C-2 removed
_build_demo_regions()). compute_regions() is the one place scores get
produced, and it always goes through app.services.intelligence_client's
real call into /intelligence's predict_batch.

`region_level` defaults to "adm_dong", not "sigungu": intelligence's
synthetic dataset only has real region_feature rows at adm_dong granularity
(verified directly - sigungu/sido-level region_ids all resolve to None
features there, so predict_batch would score everyone identically-neutral,
README §4-3). A also now has a real adm_dong manifest (DISPATCH C-7), so
this default gets both a differentiated score and a working boundary tile.
"""

import datetime
from dataclasses import dataclass

from app.services import basemap_registry, intelligence_client


@dataclass
class RegionScore:
    region_id: str
    region_name: str
    rank: int
    opportunity_score: float
    score_percentile: float
    expected_revenue_p10: int | None
    expected_revenue_p50: int | None
    expected_revenue_p90: int | None
    confidence_level: str
    data_coverage: float
    # 01_domain_model.json demand_signal.coverage_flag: "actual"|"estimated"|
    # "suppressed". None for regions with no underlying demand_signal cell
    # yet (the mock data below). When "suppressed", app.services.privacy
    # must redact expected_revenue_* before it reaches a response
    # (06_governance.md §2.3 / VF-010) — enforced in routers/predictions.py,
    # not here, so this dataclass stays a plain data holder.
    coverage_flag: str | None = None


@dataclass
class PredictionRun:
    run_id: str
    tenant_id: str
    data_tier: str
    region_level: str
    objective: str
    boundary_vintage: str | None
    regions: list[RegionScore]
    # "queued" | "succeeded" | "failed". Defaults to "succeeded" so every
    # existing caller of create_run() (the synchronous demo-seeding path,
    # used throughout tests) keeps working unchanged — only the new
    # create_queued_run() path starts a run at "queued".
    status: str = "succeeded"
    failure_reason: str | None = None


def compute_regions(region_level: str, data_tier: str) -> list[RegionScore]:
    """DISPATCH-2 C-2: the real replacement for the old hardcoded demo
    table. Calls /intelligence's predict_batch (via intelligence_client)
    for a candidate region_id set that actually exists in the feature store
    being queried, then derives rank/opportunity_score/score_percentile the
    way intelligence/README.md §5 says a caller must - predict_batch
    doesn't rank; total_multiplier ordering is C's job."""
    region_ids = intelligence_client.region_ids_for_level(region_level)
    results = intelligence_client.run_prediction(region_ids, data_tier=data_tier)
    results.sort(key=lambda r: r.total_multiplier, reverse=True)

    n = len(results)
    regions: list[RegionScore] = []
    for i, result in enumerate(results):
        percentile = (n - 1 - i) / (n - 1) if n > 1 else 1.0
        revenue = result.expected_revenue_krw  # always None today (README §5, Step 5 not built)
        regions.append(
            RegionScore(
                region_id=result.region_id,
                region_name=intelligence_client.region_name_for(result.region_id)
                or result.region_id,
                rank=i + 1,
                opportunity_score=percentile * 100,
                score_percentile=percentile,
                expected_revenue_p10=revenue.get("p10") if revenue else None,
                expected_revenue_p50=revenue.get("p50") if revenue else None,
                expected_revenue_p90=revenue.get("p90") if revenue else None,
                # 05_scoring_spec.md §4's confidence formula (data_coverage,
                # comparable_region_count, tier) isn't implemented anywhere
                # yet - B's model doesn't compute it, so there is no real
                # signal to report. "low" is the safe floor, not a guess in
                # either direction - same principle as D-19's forced
                # downgrade for unmapped taxonomy nodes. Never fabricate
                # "medium"/"high" with nothing real behind it.
                confidence_level="low",
                data_coverage=0.0,
                # A hasn't published coverage_flag yet (DISPATCH-2 A-2, open).
                coverage_flag=None,
            )
        )
    return regions


_RUNS: dict[str, PredictionRun] = {}


def _boundary_vintage_for(region_level: str) -> str | None:
    """custom_catchment has no administrative boundary tile at all (D-09 -
    it's tenant-drawn GeoJSON inline in /scores' custom_geometries, not a
    basemap_registry artifact), so there's no vintage to record."""
    if region_level == "custom_catchment":
        return None
    return basemap_registry.latest_vintage(region_level)


def create_run(
    run_id: str,
    tenant_id: str,
    data_tier: str = "T1",
    region_level: str = "adm_dong",
    objective: str = "distribution_push",
    regions: list[RegionScore] | None = None,
) -> PredictionRun:
    """Records boundary_vintage at creation time (the level's latest vintage
    right now), so it stays fixed for this run even if A republishes later
    (ADR-001 "경계 빈티지" §2).

    Synchronous and immediately-populated - the original demo-seeding entry
    point, kept for tests that want a fully-formed run without going
    through the async HTTP job flow. `regions` defaults to a real
    compute_regions() call (not a hardcoded table anymore); tests pass an
    explicit list to seed scenarios real computation doesn't cover (e.g. a
    suppressed coverage_flag cell, tests/test_privacy.py) without depending
    on whatever compute_regions() happens to produce.

    Not what POST /v1/predictions uses (see create_queued_run below) -
    calling this synchronously from a request handler is exactly what
    00_product_spec.md Anti-goals prohibits."""
    run = PredictionRun(
        run_id=run_id,
        tenant_id=tenant_id,
        data_tier=data_tier,
        region_level=region_level,
        objective=objective,
        boundary_vintage=_boundary_vintage_for(region_level),
        regions=regions if regions is not None else compute_regions(region_level, data_tier),
        status="succeeded",
    )
    _RUNS[run_id] = run
    return run


def create_queued_run(
    run_id: str,
    tenant_id: str,
    region_level: str,
    objective: str,
    data_tier: str = "T1",
) -> PredictionRun:
    """POST /v1/predictions' entry point (DISPATCH-2 C-1). Starts with
    status="queued" and no regions - the caller (routers/predictions.py)
    must return its 202 response and only *afterwards* let
    app.services.job_runner populate this run via complete_run(), never
    compute inline here."""
    run = PredictionRun(
        run_id=run_id,
        tenant_id=tenant_id,
        data_tier=data_tier,
        region_level=region_level,
        objective=objective,
        boundary_vintage=_boundary_vintage_for(region_level),
        regions=[],
        status="queued",
    )
    _RUNS[run_id] = run
    return run


def complete_run(run_id: str, regions: list[RegionScore]) -> None:
    run = _RUNS[run_id]
    run.regions = regions
    run.status = "succeeded"


def fail_run(run_id: str, reason: str) -> None:
    run = _RUNS[run_id]
    run.status = "failed"
    run.failure_reason = reason


def get_run(run_id: str, tenant_id: str) -> PredictionRun | None:
    run = _RUNS.get(run_id)
    if run is None or run.tenant_id != tenant_id:
        return None
    return run


# ─────────────────────── Idempotency-Key (DISPATCH-2 C-3) ───────────────────────
# 04_api_contract.yaml components.parameters.IdempotencyKey: "동일 키로 24시간
# 내 재요청 시 원 결과를 그대로 반환한다." Keyed by (tenant_id, key) - a key is
# only meaningful within the tenant that sent it; two tenants coincidentally
# using the same string must not collide.
_IDEMPOTENCY_TTL = datetime.timedelta(hours=24)
_IDEMPOTENCY_KEYS: dict[tuple[str, str], tuple[str, datetime.datetime]] = {}


def find_run_id_for_idempotency_key(tenant_id: str, key: str) -> str | None:
    """Returns the run_id already created for this (tenant, key) pair if
    it's still within the 24h window, else None (including once expired -
    a later request with the same key is free to create a new run)."""
    entry = _IDEMPOTENCY_KEYS.get((tenant_id, key))
    if entry is None:
        return None
    run_id, recorded_at = entry
    if datetime.datetime.now(datetime.timezone.utc) - recorded_at > _IDEMPOTENCY_TTL:
        del _IDEMPOTENCY_KEYS[(tenant_id, key)]
        return None
    return run_id


def remember_idempotency_key(tenant_id: str, key: str, run_id: str) -> None:
    _IDEMPOTENCY_KEYS[(tenant_id, key)] = (run_id, datetime.datetime.now(datetime.timezone.utc))


# Seed one demo run so the endpoint is testable before POST /predictions exists.
create_run("run_demo01", tenant_id="tnt_demo")
