from pathlib import Path

from src.taxonomy_mapping.demand_signal import (
    SUPPRESSION_THRESHOLD_STORES,
    _mock_raw_store_count,
    build_demand_signal,
    data_source_entry,
)
from src.taxonomy_mapping.sbiz_mapping import coverage_report, leaf_mappings, load_taxonomy

REGION_IDS = [f"41{i:03d}" for i in range(1, 41)] + [f"11{i:03d}" for i in range(1, 11)]


def test_coverage_report_never_marks_a_node_as_mapped_without_a_real_sbiz_code():
    taxonomy = load_taxonomy()
    report = coverage_report(taxonomy)
    mappings = {m.node_id: m for m in leaf_mappings(taxonomy)}

    for node_id in report["direct"] + report["inherited"]:
        assert mappings[node_id].sbiz_codes, f"{node_id} 는 매핑됐다는데 실제 sbiz_codes 가 비어 있다"
    for node_id in report["none"]:
        assert mappings[node_id].sbiz_codes is None

    assert report["mappable_count"] + report["unmappable_count"] == report["total_leaf_nodes"]
    # 지금 계약 스냅샷 기준 실측치 — 값이 바뀌면(=계약에 매핑이 추가되면) 이 테스트가
    # 시끄럽게 깨지는 게 맞다. 조용히 넘어가면 안 되는 변화다.
    assert report["direct"] == ["TX-FOOD-BEV-COFFEE-RTD", "TX-FNB-CAFE"]
    assert report["inherited"] == []


def test_unmapped_leaf_never_produces_a_demand_signal_row():
    """D-19 핵심: 매핑 없는 노드는 행 자체가 없어야 한다. 0 으로 채우면 안 된다."""
    taxonomy = load_taxonomy()
    mappings = leaf_mappings(taxonomy)
    mappable = [m for m in mappings if m.resolution in ("direct", "inherited")]
    unmappable_ids = {m.node_id for m in mappings if m.resolution == "none"}
    assert unmappable_ids  # 지금 계약 스냅샷엔 34개가 있어야 이 테스트가 의미 있다

    rows = build_demand_signal(REGION_IDS, mappable, period="2026-01")

    row_node_ids = {r.taxonomy_node_id for r in rows}
    assert row_node_ids.isdisjoint(unmappable_ids)
    assert row_node_ids == {"TX-FOOD-BEV-COFFEE-RTD", "TX-FNB-CAFE"}
    # 매핑 없는 노드를 실수로 섞어 넣어도(방어적 필터) 조용히 통과하면 안 된다는 걸 확인.
    taxonomy_none_leaf = next(m for m in mappings if m.resolution == "none")
    rows_with_bad_input = build_demand_signal(REGION_IDS, mappable + [taxonomy_none_leaf], period="2026-01")
    assert taxonomy_none_leaf.node_id not in {r.taxonomy_node_id for r in rows_with_bad_input}


def test_spend_krw_is_always_null_no_card_mcc_license():
    taxonomy = load_taxonomy()
    mappable = [m for m in leaf_mappings(taxonomy) if m.resolution in ("direct", "inherited")]
    rows = build_demand_signal(REGION_IDS, mappable, period="2026-01")
    assert rows
    assert all(r.spend_krw is None for r in rows)
    assert all(r.transaction_count is None for r in rows)


def test_suppression_threshold_hides_raw_value_and_flags_suppressed():
    """06_governance.md §2.3: 셀당 점포 5개 미만이면 원시값을 노출하지 않는다."""
    taxonomy = load_taxonomy()
    mappable = [m for m in leaf_mappings(taxonomy) if m.resolution in ("direct", "inherited")]
    rows = build_demand_signal(REGION_IDS, mappable, period="2026-01")

    suppressed = [r for r in rows if r.coverage_flag == "suppressed"]
    actual = [r for r in rows if r.coverage_flag == "actual"]
    assert suppressed, "이 지역/노드/시드 조합에서 억제 대상이 하나도 없다 — A-2 의 목적(실제 억제 셀을 산출물에 싣는 것)이 충족되지 않는다"
    assert actual

    for r in suppressed:
        raw = _mock_raw_store_count(r.region_id, r.taxonomy_node_id)
        assert raw < SUPPRESSION_THRESHOLD_STORES
        # 대체값(상위 지역 평균) 또는 null 이어야 하고, 절대 원시값 그대로여서는 안 된다.
        assert r.store_count is None or r.store_count != raw
        if r.store_count is not None:
            assert r.store_count >= SUPPRESSION_THRESHOLD_STORES or r.store_count != raw

    for r in actual:
        raw = _mock_raw_store_count(r.region_id, r.taxonomy_node_id)
        assert raw >= SUPPRESSION_THRESHOLD_STORES
        assert r.store_count == raw


def test_data_source_entry_matches_governance_registration_example_shape():
    entry = data_source_entry()
    for key in (
        "source_id", "name", "license", "commercial_use_allowed",
        "refresh_cadence", "granularity", "known_limitations",
    ):
        assert key in entry
    assert entry["source_id"] == "src_sbiz_market"
    assert entry["commercial_use_allowed"] is True
    assert entry["is_synthetic_placeholder"] is True  # 실 API 연동 전이라는 사실을 숨기지 않는다


def test_build_cli_writes_manifest_artifacts(tmp_path):
    from src.taxonomy_mapping.build import build

    region_source = Path(__file__).parent / "fixtures" / "sigungu_sample_fixture.geojson"
    summary = build(output_root=tmp_path, region_source=region_source, period="2026-01")

    assert summary["leaf_nodes_unmappable"] > 0
    assert summary["rows_suppressed"] > 0
    assert summary["demand_signal_rows"] == summary["rows_actual"] + summary["rows_suppressed"]

    assert (tmp_path / "manifest" / "taxonomy_sbiz_coverage.json").exists()
    assert (tmp_path / "manifest" / "demand_signal-sigungu-2026-01.json").exists()
    assert (tmp_path / "manifest" / "data_source-src_sbiz_market.json").exists()
