"""In-memory prediction_run + region-score store.

Placeholder until the real async job pipeline (RECONCILIATION.md #5 step 4)
and a real datastore exist — /intelligence has no code yet either
(intelligence/RECONCILIATION.md #1), so there is nothing real to call.
This exists so `GET /predictions/{run_id}/regions` and `GET
/predictions/{run_id}/scores` have something to serve, and to demonstrate
recording `boundary_vintage` on a run at creation time per ADR-001.
`create_run` is not wired to a `POST /predictions` endpoint yet (out of
scope for this change) — it seeds one demo run below.
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
    region_level: str = "adm_dong",
    objective: str = "distribution_push",
) -> PredictionRun:
    """Records boundary_vintage at creation time (the level's latest vintage
    right now), so it stays fixed for this run even if A republishes later
    (ADR-001 "경계 빈티지" §2)."""
    run = PredictionRun(
        run_id=run_id,
        tenant_id=tenant_id,
        data_tier=data_tier,
        region_level=region_level,
        objective=objective,
        boundary_vintage=basemap_registry.latest_vintage(region_level),
        regions=_build_demo_regions(),
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
