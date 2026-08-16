"""sbiz 원천으로부터 `demand_signal` 행을 만든다 (01_domain_model.json 스키마).

**지금은 실제 sbiz API 연동 전이다** (A-3 이 그 착수 작업). 이 모듈은 결정론적
합성(mock) 점포 관측치로 파이프라인 구조 — 매핑 해석, k-익명성 억제, spend_krw
null 고정 — 를 검증한다. `data_source` 레지스트리에도 이 사실을 숨기지 않는다
(is_synthetic_placeholder=true).

**절대 규칙 두 가지**:
1. sbiz 매핑이 없는(직접도 상속도 없는) taxonomy_node 는 그 어떤 지역에 대해서도
   `demand_signal` 행을 만들지 않는다 (D-19, `02_taxonomy.json` public_data_mapping_note).
   0으로 채우지 않는다 — 행 자체가 없다.
2. k-익명성 임계(06_governance.md §2.3, 셀당 점포 5개 미만) 미달 관측치의
   **원시값은 어떤 산출물에도 남기지 않는다.** 상위(sido) 지역의 비억제 평균으로
   대체하거나, 그마저 없으면 null 로 둔다.
"""
from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.taxonomy_mapping.sbiz_mapping import LeafMapping

SUPPRESSION_THRESHOLD_STORES = 5  # 06_governance.md §2.3
SOURCE_ID = "src_sbiz_market"  # 06_governance.md §3 등록 예시와 동일 id


def _mock_raw_store_count(region_id: str, node_id: str) -> int:
    """결정론적 합성 관측치. 실 API 연동(A-3) 전까지의 자리표시자.

    시드는 (region_id, node_id) 조합의 sha256 이라 재현 가능하고, 지역/노드
    조합마다 값이 달라진다. 일부러 낮은 값이 자주 나오게 해 억제 대상이
    실제로 만들어지도록 한다 — 그래야 C 의 VF-010 차단이 뭔가를 차단해본다.
    """
    digest = hashlib.sha256(f"{region_id}|{node_id}".encode("utf-8")).digest()
    roll = int.from_bytes(digest[:2], "big") / 65535  # [0, 1)
    if roll < 0.18:
        # 저밀도 상권: 억제 대상이 나오도록 의도적으로 낮은 구간
        return int.from_bytes(digest[2:3], "big") % SUPPRESSION_THRESHOLD_STORES  # 0..4
    # 일반 상권: 5~60개 사이
    return 5 + int.from_bytes(digest[3:5], "big") % 56


def sido_prefix(region_id: str) -> str:
    return region_id[:2]


@dataclass
class DemandSignalRow:
    region_id: str
    taxonomy_node_id: str
    channel: str
    period: str
    spend_krw: None
    transaction_count: None
    store_count: int | None
    spend_index: float | None
    coverage_flag: str
    source_id: str

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "taxonomy_node_id": self.taxonomy_node_id,
            "channel": self.channel,
            "period": self.period,
            "spend_krw": self.spend_krw,
            "transaction_count": self.transaction_count,
            "store_count": self.store_count,
            "spend_index": self.spend_index,
            "coverage_flag": self.coverage_flag,
            "source_id": self.source_id,
        }


def _spend_index(store_count: int | None, national_mean: float) -> float | None:
    """store_count 만을 근거로 한 전국 대비 지수(100=전국 평균).

    card_mcc 라이선스 미확보라 절대 소비금액을 낼 수 없다(ADR-004) — 그 대체로
    "점포 수와 지역 소비력 프록시"를 쓰라는 지시를 store_count 자기 자신의
    전국 평균 대비 비율로 구현했다. 다른 소비력 프록시(소득분위 등)는 아직
    region_feature 에 없어(§5 미착수) 지금은 이 값 하나뿐이다 — spend_krw 처럼
    금액을 지어내지 않는다.
    """
    if store_count is None or national_mean <= 0:
        return None
    return round(100.0 * store_count / national_mean, 1)


def build_demand_signal(
    region_ids: list[str],
    mappable_leaves: list[LeafMapping],
    period: str,
    channel: str = "all",
) -> list[DemandSignalRow]:
    """매핑이 있는(direct/inherited) 리프 노드에 한해서만 지역별 행을 만든다.

    `mappable_leaves` 에 resolution="none" 인 노드를 넣으면 안 된다 —
    호출자가 이미 `sbiz_mapping.coverage_report()` 로 걸러낸 목록을 넘긴다는
    계약이다. (여기서도 방어적으로 한 번 더 걸러 조용한 0 채움을 원천 차단한다.)
    """
    mappable_leaves = [m for m in mappable_leaves if m.resolution in ("direct", "inherited")]

    rows: list[DemandSignalRow] = []
    for leaf in mappable_leaves:
        raw_by_region: dict[str, int] = {
            rid: _mock_raw_store_count(rid, leaf.node_id) for rid in region_ids
        }

        # sido 별 "억제되지 않은" 관측치 평균 — 대체값 후보(06 §2.3: 상위 지역 값으로 대체)
        sido_actual_values: dict[str, list[int]] = {}
        for rid, raw in raw_by_region.items():
            if raw >= SUPPRESSION_THRESHOLD_STORES:
                sido_actual_values.setdefault(sido_prefix(rid), []).append(raw)

        actual_raw_values = [v for v in raw_by_region.values() if v >= SUPPRESSION_THRESHOLD_STORES]
        national_mean = statistics.mean(actual_raw_values) if actual_raw_values else 0.0

        for rid, raw in raw_by_region.items():
            if raw >= SUPPRESSION_THRESHOLD_STORES:
                store_count = raw
                coverage_flag = "actual"
            else:
                # 원시값(raw)은 여기서 소멸한다 — 아래 어떤 필드에도 대입하지 않는다.
                siblings = sido_actual_values.get(sido_prefix(rid))
                store_count = round(statistics.mean(siblings)) if siblings else None
                coverage_flag = "suppressed"

            rows.append(
                DemandSignalRow(
                    region_id=rid,
                    taxonomy_node_id=leaf.node_id,
                    channel=channel,
                    period=period,
                    spend_krw=None,  # ADR-004: card_mcc 없이는 항상 null
                    transaction_count=None,  # sbiz 는 거래건수를 주지 않는다
                    store_count=store_count,
                    spend_index=_spend_index(store_count, national_mean),
                    coverage_flag=coverage_flag,
                    source_id=SOURCE_ID,
                )
            )
    return rows


def data_source_entry(built_at: datetime | None = None) -> dict:
    """06_governance.md §3 등록 예시 형식의 data_source 레지스트리 항목.

    ADR-004 "A 가 할 일" #3 의 known_limitations 를 그대로 옮긴다.
    """
    return {
        "source_id": SOURCE_ID,
        "name": "소상공인시장진흥공단 상권정보",
        "provider": "소상공인시장진흥공단",
        "url": "https://sg.sbiz.or.kr",  # 03_region_features.json recommended_public_sources 와 동일
        "license": "공공누리 제1유형",
        "commercial_use_allowed": True,
        "refresh_cadence": "quarterly",
        "granularity": "sigungu / quarterly",
        "known_limitations": [
            "분기 갱신으로 최대 3개월 시차",
            "무점포 사업자 미포함",
            "대형 유통 채널 일부 누락",
        ],
        "last_ingested_at": (built_at or datetime.now(timezone.utc)).isoformat(),
        # 계약 스키마엔 없는 리니지 플래그 — A-3(실 SGIS/sbiz 연동) 전까지는 참이다.
        "is_synthetic_placeholder": True,
    }
