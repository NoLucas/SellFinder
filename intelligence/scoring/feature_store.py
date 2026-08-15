"""The get_features(region_ids, feature_keys, as_of) interface.

03_region_features.json's point_in_time_rule is explicit: "as_of 없이
'최신값'을 가져오는 헬퍼는 만들지 않는다. 만들면 반드시 누가 학습에 쓴다."
So this module deliberately does NOT expose any "get latest value" path -
every read goes through as_of. synthetic/README.md's leakage trap only
works as a detector because this rule is actually followed here.

This is a synthetic-data-backed implementation of the interface (Step 1's
generator is the data source). The real /data-platform-backed
implementation (open question #1 in RECONCILIATION.md) should satisfy
the exact same method signatures - FeatureStore is written as a small
Protocol so model.py never has to know which one it's talking to.
"""
from __future__ import annotations

from typing import Protocol


class FeatureStore(Protocol):
    def get_features(
        self, region_ids: list[str], feature_keys: list[str], as_of: str
    ) -> dict[str, dict[str, object]]: ...

    def get_demand(
        self, region_ids: list[str], taxonomy_node_id: str, channel: str, period: str
    ) -> dict[str, dict[str, object]]: ...


def _row_value(row: dict) -> object:
    return row["value_json"] if row["value_json"] is not None else row["value_num"]


class SyntheticFeatureStore:
    """FeatureStore backed by generate.generate_all()'s in-memory output."""

    def __init__(self, dataset: dict):
        self._by_region_feature: dict[tuple, list[dict]] = {}
        for row in dataset["region_features"]:
            key = (row["region_id"], row["feature_key"])
            self._by_region_feature.setdefault(key, []).append(row)
        for rows in self._by_region_feature.values():
            rows.sort(key=lambda r: r["valid_from"])

        self._demand_index: dict[tuple, dict] = {}
        for row in dataset["demand_signal"]:
            key = (row["region_id"], row["taxonomy_node_id"], row["channel"], row["period"])
            self._demand_index[key] = row

        self._regions_by_id = {r["region_id"]: r for r in dataset["regions"]}

    @classmethod
    def from_dataset(cls, dataset: dict) -> "SyntheticFeatureStore":
        return cls(dataset)

    def get_features(
        self, region_ids: list[str], feature_keys: list[str], as_of: str
    ) -> dict[str, dict[str, object]]:
        """valid_from <= as_of < COALESCE(valid_to, 'infinity') - per constraint in
        01_domain_model.json's region_feature entity. No fallback to "nearest" or
        "latest" value: a feature not yet valid at as_of comes back as None.
        """
        out: dict[str, dict[str, object]] = {}
        for region_id in region_ids:
            out[region_id] = {}
            for key in feature_keys:
                rows = self._by_region_feature.get((region_id, key), [])
                value = None
                for row in rows:
                    if row["valid_from"] <= as_of and (row["valid_to"] is None or as_of < row["valid_to"]):
                        value = _row_value(row)
                        break
                out[region_id][key] = value
        return out

    def get_demand(
        self, region_ids: list[str], taxonomy_node_id: str, channel: str, period: str
    ) -> dict[str, dict[str, object]]:
        out: dict[str, dict[str, object]] = {}
        for region_id in region_ids:
            row = self._demand_index.get((region_id, taxonomy_node_id, channel, period))
            out[region_id] = (
                {
                    "spend_krw": row["spend_krw"],
                    "transaction_count": row["transaction_count"],
                    "store_count": row["store_count"],
                    "spend_index": row["spend_index"],
                    "coverage_flag": row["coverage_flag"],
                }
                if row is not None
                else None
            )
        return out

    def region_meta(self, region_id: str) -> dict:
        return self._regions_by_id[region_id]

    def all_adm_dong_ids(self) -> list[str]:
        return [rid for rid, r in self._regions_by_id.items() if r["level"] == "adm_dong"]
