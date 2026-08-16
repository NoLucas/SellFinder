import json

import pytest

from src.boundary_tiles.admdongkor_source import convert_to_pipeline_geojson, raw_url

SAMPLE_RAW = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "adm_nm": "서울특별시 종로구 사직동",
                "adm_cd2": "1111053000",
                "sgg": "11110",
                "sido": "11",
                "sidonm": "서울특별시",
                "sggnm": "종로구",
                "adm_cd": "11010530",
            },
            "geometry": {"type": "Polygon", "coordinates": [[[126.9, 37.5], [127.0, 37.5], [127.0, 37.6], [126.9, 37.6], [126.9, 37.5]]]},
        },
        {
            "type": "Feature",
            "properties": {
                "adm_nm": "서울특별시 종로구 삼청동",
                "adm_cd2": "1111054000",
                "sgg": "11110",
                "sido": "11",
                "sidonm": "서울특별시",
                "sggnm": "종로구",
                "adm_cd": "11010540",
            },
            "geometry": {"type": "Polygon", "coordinates": [[[127.0, 37.5], [127.1, 37.5], [127.1, 37.6], [127.0, 37.6], [127.0, 37.5]]]},
        },
    ],
}


def test_raw_url_matches_known_repo_layout():
    assert raw_url("20260701") == (
        "https://raw.githubusercontent.com/vuski/admdongkor/master/"
        "ver20260701/HangJeongDong_ver20260701.geojson"
    )


def test_convert_maps_adm_cd2_to_region_id_and_flags_non_synthetic(tmp_path):
    src = tmp_path / "raw.geojson"
    src.write_text(json.dumps(SAMPLE_RAW, ensure_ascii=False), encoding="utf-8")

    fc = convert_to_pipeline_geojson(src)

    assert len(fc["features"]) == 2
    ids = {f["properties"]["region_id"] for f in fc["features"]}
    assert ids == {"1111053000", "1111054000"}
    for f in fc["features"]:
        assert f["properties"]["is_synthetic_placeholder"] is False
        assert f["properties"]["level"] == "adm_dong"
        assert "region_id" in f["properties"]
    # sido/sgg 는 상위 레벨 dissolve 용으로 보존돼야 한다
    assert all(f["properties"]["sido"] == "11" for f in fc["features"])
    assert all(f["properties"]["sgg"] == "11110" for f in fc["features"])


def test_convert_rejects_duplicate_region_id_instead_of_silently_dropping(tmp_path):
    dup_raw = {
        "type": "FeatureCollection",
        "features": [SAMPLE_RAW["features"][0], SAMPLE_RAW["features"][0]],
    }
    src = tmp_path / "raw_dup.geojson"
    src.write_text(json.dumps(dup_raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError):
        convert_to_pipeline_geojson(src)
