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

import json
from pathlib import Path
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


def _select_value_at(rows: list[dict], as_of: str) -> object:
    """01_domain_model.json's region_feature constraint, applied identically
    everywhere a FeatureStore filters by as_of: valid_from <= as_of <
    COALESCE(valid_to, 'infinity'). `rows` must already be sorted by
    valid_from. No "latest value" fallback exists anywhere in this
    function - a feature not yet valid at as_of comes back None, full stop
    (03_region_features.json's point_in_time_rule: "as_of 없이 '최신값'을
    가져오는 헬퍼는 만들지 않는다. 만들면 반드시 누가 학습에 쓴다.").
    """
    for row in rows:
        if row["valid_from"] <= as_of and (row["valid_to"] is None or as_of < row["valid_to"]):
            return _row_value(row)
    return None


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
                out[region_id][key] = _select_value_at(rows, as_of)
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


_REQUIRED_ROW_FIELDS = ("region_id", "feature_key", "valid_from", "source_id", "ingested_at")


def _validate_region_feature_row(row: dict, source_path: Path) -> None:
    missing = [f for f in _REQUIRED_ROW_FIELDS if f not in row]
    if missing:
        raise ValueError(
            f"{source_path}: region_feature row missing required field(s) {missing} "
            f"(01_domain_model.json's region_feature entity requires them): {row!r}"
        )
    if row.get("value_num") is None and row.get("value_json") is None:
        # this is legal (missingness is real - "05 spec never 0-fill"), not an error.
        pass


class RegionFeatureFileStore:
    """Reads region_feature rows from JSON files on disk - the reader for
    data-platform(A)'s real published output, matching 01_domain_model.json's
    region_feature entity exactly: region_id, feature_key, value_num,
    value_json, valid_from, valid_to, source_id, ingested_at.

    As of 2026-08-16, data-platform has not published any region_feature
    files yet - `find data-platform/output -type f` shows only boundary-tile
    manifests (regions-*.json under output/manifest/, *.pmtiles under
    output/tiles/), nothing shaped like a region_feature row. This class is
    therefore built directly against the CONTRACT schema above (not against
    an artifact that doesn't exist) and tested against
    tests/fixtures/region_features_fixture/*.json, which is hand-written to
    match that schema exactly. The moment A publishes real files in this
    shape, pointing `from_directory()` at that path is the only change
    needed - `get_features()`'s as_of semantics are identical to
    SyntheticFeatureStore's (same `_select_value_at` helper), so nothing
    else in model.py or a caller has to change.

    `get_demand()` deliberately raises NotImplementedError: data-platform
    has not published (or even specified an output shape for) demand_signal
    yet, either. Returning synthetic-looking numbers from a class whose
    whole point is "this is the real one" would be exactly the kind of
    invented value DISPATCH-2.md §9 warns against. A caller needing demand
    data must wait for that artifact or compose a separate demand source -
    this class does not fake one.
    """

    def __init__(self, rows: list[dict]):
        self._by_region_feature: dict[tuple, list[dict]] = {}
        for row in rows:
            key = (row["region_id"], row["feature_key"])
            self._by_region_feature.setdefault(key, []).append(row)
        for group in self._by_region_feature.values():
            group.sort(key=lambda r: r["valid_from"])

    @classmethod
    def from_directory(cls, directory: str | Path) -> "RegionFeatureFileStore":
        directory = Path(directory)
        json_files = sorted(directory.glob("*.json"))
        if not json_files:
            raise FileNotFoundError(
                f"no region_feature files found under {directory} - data-platform has not "
                "published any as of this writing (see intelligence/README.md §2). "
                "This is not a bug to work around - do not fall back to synthetic data here."
            )
        rows: list[dict] = []
        for path in json_files:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError(f"{path}: expected a JSON array of region_feature rows, got {type(data).__name__}")
            for row in data:
                _validate_region_feature_row(row, path)
                rows.append(row)
        return cls(rows)

    def get_features(
        self, region_ids: list[str], feature_keys: list[str], as_of: str
    ) -> dict[str, dict[str, object]]:
        """Identical as_of semantics to SyntheticFeatureStore.get_features -
        valid_from <= as_of < COALESCE(valid_to, 'infinity'), no "latest"
        fallback. See _select_value_at."""
        out: dict[str, dict[str, object]] = {}
        for region_id in region_ids:
            out[region_id] = {}
            for key in feature_keys:
                rows = self._by_region_feature.get((region_id, key), [])
                out[region_id][key] = _select_value_at(rows, as_of)
        return out

    def get_demand(
        self, region_ids: list[str], taxonomy_node_id: str, channel: str, period: str
    ) -> dict[str, dict[str, object]]:
        raise NotImplementedError(
            "RegionFeatureFileStore has no demand_signal source - data-platform hasn't "
            "published one yet. See this class's docstring and intelligence/README.md."
        )
