from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

AUTH = {"Authorization": "Bearer tnt_demo"}


def test_scores_requires_auth() -> None:
    resp = client.get("/v1/predictions/run_demo01/scores")
    assert resp.status_code == 401


def test_scores_shape_is_tuple_array_with_schema() -> None:
    resp = client.get("/v1/predictions/run_demo01/scores", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()

    assert body["run_id"] == "run_demo01"
    assert body["schema"] == ["region_id", "opportunity_score", "confidence_level"]
    assert body["boundary_vintage"]
    assert body["region_level"]
    assert body["objective"]
    assert body["data_tier"]
    assert body["custom_geometries"] is None

    for row in body["scores"]:
        assert len(row) == 3
        region_id, score, confidence_level = row
        assert isinstance(region_id, str)
        assert isinstance(score, (int, float))
        assert confidence_level in ("low", "medium", "high")


def test_scores_never_carries_revenue() -> None:
    resp = client.get("/v1/predictions/run_demo01/scores", headers=AUTH)
    body = resp.json()
    assert "expected_revenue_krw" not in body
    for row in body["scores"]:
        assert "expected_revenue_krw" not in row


def test_scores_returns_all_regions_unpaginated() -> None:
    resp = client.get("/v1/predictions/run_demo01/scores", headers=AUTH)
    body = resp.json()
    assert "next_cursor" not in body
    assert "cursor" not in body
    assert len(body["scores"]) == 5  # all demo regions, in one response


def test_scores_range_matches_actual_scores() -> None:
    resp = client.get("/v1/predictions/run_demo01/scores", headers=AUTH)
    body = resp.json()
    values = [row[1] for row in body["scores"]]
    assert body["score_range"]["min"] == min(values)
    assert body["score_range"]["max"] == max(values)
    assert body["score_range"]["min"] <= body["score_range"]["p50"] <= body["score_range"]["max"]


def test_scores_unknown_run_is_404() -> None:
    resp = client.get("/v1/predictions/run_nope/scores", headers=AUTH)
    assert resp.status_code == 404
