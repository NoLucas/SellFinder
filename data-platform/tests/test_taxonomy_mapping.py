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


# ---------------------------------------------------------------------------
# VF-013류 자체 점검 (총괄자 4차 지시): C 는 값은 막았는데 정렬 순서가 원시값을
# 반영해 상대 크기가 새는 부채널을 냈다. 여기서는 같은 종류의 결함이 A 의
# 파이프라인(집계·순위 산출)에 있는지 직접 확인한다.
# ---------------------------------------------------------------------------


def test_two_suppressed_cells_in_same_sido_are_indistinguishable_in_output():
    """원시값이 달라도(0 대 4개 등) 같은 sido 안에서는 같은 대체값을 받아야 한다.

    다르게 나온다면 그건 대체값 산정 어딘가에 원시값이 새고 있다는 뜻이다 —
    VF-013 이 "값은 막았는데 순서가 원시 크기를 반영"했던 것과 같은 실패 모양.
    """
    taxonomy = load_taxonomy()
    mappable = [m for m in leaf_mappings(taxonomy) if m.resolution in ("direct", "inherited")]
    node_id = mappable[0].node_id

    region_ids = [f"41{i:03d}" for i in range(1, 200)]
    raws = {rid: _mock_raw_store_count(rid, node_id) for rid in region_ids}
    suppressed_pairs = [
        (rid, raw) for rid, raw in raws.items() if raw < SUPPRESSION_THRESHOLD_STORES
    ]
    distinct_raw_values = {raw for _, raw in suppressed_pairs}
    assert len(distinct_raw_values) >= 2, "같은 sido 안에서 서로 다른 원시값을 가진 억제 셀 쌍을 못 찾았다 — 리전 표본을 넓혀야 한다"

    rows = build_demand_signal(region_ids, mappable, period="2026-01")
    suppressed_rows = {r.region_id: r.store_count for r in rows if r.taxonomy_node_id == node_id and r.coverage_flag == "suppressed"}

    output_values_for_suppressed = {suppressed_rows[rid] for rid, _raw in suppressed_pairs}
    # 원시값이 여럿이었는데 출력값 종류가 그대로 여럿이면(원시값 가짓수만큼) 의심스럽다.
    # 올바른 구현은 "같은 sido"라는 한 가지 대체값으로 수렴해야 한다.
    assert len(output_values_for_suppressed) == 1, (
        f"억제 셀들의 원시값은 {distinct_raw_values} 로 서로 달랐는데 출력 store_count 가 "
        f"{output_values_for_suppressed} 로 갈라졌다 — 원시값이 대체 로직에 새고 있다"
    )


def test_national_mean_and_sido_substitute_never_derived_from_suppressed_raw_values():
    """spend_index 계산에 쓰이는 national_mean 이 억제 원시값을 단 하나도 섞지 않는지
    외부에서 독립적으로 재계산해 대조한다(합이 아니라 증인을 세우는 방식, VF-001 교훈)."""
    taxonomy = load_taxonomy()
    mappable = [m for m in leaf_mappings(taxonomy) if m.resolution in ("direct", "inherited")]
    node_id = mappable[0].node_id
    region_ids = [f"41{i:03d}" for i in range(1, 300)]

    rows = build_demand_signal(region_ids, mappable, period="2026-01")
    node_rows = [r for r in rows if r.taxonomy_node_id == node_id]

    raws = {rid: _mock_raw_store_count(rid, node_id) for rid in region_ids}
    independent_actual_only = [v for v in raws.values() if v >= SUPPRESSION_THRESHOLD_STORES]
    assert independent_actual_only  # 표본에 actual 이 없으면 이 테스트가 무의미하다
    independent_mean = sum(independent_actual_only) / len(independent_actual_only)

    # actual 행들의 spend_index 를 거꾸로 풀어 파이프라인이 실제로 쓴 national_mean 을
    # 복원한다. spend_index 는 소수 1자리로 반올림돼 저장되므로(_spend_index), 행 하나만
    # 역산하면 반올림 오차(최대 ±0.05/spend_index, 실측 약 0.05%)가 낀다 — 여러 actual
    # 행에 걸쳐 평균해 그 반올림 잡음을 지운다(대수의 법칙). 그래도 남는 오차는
    # 반올림 크기 수준(상대 0.5%)까지만 허용한다 — 그 이상 벌어지면 반올림이 아니라
    # 실제로 다른 값(억제 원시값 혼입)에서 왔다고 봐야 한다.
    actual_rows = [r for r in node_rows if r.coverage_flag == "actual"]
    assert len(actual_rows) >= 10, "반올림 잡음을 평균으로 지우기엔 actual 표본이 너무 적다"
    recovered_means = [100.0 * r.store_count / r.spend_index for r in actual_rows]
    recovered_mean = sum(recovered_means) / len(recovered_means)

    relative_diff = abs(recovered_mean - independent_mean) / independent_mean
    assert relative_diff < 0.005, (
        "파이프라인이 쓴 national_mean 이 '억제 제외 실측치만의 평균'과 다르다 — "
        "억제된 원시값이 평균 계산에 섞여 들어갔을 가능성이 있다"
    )


