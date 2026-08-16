from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_old_api_v1_health_prefix_is_gone() -> None:
    """BRIEF-C 7 / DISPATCH-2 C-5: /api/v1/health -> /v1/health, unifying
    every route under the same prefix as everything else in this service."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 404
