import gzip
import json
from pathlib import Path

import mapbox_vector_tile
import pytest
from pmtiles.reader import MemorySource, Reader

import src.boundary_tiles.tiler as tiler_mod
from src.boundary_tiles.build import SOURCE_LAYER, build_vintage
from src.boundary_tiles.feature_id import FeatureIdCollisionError, build_id_map, region_id_to_feature_id
from src.boundary_tiles.manifest import VintageExistsError, load_manifest
from src.boundary_tiles.tiler import TileJoinKeyVerificationError

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
    assert entry["maxzoom"] == 10  # D-14 / ADR-002 결정 4
    assert entry["available_vintages"] == ["2026-01-01"]
    assert entry["tile_url"] == "http://localhost:8000/artifacts/tiles/regions-sido-2026-01-01.pmtiles"
    assert "id_map_path" not in entry  # ADR-005 결정 4: 계약 산출물에서 제외

    pmtiles_path = tmp_path / "tiles" / "regions-sido-2026-01-01.pmtiles"
    id_map_path = tmp_path / "tiles" / "regions-sido-2026-01-01.id_map.json"
    assert pmtiles_path.exists()
    assert id_map_path.exists()  # 내부 디버깅용 산출물로는 계속 남는다
    assert entry["feature_count"] == 5

    # 계약 인수인계물: output/manifest/regions-{level}-{vintage}.json 이 C 의 입력이다(D-13).
    per_vintage_manifest_path = tmp_path / "manifest" / "regions-sido-2026-01-01.json"
    assert per_vintage_manifest_path.exists()
    on_disk_entry = json.loads(per_vintage_manifest_path.read_text(encoding="utf-8"))
    assert on_disk_entry == entry

    id_map = json.loads(id_map_path.read_text(encoding="utf-8"))
    assert id_map["region_id_to_feature_id"]["11"] == 11  # 서울
    assert id_map["feature_id_to_region_id"]["11"] == "11"

    # pmtiles를 실제로 읽어서 z=0 타일에 feature id가 제대로 들어갔는지 확인한다.
    reader = Reader(MemorySource(pmtiles_path.read_bytes()))
    header = reader.header()
    assert header["min_zoom"] == 0
    assert header["max_zoom"] == 10

    raw = reader.get(0, 0, 0)
    assert raw is not None
    decoded = mapbox_vector_tile.decode(gzip.decompress(raw))
    layer = decoded[SOURCE_LAYER]
    found_ids = {feat["id"] for feat in layer["features"]}
    assert found_ids  # z=0 타일 하나에 최소 한 지역은 걸려야 한다
    assert found_ids.issubset(set(id_map["region_id_to_feature_id"].values()))

    region_ids_in_tile = set()
    for feat in layer["features"]:
        # ADR-005/D-20: region_id는 조인 키로 properties 에 원문 문자열 그대로 실린다.
        assert "region_id" in feat["properties"]
        region_ids_in_tile.add(feat["properties"]["region_id"])
    assert region_ids_in_tile.issubset(set(id_map["region_id_to_feature_id"].keys()))


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
    first_pmtiles = tmp_path / "tiles" / "regions-sido-2026-01-01.pmtiles"
    first_id_map = tmp_path / "tiles" / "regions-sido-2026-01-01.id_map.json"
    first_bytes_before = first_pmtiles.read_bytes()
    first_id_map_before = first_id_map.read_bytes()

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
    assert first_id_map.read_bytes() == first_id_map_before
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

    # 두 번째 빈티지의 계약 인수인계 매니페스트 파일도 별도로 생겨야 한다.
    assert (tmp_path / "manifest" / "regions-sido-2026-01-01.json").exists()
    assert (tmp_path / "manifest" / "regions-sido-2026-07-01.json").exists()


def test_build_fails_when_feature_id_property_missing_from_tile(tmp_path, monkeypatch):
    """A-3 / ADR-005: 광고한 feature_id_property 가 실제 타일에 없으면 빌드가 실패해야 한다.

    일부러 region_id 속성을 지운 BoundaryFeature 를 만들어 파이프라인에 흘려보낸다.
    이 테스트가 통과(=예외 없이 끝남)하면 A-3 자체검증이 가짜라는 뜻이다.
    """
    real_load = tiler_mod.load_boundary_features

    def stripped_load(feature_collection, id_map):
        features = real_load(feature_collection, id_map)
        return [
            tiler_mod.BoundaryFeature(
                region_id=f.region_id,
                feature_id=f.feature_id,
                properties={k: v for k, v in f.properties.items() if k != "region_id"},
                geometry=f.geometry,
            )
            for f in features
        ]

    monkeypatch.setattr(tiler_mod, "load_boundary_features", stripped_load)
    import src.boundary_tiles.build as build_mod

    monkeypatch.setattr(build_mod, "load_boundary_features", stripped_load)

    with pytest.raises(TileJoinKeyVerificationError):
        build_vintage(
            level="sido",
            vintage="2026-01-01",
            source_geojson_path=FIXTURES / "sido_sample_2026-01-01.geojson",
            output_root=tmp_path,
            source_id="src_sample_boundary",
        )

    # 실패한 빌드는 어떤 산출물도 매니페스트에 등록해서는 안 된다.
    assert not (tmp_path / "manifest" / "regions-sido-2026-01-01.json").exists()
    manifest = load_manifest(tmp_path / "tiles" / "manifest.json")
    assert "sido" not in manifest.get("levels", {})