def test_sorting_output_by_store_count_does_not_recover_raw_suppressed_ranking():
    """VF-013 이 정확히 이 모양이었다: 값은 가렸는데 정렬하면 원래 크기 순서가 드러남.

    전체 출력을 store_count 로 정렬했을 때, 같은 sido 의 억제 셀들 사이 순서가
    원시값 순서와 우연히도 일치하면 안 된다 —애초에 전부 동일값(위 테스트)이라
    "동순위"가 되어야 하고, 정렬 알고리즘이 원시값을 타이브레이커로 쓰지 않는지도 확인.
    """
    taxonomy = load_taxonomy()
    mappable = [m for m in leaf_mappings(taxonomy) if m.resolution in ("direct", "inherited")]
    node_id = mappable[0].node_id
    region_ids = [f"41{i:03d}" for i in range(1, 200)]

    rows = build_demand_signal(region_ids, mappable, period="2026-01")
    node_rows = [r for r in rows if r.taxonomy_node_id == node_id]
    suppressed = [r for r in node_rows if r.coverage_flag == "suppressed"]
    assert len(suppressed) >= 2

    # 정렬 자체가 그냥 딕셔너리/리스트 필드(store_count)만 보고 이뤄지므로, raw 값을
    # 몰래 참조하는 별도 정렬 키가 코드 어디에도 없음을 데이터클래스 필드로도 확인한다.
    from dataclasses import fields

    field_names = {f.name for f in fields(type(suppressed[0]))}
    assert "raw_store_count" not in field_names
    assert not any(k.startswith("_raw") for k in field_names)

    sorted_by_output = sorted(suppressed, key=lambda r: (r.store_count, r.region_id))
    sorted_by_true_raw = sorted(suppressed, key=lambda r: (_mock_raw_store_count(r.region_id, node_id), r.region_id))
    # 억제 셀은 전부 같은 sido 대체값으로 수렴하므로(위 테스트), store_count 정렬은
    # 진짜 순위가 아니라 region_id 타이브레이커 순서와 같아야 한다 — 즉 store_count 자체가
    # 이미 원시 순위를 구분하지 못한다는 뜻이다.
    output_order_region_ids = [r.region_id for r in sorted_by_output]
    tiebreaker_only_order = [r.region_id for r in sorted(suppressed, key=lambda r: r.region_id)]
    assert output_order_region_ids == tiebreaker_only_order, (
        "store_count 로 정렬한 순서가 region_id 타이브레이커만으로 정렬한 것과 다르다 — "
        "store_count 가 억제 셀 사이에서도 서로 달라 원시 크기 순서를 구분하고 있다는 뜻"
    )
