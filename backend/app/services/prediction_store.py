"""In-memory prediction_run + region-score store.

Placeholder until the real async job pipeline (RECONCILIATION.md #5 step 4)
and a real datastore exist — /intelligence has no code yet either
(intelligence/RECONCILIATION.md #1), so there is nothing real to call.
This exists so `GET /predictions/{run_id}/regions` and `GET
/predictions/{run_id}/scores` have something to serve, and to demonstrate
recording `boundary_vintage` on a run at creation time per ADR-001.
`create_run` is not wired to a `POST /predictions` endpoint yet (out of
scope for this change) — it seeds one demo run below.

`region_level` defaults to "sigungu", not "adm_dong": the demo region_ids
below (41135, 11650, ...) are 5-digit codes, which is sigungu shape, not
adm_dong (03_region_features.json region_hierarchy / validate_contracts.py
_LEVEL_ID_DIGITS) — matches D-15's fix to samples/scores.json. It also has
to be a level basemap_registry actually has an artifact for (DISPATCH C-7):
A has published real data for "sido" and a D-12 fixture for "sigungu", but
nothing yet for "adm_dong", so defaulting here to "adm_dong" would make
`basemap_registry.latest_vintage()` raise NoBoundaryArtifactsError at
import time and take the whole app down.
"""

from dataclasses import dataclass

from app.services import basemap_registry


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
    boundary_vintage: str
    regions: list[RegionScore]


_DEMO_REGIONS: list[tuple] = [
    ("41135", "경기도 성남시 분당구", 92.1, 0.99, 82_000_000, 145_000_000, 231_000_000, "high", 0.86),
    ("11650", "서울특별시 서초구", 88.4, 0.95, 71_000_000, 128_000_000, 205_000_000, "high", 0.82),
    ("11680", "서울특별시 강남구", 86.9, 0.93, 69_000_000, 121_000_000, 198_000_000, "medium", 0.74),
    ("28245", "인천광역시 연수구", 74.2, 0.81, 41_000_000, 78_000_000, 130_000_000, "medium", 0.63),
    ("41461", "경기도 화성시", 61.8, 0.68, None, None, None, "low", 0.38),
]


def _build_demo_regions() -> list[RegionScore]:
    return [
        RegionScore(
            region_id=region_id,
            region_name=name,
            rank=i + 1,
            opportunity_score=score,
            score_percentile=percentile,
            expected_revenue_p10=p10,
            expected_revenue_p50=p50,
            expected_revenue_p90=p90,
            confidence_level=level,
            data_coverage=coverage,
        )
        for i, (region_id, name, score, percentile, p10, p50, p90, level, coverage) in enumerate(
            _DEMO_REGIONS
        )
    ]


_RUNS: dict[str, PredictionRun] = {}


def create_run(
    run_id: str,
    tenant_id: str,
    data_tier: str = "T1",
    region_level: str = "sigungu",
    objective: str = "distribution_push",
    regions: list[RegionScore] | None = None,
) -> PredictionRun:
    """Records boundary_vintage at creation time (the level's latest vintage
    right now), so it stays fixed for this run even if A republishes later
    (ADR-001 "경계 빈티지" §2).

    `regions` defaults to the shared demo dataset; tests pass an explicit
    list to seed scenarios the demo data doesn't cover (e.g. a suppressed
    coverage_flag cell, tests/test_privacy.py) without disturbing the demo
    rows other tests already assert against."""
    run = PredictionRun(
        run_id=run_id,
        tenant_id=tenant_id,
        data_tier=data_tier,
        region_level=region_level,
        objective=objective,
        boundary_vintage=basemap_registry.latest_vintage(region_level),
        regions=regions if regions is not None else _build_demo_regions(),
    )
    _RUNS[run_id] = run
    return run


def get_run(run_id: str, tenant_id: str) -> PredictionRun | None:
    run = _RUNS.get(run_id)
    if run is None or run.tenant_id != tenant_id:
        return None
    return run


# Seed one demo run so the endpoint is testable before POST /predictions exists.
create_run("run_demo01", tenant_id="tnt_demo")
