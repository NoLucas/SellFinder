import gzip
import json
from pathlib import Path

import mapbox_vector_tile
import pytest
from pmtiles.reader import MemorySource, Reader

from src.boundary_tiles.build import build_vintage
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

    pmtiles_path = tmp_path / entry["pmtiles_path"]
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
    layer = decoded["sido"]
    found_ids = {feat["id"] for feat in layer["features"]}
    assert found_ids  # z=0 타일 하나에 최소 한 지역은 걸려야 한다
    assert found_ids.issubset(set(id_map["region_id_to_feature_id"].values()))

    for feat in layer["features"]:
        assert "region_id" not in feat["properties"]  # 브리프 지시사항: 속성이 아니라 id


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


def test_new_vintage_does_not_touch_previous_vintage_files(tmp_path):
    first = build_vintage(
        level="sido",
        vintage="2026-01-01",
        source_geojson_path=FIXTURES / "sido_sample_2026-01-01.geojson",
        output_root=tmp_path,
        source_id="src_sample_boundary",
    )
    first_pmtiles = tmp_path / first["pmtiles_path"]
    first_bytes_before = first_pmtiles.read_bytes()

    second = build_vintage(
        level="sido",
        vintage="2026-07-01",
        source_geojson_path=FIXTURES / "sido_sample_2026-07-01.geojson",
        output_root=tmp_path,
        source_id="src_sample_boundary",
        valid_to=None,
    )

    # 이전 vintage 파일이 그대로다 (바이트 단위로 불변).
    assert first_pmtiles.read_bytes() == first_bytes_before
    assert second["pmtiles_path"] != first["pmtiles_path"]

    manifest = load_manifest(tmp_path / "tiles" / "manifest.json")
    vintages = [e["vintage"] for e in manifest["levels"]["sido"]]
    assert vintages == ["2026-01-01", "2026-07-01"]  # 둘 다 남아있고, 오래된 순 정렬
