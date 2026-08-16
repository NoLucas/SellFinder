"""Unit tests for app.services.basemap_registry that exercise paths the
live /v1/basemap/regions/manifest endpoint can no longer reach now that A
has published real data for all three contract levels (sido/sigungu/
adm_dong) - the endpoint's `level` Query pattern only accepts those three,
so D-13's "manifest file absent" 503 branch needs a level string outside
that enum to trigger, which only a direct registry call can supply."""
import pytest

from app.services import basemap_registry


def test_unpublished_level_raises_not_a_false_empty_list() -> None:
    with pytest.raises(basemap_registry.NoBoundaryArtifactsError):
        basemap_registry.get_manifest("gu")  # not a real contract level


def test_latest_vintage_unpublished_level_raises() -> None:
    with pytest.raises(basemap_registry.NoBoundaryArtifactsError):
        basemap_registry.latest_vintage("gu")


def test_known_levels_resolve() -> None:
    for level in ("sido", "sigungu", "adm_dong"):
        manifest = basemap_registry.get_manifest(level)
        assert manifest["level"] == level
        assert manifest["available_vintages"]
