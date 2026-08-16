from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_manifest_requires_auth() -> None:
    resp = client.get("/v1/basemap/regions/manifest?level=adm_dong")
    assert resp.status_code == 401


def test_manifest_requires_level() -> None:
    resp = client.get(
        "/v1/basemap/regions/manifest", headers={"Authorization": "Bearer tnt_demo"}
    )
    assert resp.status_code == 422


def test_manifest_returns_pointer_to_pmtiles_only() -> None:
    resp = client.get(
        "/v1/basemap/regions/manifest?level=adm_dong",
        headers={"Authorization": "Bearer tnt_demo"},
    )
    assert resp.status_code == 200
    # signed URL (adm_dong requires signing) must not be shared-cacheable — VF-006
    assert resp.headers["cache-control"] == "private, max-age=3600"

    body = resp.json()
    assert body["level"] == "adm_dong"
    assert body["feature_id_property"] == "region_id"
    assert body["source_layer"] == "regions"
    assert body["tile_url"].startswith("https://cdn.sellfinder.kr/tiles/")
    assert body["tile_url"].endswith(".pmtiles") or "sig=" in body["tile_url"]
    assert "sig=" in body["tile_url"]  # adm_dong requires signing
    assert body["boundary_vintage"] in body["available_vintages"]
    assert body["available_vintages"] == sorted(body["available_vintages"], reverse=True)


def test_manifest_sido_is_not_signed() -> None:
    resp = client.get(
        "/v1/basemap/regions/manifest?level=sido",
        headers={"Authorization": "Bearer tnt_demo"},
    )
    assert resp.headers["cache-control"] == "public, max-age=3600"

    body = resp.json()
    assert "sig=" not in body["tile_url"]


def test_manifest_specific_vintage() -> None:
    resp = client.get(
        "/v1/basemap/regions/manifest?level=adm_dong&vintage=2025-01-01",
        headers={"Authorization": "Bearer tnt_demo"},
    )
    assert resp.status_code == 200
    assert resp.json()["boundary_vintage"] == "2025-01-01"


def test_manifest_unknown_vintage_is_404() -> None:
    resp = client.get(
        "/v1/basemap/regions/manifest?level=adm_dong&vintage=1999-01-01",
        headers={"Authorization": "Bearer tnt_demo"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "BOUNDARY_VINTAGE_NOT_FOUND"
