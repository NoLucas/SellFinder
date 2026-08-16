import pytest

from src.boundary_tiles.sgis_source import (
    CONSUMER_KEY_ENV,
    CONSUMER_SECRET_ENV,
    SgisCredentials,
    SgisCredentialsMissingError,
    fetch_boundary_geojson,
)


def test_missing_credentials_fails_closed_not_silently(monkeypatch):
    """자격증명이 없으면 예외로 멈춰야 한다 — 합성 데이터로 조용히 대체하면 안 된다."""
    monkeypatch.delenv(CONSUMER_KEY_ENV, raising=False)
    monkeypatch.delenv(CONSUMER_SECRET_ENV, raising=False)
    with pytest.raises(SgisCredentialsMissingError):
        SgisCredentials.from_env()


def test_fetch_boundary_geojson_requires_credentials_before_anything_else(monkeypatch, tmp_path):
    monkeypatch.delenv(CONSUMER_KEY_ENV, raising=False)
    monkeypatch.delenv(CONSUMER_SECRET_ENV, raising=False)
    with pytest.raises(SgisCredentialsMissingError):
        fetch_boundary_geojson("adm_dong", "2024-01-01", tmp_path / "out.geojson")


def test_fetch_boundary_geojson_is_explicitly_unimplemented_once_credentials_exist(monkeypatch, tmp_path):
    """자격증명이 있어도 아직 미구현임을 분명한 예외로 알려야 한다 — 조용한 no-op 금지."""
    monkeypatch.setenv(CONSUMER_KEY_ENV, "dummy")
    monkeypatch.setenv(CONSUMER_SECRET_ENV, "dummy")
    with pytest.raises(NotImplementedError):
        fetch_boundary_geojson("adm_dong", "2024-01-01", tmp_path / "out.geojson")
