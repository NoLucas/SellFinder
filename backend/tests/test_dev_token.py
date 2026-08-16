"""ADR-003 "개발 중 임시 조치": /v1/dev/token exists only in development.
DECISIONS.md D-17 — if this route is reachable in a production build, it is
an S1 defect. The gate is checked at app-creation time (app.main.create_app),
not inside the handler, so a production build genuinely never registers it."""
from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app
from app.security import verify_token


def test_dev_token_issued_in_development() -> None:
    assert settings.env == "development"
    client = TestClient(create_app())
    resp = client.post(
        "/v1/dev/token",
        json={"tenant_id": "tnt_demo", "role": "analyst", "region_scope": ["41"]},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    claims = verify_token(token)
    assert claims.tenant_id == "tnt_demo"
    assert claims.role == "analyst"
    assert claims.region_scope == ["41"]

    # and the issued token actually authenticates against a real endpoint —
    # run_demo01 is owned by tenant_id "tnt_demo", matching the claim above.
    api_resp = client.get(
        "/v1/predictions/run_demo01/regions", headers={"Authorization": f"Bearer {token}"}
    )
    assert api_resp.status_code == 200
    assert len(api_resp.json()["data"]) > 0


def test_dev_token_route_absent_outside_development() -> None:
    original = settings.env
    settings.env = "production"
    try:
        client = TestClient(create_app())
        resp = client.post("/v1/dev/token", json={"tenant_id": "tnt_demo"})
        assert resp.status_code == 404
    finally:
        settings.env = original
