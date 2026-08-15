from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_manifest_requires_auth() -> None:
    resp = client.get("/v1/basemap/regions/manifest")
    assert resp.status_code == 401


def test_manifest_returns_pointer_urls_only() -> None:
    resp = client.get(
        "/v1/basemap/regions/manifest", headers={"Authorization": "Bearer tnt_demo"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["boundary_vintage"] == "2026-08"

    levels = {lvl["level"]: lvl for lvl in body["levels"]}
    assert {"sido", "sigungu", "adm_dong"} <= levels.keys()
    for lvl in levels.values():
        assert lvl["url"].startswith("https://data-platform.sellfinder.internal/")

    # Only the level flagged requires_signing in the registry gets a signature.
    assert "sig=" not in levels["sido"]["url"]
    assert "sig=" in levels["adm_dong"]["url"]
