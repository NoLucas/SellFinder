"""region_feature.commercial.store_count_by_node / income_spend.spend_index_by_node
를 이미 발행한 `demand_signal`(DISPATCH-2 §9)에서 파생시킨다.

`03_region_features.json` 이 두 피처 모두 "demand_signal 에서 파생"이라고 이미
명시한다 — 별도 수집이 아니라 순수 파생(aggregation)이다. 그래서 새 데이터
소스 탐색 없이 지금 바로 착수 가능하다(DISPATCH-5 두 번째 과제의 "착수 가능한
것부터" 항목).

**억제(coverage_flag='suppressed') 값도 그대로 포함한다** — demand_signal 쪽에서
이미 원시값이 아니라 대체값으로 안전하게 처리됐으므로(§9.2, §10.3) 여기서 다시
거를 필요가 없다. 다만 taxonomy_node 자체가 sbiz 매핑이 없어 demand_signal 행이
아예 없는 노드는(§9.1, 34/36개) 당연히 여기도 안 나타난다 — 조용한 0 채움이
아니라 애초에 입력에 없다.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.region_features.writer import RegionFeatureRow


def _period_to_valid_from(period: str) -> str:
    """'2026-01' -> '2026-01-01'."""
    return f"{period}-01"


def derive_rows(demand_signal_path: Path, valid_to: str | None = None) -> list[RegionFeatureRow]:
    with demand_signal_path.open("r", encoding="utf-8") as f:
        ds_rows = json.load(f)
    if not ds_rows:
        return []

    period = ds_rows[0]["period"]
    valid_from = _period_to_valid_from(period)
    ingested_at = datetime.now(timezone.utc).isoformat()

    store_count_by_region: dict[str, dict[str, int | None]] = {}
    spend_index_by_region: dict[str, dict[str, float | None]] = {}
    source_id_by_region: dict[str, str] = {}

    for row in ds_rows:
        rid = row["region_id"]
        node = row["taxonomy_node_id"]
        store_count_by_region.setdefault(rid, {})[node] = row["store_count"]
        spend_index_by_region.setdefault(rid, {})[node] = row["spend_index"]
        source_id_by_region[rid] = row["source_id"]  # demand_signal 이 이미 source_id 를 갖고 있다

    out: list[RegionFeatureRow] = []
    for rid, by_node in store_count_by_region.items():
        out.append(
            RegionFeatureRow(
                region_id=rid, feature_key="store_count_by_node",
                valid_from=valid_from, valid_to=valid_to,
                source_id=source_id_by_region[rid], ingested_at=ingested_at,
                value_json=by_node,
            )
        )
    for rid, by_node in spend_index_by_region.items():
        out.append(
            RegionFeatureRow(
                region_id=rid, feature_key="spend_index_by_node",
                valid_from=valid_from, valid_to=valid_to,
                source_id=source_id_by_region[rid], ingested_at=ingested_at,
                value_json=by_node,
            )
        )
    return out
