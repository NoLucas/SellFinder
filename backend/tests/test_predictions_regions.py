from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

AUTH = {"Authorization": "Bearer tnt_demo"}


def test_regions_requires_auth() -> None:
    resp = client.get("/v1/predictions/run_demo01/regions")
    assert resp.status_code == 401


def test_regions_returns_boundary_vintage_and_scores() -> None:
    resp = client.get("/v1/predictions/run_demo01/regions", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["boundary_vintage"] == "2026-08"
    assert len(body["data"]) > 0
    scores = [r["opportunity_score"] for r in body["data"]]
    assert scores == sorted(scores, reverse=True)


def test_regions_unknown_run_is_404() -> None:
    resp = client.get("/v1/predictions/run_nope/regions", headers=AUTH)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PREDICTION_RUN_NOT_FOUND"


def test_regions_wrong_tenant_is_404_not_leaked() -> None:
    resp = client.get(
        "/v1/predictions/run_demo01/regions",
        headers={"Authorization": "Bearer tnt_other"},
    )
    assert resp.status_code == 404


def test_regions_cursor_pagination() -> None:
    first = client.get("/v1/predictions/run_demo01/regions?limit=2", headers=AUTH)
    body = first.json()
    assert len(body["data"]) == 2
    assert body["next_cursor"] is not None

    second = client.get(
        f"/v1/predictions/run_demo01/regions?limit=2&cursor={body['next_cursor']}",
        headers=AUTH,
    )
    assert second.json()["data"][0]["region_id"] != body["data"][0]["region_id"]


def test_regions_min_confidence_filter() -> None:
    resp = client.get(
        "/v1/predictions/run_demo01/regions?min_confidence=high", headers=AUTH
    )
    body = resp.json()
    assert all(r["confidence"]["level"] == "high" for r in body["data"])
