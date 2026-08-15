import gzip
import json
from pathlib import Path

import mapbox_vector_tile
import pytest
from pmtiles.reader import MemorySource, Reader

from src.boundary_tiles.build import SOURCE_LAYER, build_vintage
from src.boundary_tiles.feature_id import FeatureIdCollisionError, build_id_map, region_id_to_feature_id
from src.boundary_tiles.manifest import VintageExistsError, load_manifest

FIXTURES = Path(__file__).parent / "fixtures"


def test_feature_id_numeric_region_id_is_identity():
    assert region_id_to_feature_id("11") == 11
    assert region_id_to_feature_id("1168010600") == 1168010600


def test_feature_id_non_numeric_is_stable_and_js_safe():
    fid = region_id_to_feature_id("cst_01J8XK")
    assert fid == region_id_to_feature_id("cst_01J8XK")  # deterministic
    assert fid < 2**53 - 1  # JS Number.MAX_SAFE_INTEGER
    assert fid >= 0


def test_build_id_map_detects_collision(monkeypatch):
    # 강제로 같은 feature_id를 반환하도록 만들어 충돌 감지 로직 자체를 검증한다.
    import src.boundary_tiles.feature_id as feature_id_mod

    monkeypatch.setattr(feature_id_mod, "region_id_to_feature_id", lambda rid: 1)
    with pytest.raises(FeatureIdCollisionError):
        feature_id_mod.build_id_map(["a", "b"])


def test_build_vintage_end_to_end(tmp_path):
    entry = build_vintage(
        level="sido",
        vintage="2026-01-01",
        source_geojson_path=FIXTURES / "sido_sample_2026-01-01.geojson",
        output_root=tmp_path,
        source_id="src_sample_boundary",
    )

    # shared/contracts/04_api_contract.yaml 의 /basemap/regions/manifest 응답 예시와
    # 필드가 정확히 맞아야 backend가 이 entry를 거의 그대로 서빙할 수 있다.
    assert entry["level"] == "sido"
    assert entry["boundary_vintage"] == "2026-01-01"
    assert entry["source_layer"] == "regions"
    assert entry["feature_id_property"] == "region_id"
    assert entry["minzoom"] == 0
    assert entry["maxzoom"] == 8
    assert entry["available_vintages"] == ["2026-01-01"]
    assert entry["tile_url"] == "tiles/regions-sido-2026-01-01.pmtiles"

    pmtiles_path = tmp_path / entry["tile_url"]
    id_map_path = tmp_path / entry["id_map_path"]
    assert pmtiles_path.exists()
    assert id_map_path.exists()
    assert entry["feature_count"] == 5

    id_map = json.loads(id_map_path.read_text(encoding="utf-8"))
    assert id_map["region_id_to_feature_id"]["11"] == 11  # 서울
    assert id_map["feature_id_to_region_id"]["11"] == "11"

    # pmtiles를 실제로 읽어서 z=0 타일에 feature id가 제대로 들어갔는지 확인한다.
    reader = Reader(MemorySource(pmtiles_path.read_bytes()))
    header = reader.header()
    assert header["min_zoom"] == 0
    assert header["max_zoom"] == 8

    raw = reader.get(0, 0, 0)
    assert raw is not None
    decoded = mapbox_vector_tile.decode(gzip.decompress(raw))
    layer = decoded[SOURCE_LAYER]
    found_ids = {feat["id"] for feat in layer["features"]}
    assert found_ids  # z=0 타일 하나에 최소 한 지역은 걸려야 한다
    assert found_ids.issubset(set(id_map["region_id_to_feature_id"].values()))

    for feat in layer["features"]:
        # region_id는 feature id로만 실리고, 속성(properties)에는 없어야 한다.
        assert "region_id" not in feat["properties"]


def test_build_vintage_refuses_to_overwrite_same_vintage(tmp_path):
    kwargs = dict(
        level="sido",
        vintage="2026-01-01",
        source_geojson_path=FIXTURES / "sido_sample_2026-01-01.geojson",
        output_root=tmp_path,
        source_id="src_sample_boundary",
    )
    build_vintage(**kwargs)
    with pytest.raises(VintageExistsError):
        build_vintage(**kwargs)


def test_new_vintage_does_not_touch_previous_vintage_artifact_files(tmp_path):
    first = build_vintage(
        level="sido",
        vintage="2026-01-01",
        source_geojson_path=FIXTURES / "sido_sample_2026-01-01.geojson",
        output_root=tmp_path,
        source_id="src_sample_boundary",
    )
    first_pmtiles = tmp_path / first["tile_url"]
    first_bytes_before = first_pmtiles.read_bytes()
    first_id_map_before = (tmp_path / first["id_map_path"]).read_bytes()

    second = build_vintage(
        level="sido",
        vintage="2026-07-01",
        source_geojson_path=FIXTURES / "sido_sample_2026-07-01.geojson",
        output_root=tmp_path,
        source_id="src_sample_boundary",
        valid_to=None,
    )

    # 이전 vintage의 타일/id_map 파일 바이트가 그대로다 — 절대 덮어쓰지 않는다.
    assert first_pmtiles.read_bytes() == first_bytes_before
    assert (tmp_path / first["id_map_path"]).read_bytes() == first_id_map_before
    assert second["tile_url"] != first["tile_url"]

    manifest = load_manifest(tmp_path / "tiles" / "manifest.json")
    vintages_dict = manifest["levels"]["sido"]["vintages"]
    assert sorted(vintages_dict.keys()) == ["2026-01-01", "2026-07-01"]
    assert manifest["levels"]["sido"]["latest_vintage"] == "2026-07-01"

    # available_vintages는 "지금 존재하는 전체 목록"이라 새 vintage가 생기면
    # 예전 항목에서도 갱신된다 — 하지만 그 vintage 자체를 정의하는 다른 필드
    # (tile_url, sha256, feature_count 등)는 손대지 않는다.
    old_entry = vintages_dict["2026-01-01"]
    assert old_entry["available_vintages"] == ["2026-01-01", "2026-07-01"]
    assert old_entry["tile_url"] == first["tile_url"]
    assert old_entry["sha256"] == first["sha256"]
    assert old_entry["feature_count"] == first["feature_count"]
