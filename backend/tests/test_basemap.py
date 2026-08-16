from fastapi.testclient import TestClient

from app.main import app
from app.services import basemap_registry

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
    # dev artifact server, not the invented cdn.sellfinder.kr from the old
    # hardcoded table (VF-004) — this is A's real committed tile_url
    assert body["tile_url"].startswith("http://localhost:8000/artifacts/")
    assert "sig=" in body["tile_url"]  # adm_dong requires signing
    assert body["minzoom"] == 5 and body["maxzoom"] == 14  # from A's manifest, D-14
    assert body["boundary_vintage"] in body["available_vintages"]
    assert body["available_vintages"] == sorted(body["available_vintages"], reverse=True)


def test_manifest_sido_is_not_signed() -> None:
    resp = client.get(
        "/v1/basemap/regions/manifest?level=sido",
        headers={"Authorization": "Bearer tnt_demo"},
    )
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=3600"

    body = resp.json()
    assert "sig=" not in body["tile_url"]
    assert body["minzoom"] == 0 and body["maxzoom"] == 10  # from A's manifest, D-14


def test_manifest_sigungu_prefers_real_vintage_over_fixture() -> None:
    """A published real sigungu output (2026-01-01) after the D-12 fixture
    already existed. The bare string "fixture" sorts after any "YYYY-MM-DD"
    string lexically, so a naive vintage sort would wrongly present the
    synthetic placeholder as "latest". Default (no ?vintage=) must resolve
    to the real dated vintage."""
    resp = client.get(
        "/v1/basemap/regions/manifest?level=sigungu",
        headers={"Authorization": "Bearer tnt_demo"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["boundary_vintage"] == "2026-01-01"
    assert set(body["available_vintages"]) == {"2026-01-01", "fixture"}


def test_manifest_sigungu_fixture_still_reachable_by_explicit_vintage() -> None:
    """D's integration fixture (verification/fixtures/vf_56_*) targets this
    exact vintage's .pmtiles — it must stay reachable even though it's no
    longer "latest"."""
    resp = client.get(
        "/v1/basemap/regions/manifest?level=sigungu&vintage=fixture",
        headers={"Authorization": "Bearer tnt_demo"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["boundary_vintage"] == "fixture"
    assert body["tile_url"].startswith("http://localhost:8000/artifacts/")


def test_manifest_specific_vintage() -> None:
    resp = client.get(
        "/v1/basemap/regions/manifest?level=sido&vintage=2026-01-01",
        headers={"Authorization": "Bearer tnt_demo"},
    )
    assert resp.status_code == 200
    assert resp.json()["boundary_vintage"] == "2026-01-01"


def test_manifest_unknown_vintage_is_404() -> None:
    resp = client.get(
        "/v1/basemap/regions/manifest?level=sido&vintage=1999-01-01",
        headers={"Authorization": "Bearer tnt_demo"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "BOUNDARY_VINTAGE_NOT_FOUND"


def test_manifest_unpublished_level_is_503_not_empty_list(monkeypatch) -> None:
    """D-13 / ADR-002 결정 3: all three real contract levels currently have
    real manifests on disk, so this forces the "A hasn't published yet"
    branch end-to-end through the router (not just the registry unit test)
    to confirm it actually reaches the client as 503, not a silently-empty
    available_vintages."""

    def _raise(level: str, vintage: str | None = None) -> dict:
        raise basemap_registry.NoBoundaryArtifactsError(level)

    monkeypatch.setattr(basemap_registry, "get_manifest", _raise)
    resp = client.get(
        "/v1/basemap/regions/manifest?level=adm_dong",
        headers={"Authorization": "Bearer tnt_demo"},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "BOUNDARY_MANIFEST_NOT_PUBLISHED"
