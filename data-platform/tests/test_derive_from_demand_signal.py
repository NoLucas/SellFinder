import json

from src.region_features.derive_from_demand_signal import derive_rows
from src.region_features.writer import load_feature_registry, write_region_features

SAMPLE_DS = [
    {
        "region_id": "41135", "taxonomy_node_id": "TX-FOOD-BEV-COFFEE-RTD",
        "channel": "all", "period": "2026-01", "spend_krw": None, "transaction_count": None,
        "store_count": 48, "spend_index": 149.5, "coverage_flag": "actual", "source_id": "src_sbiz_market",
    },
    {
        "region_id": "41135", "taxonomy_node_id": "TX-FNB-CAFE",
        "channel": "all", "period": "2026-01", "spend_krw": None, "transaction_count": None,
        "store_count": 12, "spend_index": 80.1, "coverage_flag": "actual", "source_id": "src_sbiz_market",
    },
    {
        "region_id": "11650", "taxonomy_node_id": "TX-FOOD-BEV-COFFEE-RTD",
        "channel": "all", "period": "2026-01", "spend_krw": None, "transaction_count": None,
        "store_count": 28, "spend_index": 87.2, "coverage_flag": "suppressed", "source_id": "src_sbiz_market",
    },
]


def test_derive_groups_by_region_into_node_keyed_json(tmp_path):
    src = tmp_path / "demand_signal-sigungu-2026-01.json"
    src.write_text(json.dumps(SAMPLE_DS, ensure_ascii=False), encoding="utf-8")

    rows = derive_rows(src)
    store_count_rows = [r for r in rows if r.feature_key == "store_count_by_node"]
    spend_index_rows = [r for r in rows if r.feature_key == "spend_index_by_node"]

    by_region = {r.region_id: r for r in store_count_rows}
    assert by_region["41135"].value_json == {"TX-FOOD-BEV-COFFEE-RTD": 48, "TX-FNB-CAFE": 12}
    assert by_region["11650"].value_json == {"TX-FOOD-BEV-COFFEE-RTD": 28}
    assert all(r.valid_from == "2026-01-01" for r in store_count_rows)
    assert all(r.source_id == "src_sbiz_market" for r in store_count_rows)
    assert len(spend_index_rows) == 2


def test_suppressed_demand_signal_rows_still_included_since_already_safe(tmp_path):
    """demand_signal 의 store_count 는 이미 안전한 대체값이므로(§9.2) 여기서 다시 거를 필요가 없다."""
    src = tmp_path / "demand_signal-sigungu-2026-01.json"
    src.write_text(json.dumps(SAMPLE_DS, ensure_ascii=False), encoding="utf-8")

    rows = derive_rows(src)
    row_11650 = next(r for r in rows if r.feature_key == "store_count_by_node" and r.region_id == "11650")
    assert row_11650.value_json["TX-FOOD-BEV-COFFEE-RTD"] == 28  # SAMPLE_DS 의 대체값 그대로, raw 아님


def test_derived_rows_pass_the_real_writer_validation(tmp_path):
    """파생 결과가 writer.py 의 타입/스키마 검증을 실제로 통과하는지 — mock 이 아니라
    실제 write_region_features 를 호출해 RegionFeatureFileStore 호환 파일이 나오는지 본다."""
    src = tmp_path / "demand_signal-sigungu-2026-01.json"
    src.write_text(json.dumps(SAMPLE_DS, ensure_ascii=False), encoding="utf-8")

    rows = derive_rows(src)
    written = write_region_features(rows, tmp_path / "region_features", registry=load_feature_registry())
    assert set(written.keys()) == {"store_count_by_node", "spend_index_by_node"}

    data = json.loads(written["store_count_by_node"].read_text(encoding="utf-8"))
    required = {"region_id", "feature_key", "value_num", "value_json", "valid_from", "valid_to", "source_id", "ingested_at"}
    for row in data:
        assert required.issubset(row.keys())
        assert row["value_num"] is None  # json 타입 피처이므로 value_num 은 항상 비어야 한다
