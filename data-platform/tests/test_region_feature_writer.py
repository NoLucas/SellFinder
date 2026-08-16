import json

import pytest

from src.region_features.writer import (
    RegionFeatureRow,
    RegionFeatureValidationError,
    load_feature_registry,
    write_region_features,
)

SOURCE = "src_mois_population"
INGESTED = "2026-08-17T00:00:00+00:00"


def test_registry_excludes_tenant_scoped_keys():
    registry = load_feature_registry()
    assert "pop_total" in registry
    assert "single_household_ratio" in registry
    # tenant_scoped 4개는 A 의 공개 파이프라인 대상이 아니다 (backend/tenant_sales 소유)
    for key, spec in registry.items():
        assert spec.get("_category") != "tenant_scoped"


def test_unregistered_feature_key_rejected(tmp_path):
    row = RegionFeatureRow(
        region_id="11650", feature_key="not_a_real_feature",
        valid_from="2026-01-01", valid_to=None,
        source_id=SOURCE, ingested_at=INGESTED, value_num=1.0,
    )
    with pytest.raises(RegionFeatureValidationError):
        write_region_features([row], tmp_path)


def test_type_mismatch_rejected(tmp_path):
    # pop_total 은 type=number 인데 value_json 을 채우면 거부돼야 한다.
    row = RegionFeatureRow(
        region_id="11650", feature_key="pop_total",
        valid_from="2026-01-01", valid_to=None,
        source_id=SOURCE, ingested_at=INGESTED, value_json={"oops": 1},
    )
    with pytest.raises(RegionFeatureValidationError):
        write_region_features([row], tmp_path)


def test_missing_source_id_rejected(tmp_path):
    row = RegionFeatureRow(
        region_id="11650", feature_key="pop_total",
        valid_from="2026-01-01", valid_to=None,
        source_id="", ingested_at=INGESTED, value_num=100.0,
    )
    with pytest.raises(RegionFeatureValidationError):
        write_region_features([row], tmp_path)


def test_missing_value_is_explicit_null_not_zero(tmp_path):
    """feature_quality_rules: 결측은 0 이 아니라 null 로 남긴다 (행은 존재한다)."""
    row = RegionFeatureRow(
        region_id="11650", feature_key="pop_total",
        valid_from="2026-01-01", valid_to=None,
        source_id=SOURCE, ingested_at=INGESTED, value_num=None,
    )
    written = write_region_features([row], tmp_path)
    data = json.loads(written["pop_total"].read_text(encoding="utf-8"))
    assert data[0]["value_num"] is None
    assert data[0]["region_id"] == "11650"  # 행 자체는 살아있다 - 0 으로 채워지지 않았을 뿐


def test_overlapping_valid_periods_rejected(tmp_path):
    rows = [
        RegionFeatureRow(
            region_id="11650", feature_key="pop_total",
            valid_from="2026-01-01", valid_to="2026-07-01",
            source_id=SOURCE, ingested_at=INGESTED, value_num=100.0,
        ),
        RegionFeatureRow(
            region_id="11650", feature_key="pop_total",
            valid_from="2026-05-01", valid_to=None,  # 겹침: 05-01 < 07-01
            source_id=SOURCE, ingested_at=INGESTED, value_num=110.0,
        ),
    ]
    with pytest.raises(RegionFeatureValidationError):
        write_region_features(rows, tmp_path)


def test_adjacent_non_overlapping_periods_are_fine(tmp_path):
    rows = [
        RegionFeatureRow(
            region_id="11650", feature_key="pop_total",
            valid_from="2026-01-01", valid_to="2026-07-01",
            source_id=SOURCE, ingested_at=INGESTED, value_num=100.0,
        ),
        RegionFeatureRow(
            region_id="11650", feature_key="pop_total",
            valid_from="2026-07-01", valid_to=None,  # valid_to 는 배타적 상한이라 안 겹침
            source_id=SOURCE, ingested_at=INGESTED, value_num=105.0,
        ),
    ]
    written = write_region_features(rows, tmp_path)
    data = json.loads(written["pop_total"].read_text(encoding="utf-8"))
    assert len(data) == 2


def test_json_type_feature_round_trips(tmp_path):
    row = RegionFeatureRow(
        region_id="11650", feature_key="pop_age_dist",
        valid_from="2026-01-01", valid_to=None,
        source_id=SOURCE, ingested_at=INGESTED,
        value_json={"0_9": 0.08, "10s": 0.09, "20s": 0.15, "30s": 0.18, "40s": 0.16, "50s": 0.15, "60plus": 0.19},
    )
    written = write_region_features([row], tmp_path)
    data = json.loads(written["pop_age_dist"].read_text(encoding="utf-8"))
    assert abs(sum(data[0]["value_json"].values()) - 1.0) < 0.01


def test_writes_are_grouped_one_file_per_feature_key(tmp_path):
    rows = [
        RegionFeatureRow(
            region_id="11650", feature_key="pop_total",
            valid_from="2026-01-01", valid_to=None,
            source_id=SOURCE, ingested_at=INGESTED, value_num=100.0,
        ),
        RegionFeatureRow(
            region_id="41135", feature_key="pop_total",
            valid_from="2026-01-01", valid_to=None,
            source_id=SOURCE, ingested_at=INGESTED, value_num=200.0,
        ),
        RegionFeatureRow(
            region_id="11650", feature_key="household_count",
            valid_from="2026-01-01", valid_to=None,
            source_id=SOURCE, ingested_at=INGESTED, value_num=50.0,
        ),
    ]
    written = write_region_features(rows, tmp_path)
    assert set(written.keys()) == {"pop_total", "household_count"}
    pop_total_rows = json.loads(written["pop_total"].read_text(encoding="utf-8"))
    assert len(pop_total_rows) == 2

    # RegionFeatureFileStore.from_directory 가 기대하는 필드가 전부 있는지 직접 확인
    # (intelligence/ 를 import 하지 않는다 - 계약 스키마만으로 대조, 폴더 경계 유지)
    required = {"region_id", "feature_key", "value_num", "value_json", "valid_from", "valid_to", "source_id", "ingested_at"}
    for row in pop_total_rows:
        assert required.issubset(row.keys())
