"""VF-008 / VF-005: no test previously created a data_tier="T0" run, so the
T0 branches in routers/predictions.py (money null, confidence ceiling) ran
in production code but never under test. This seeds one and drives both
endpoints.

Since DISPATCH-2 C-2, prediction_store.compute_regions() calls real
predict_batch, which doesn't compute confidence at all yet (README §5) -
compute_regions() defaults every region to confidence_level="low" (the safe
floor, never fabricated). That means real computation alone can never
produce a "high" row to clamp, so the ceiling tests below seed an explicit
regions=[...] override (prediction_store.create_run's escape hatch,
already used by tests/test_privacy.py) with a genuine "high" row - without
it, the T0 ceiling assertion would be vacuously true for the wrong reason
(nothing to clamp) rather than actually exercising the clamp."""
from fastapi.testclient import TestClient

from app.main import app
from app.services import prediction_store

client = TestClient(app)
AUTH = {"Authorization": "Bearer tnt_t0"}

_HIGH_CONFIDENCE_REGION = prediction_store.RegionScore(
    region_id="91001001",
    region_name="테스트 고신뢰 지역",
    rank=1,
    opportunity_score=90.0,
    score_percentile=0.95,
    expected_revenue_p10=10_000_000,
    expected_revenue_p50=20_000_000,
    expected_revenue_p90=30_000_000,
    confidence_level="high",
    data_coverage=0.9,
)

prediction_store.create_run(
    "run_t0_test", tenant_id="tnt_t0", data_tier="T0", regions=[_HIGH_CONFIDENCE_REGION]
)
prediction_store.create_run(
    "run_t1_high_confidence_test",
    tenant_id="tnt_t1_hc",
    data_tier="T1",
    regions=[_HIGH_CONFIDENCE_REGION],
)


def test_t0_regions_never_return_revenue() -> None:
    resp = client.get("/v1/predictions/run_t0_test/regions", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) > 0
    assert all(r["expected_revenue_krw"] is None for r in body["data"])


def test_t0_scores_never_return_revenue() -> None:
    resp = client.get("/v1/predictions/run_t0_test/scores", headers=AUTH)
    assert resp.status_code == 200
    assert "expected_revenue_krw" not in resp.text


def test_t0_regions_confidence_capped_at_medium() -> None:
    resp = client.get("/v1/predictions/run_t0_test/regions", headers=AUTH)
    levels = [r["confidence"]["level"] for r in resp.json()["data"]]
    # the seeded region really is "high" pre-clamp (see
    # test_t1_baseline_still_allows_high_confidence below) - if this test
    # ever sees "high" here, the T0 ceiling stopped firing.
    assert "high" not in levels


def test_t0_scores_confidence_capped_at_medium() -> None:
    resp = client.get("/v1/predictions/run_t0_test/scores", headers=AUTH)
    levels = [row[2] for row in resp.json()["scores"]]
    assert "high" not in levels


def test_t1_baseline_still_allows_high_confidence() -> None:
    """Guards against a ceiling implementation that clamps everyone, not
    just T0 - same seed region as run_t0_test, but T1 here, so "high" must
    survive untouched."""
    resp = client.get(
        "/v1/predictions/run_t1_high_confidence_test/regions",
        headers={"Authorization": "Bearer tnt_t1_hc"},
    )
    levels = [r["confidence"]["level"] for r in resp.json()["data"]]
    assert "high" in levels


def test_min_confidence_filter_uses_the_displayed_clamped_value() -> None:
    """VF-013 follow-up (총괄자 6차 지시 둘째 판정): min_confidence must
    filter on the same post-clamp value the response actually displays, not
    the raw pre-clamp confidence_level. run_t0_test's only region is "high"
    pre-clamp but displays "medium" (T0 ceiling) - a filter reading the raw
    field would wrongly include it under min_confidence=high even though
    every row in the response shows "medium"."""
    resp = client.get(
        "/v1/predictions/run_t0_test/regions?min_confidence=high", headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []

    # sanity: the same region set, unfiltered, does show up (proves the
    # empty result above is the filter working correctly, not a broken run)
    unfiltered = client.get("/v1/predictions/run_t0_test/regions", headers=AUTH)
    assert len(unfiltered.json()["data"]) == 1
    assert unfiltered.json()["data"][0]["confidence"]["level"] == "medium"

    # and min_confidence=medium must still include it (clamped value passes)
    at_medium = client.get(
        "/v1/predictions/run_t0_test/regions?min_confidence=medium", headers=AUTH
    )
    assert len(at_medium.json()["data"]) == 1
