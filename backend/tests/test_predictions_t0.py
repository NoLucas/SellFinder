"""VF-008 / VF-005: no test previously created a data_tier="T0" run, so the
T0 branches in routers/predictions.py (money null, confidence ceiling) ran
in production code but never under test. This seeds one and drives both
endpoints."""
from fastapi.testclient import TestClient

from app.main import app
from app.services import prediction_store

client = TestClient(app)
AUTH = {"Authorization": "Bearer tnt_t0"}

prediction_store.create_run("run_t0_test", tenant_id="tnt_t0", data_tier="T0")


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
    assert "high" not in levels
    # underlying demo data does contain a "high" row (T1 baseline) —
    # confirm this test would actually catch a regression, not just pass
    # because the fixture happened to have no highs.
    assert set(levels) & {"medium", "low"}


def test_t0_scores_confidence_capped_at_medium() -> None:
    resp = client.get("/v1/predictions/run_t0_test/scores", headers=AUTH)
    levels = [row[2] for row in resp.json()["scores"]]
    assert "high" not in levels


def test_t1_baseline_still_allows_high_confidence() -> None:
    """Guards against a ceiling implementation that clamps everyone, not
    just T0 (run_demo01 is T1 and its demo data includes 'high' rows)."""
    resp = client.get(
        "/v1/predictions/run_demo01/regions", headers={"Authorization": "Bearer tnt_demo"}
    )
    levels = [r["confidence"]["level"] for r in resp.json()["data"]]
    assert "high" in levels
