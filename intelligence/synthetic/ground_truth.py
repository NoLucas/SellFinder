"""Planted relationships + the leakage trap.

The brief is explicit: don't scatter random data, plant answers a model
should be able to recover, and record the exact coefficients so recovery
is checkable later. Every relationship here is grounded in a real note
already present in 02_taxonomy.json (e.g. "1인가구 비중·야간 유동인구와
상관 높음" for HMR) so the plant isn't arbitrary.

Each relationship multiplies demand_signal.spend_index for one
taxonomy_node when a region's *profile* (see feature_gen.build_region_profiles)
clears a quantile threshold on some derived metric. Thresholds are
resolved to concrete numbers against the actual generated region set
(not hardcoded) so they stay correct regardless of --regions/--seed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


def _age_2030_share(profile: dict) -> float:
    dist = profile["pop_age_dist"]
    return dist["20s"] + dist["30s"]


@dataclass(frozen=True)
class RelationshipDef:
    id: str
    taxonomy_node_id: str
    derive: Callable[[dict], float]
    derived_metric_name: str
    quantile: float  # e.g. 0.75 = top quartile
    multiplier: float
    description: str
    extra_condition: Callable[[dict], bool] | None = None
    extra_condition_desc: str | None = None


RELATIONSHIP_DEFS: list[RelationshipDef] = [
    RelationshipDef(
        id="rtd_coffee_young_affluent",
        taxonomy_node_id="TX-FOOD-BEV-COFFEE-RTD",
        derive=_age_2030_share,
        derived_metric_name="age_2030_share",
        quantile=0.75,
        multiplier=1.6,
        description=(
            "20-30대 인구 비중 상위 25% 지역이면서 income_decile>=7인 지역은 "
            "RTD 커피 spend_index가 1.6배."
        ),
        extra_condition=lambda p: p["income_decile"] >= 7,
        extra_condition_desc="income_decile >= 7",
    ),
    RelationshipDef(
        id="hmr_single_household",
        taxonomy_node_id="TX-FOOD-PROC-HMR",
        derive=lambda p: p["single_household_ratio"],
        derived_metric_name="single_household_ratio",
        quantile=0.667,
        multiplier=1.4,
        description="1인가구 비중 상위 1/3 지역은 간편식(HMR) spend_index가 1.4배.",
    ),
    RelationshipDef(
        id="babyfood_birth_rate",
        taxonomy_node_id="TX-KIDS-BABYFOOD",
        derive=lambda p: p["birth_count_12m"],
        derived_metric_name="birth_count_12m",
        quantile=0.75,
        multiplier=1.8,
        description="최근 12개월 출생아 수 상위 25% 지역은 분유·이유식 spend_index가 1.8배.",
    ),
    RelationshipDef(
        id="large_appliance_new_apartments",
        taxonomy_node_id="TX-ELEC-LARGE",
        derive=lambda p: p["new_apartment_units_12m"],
        derived_metric_name="new_apartment_units_12m",
        quantile=0.75,
        multiplier=1.5,
        description="최근 12개월 신규 입주 물량 상위 25% 지역은 대형가전 spend_index가 1.5배.",
    ),
    RelationshipDef(
        id="pet_supplies_registration",
        taxonomy_node_id="TX-LIVING-PET",
        derive=lambda p: p["pet_registered_count"],
        derived_metric_name="pet_registered_count",
        quantile=0.75,
        multiplier=1.5,
        description="반려동물 등록 두수 상위 25% 지역은 반려동물 용품 spend_index가 1.5배.",
    ),
]


def resolve_relationships(profiles: dict[str, dict]) -> list[dict]:
    """Turn declarative RelationshipDefs into concrete, checkable specs.

    For each relationship: compute the metric for every region, resolve
    the quantile to a real cutoff value, and list exactly which region_ids
    qualify. This resolved form is what gets written to ground_truth.json -
    a later validator doesn't need this module at all, just the JSON.
    """
    region_ids = sorted(profiles.keys())
    resolved = []
    for rel in RELATIONSHIP_DEFS:
        values = {rid: rel.derive(profiles[rid]) for rid in region_ids}
        sorted_vals = sorted(values.values())
        idx = min(int(len(sorted_vals) * rel.quantile), len(sorted_vals) - 1)
        cutoff = sorted_vals[idx]
        qualifying = [
            rid
            for rid in region_ids
            if values[rid] >= cutoff and (rel.extra_condition is None or rel.extra_condition(profiles[rid]))
        ]
        resolved.append(
            {
                "id": rel.id,
                "taxonomy_node_id": rel.taxonomy_node_id,
                "target_field": "demand_signal.spend_index",
                "derived_metric": rel.derived_metric_name,
                "quantile_threshold": rel.quantile,
                "resolved_cutoff_value": round(cutoff, 4),
                "extra_condition": rel.extra_condition_desc,
                "multiplier": rel.multiplier,
                "description": rel.description,
                "qualifying_region_count": len(qualifying),
                "qualifying_region_ids": qualifying,
            }
        )
    return resolved


def multiplier_for(region_id: str, taxonomy_node_id: str, profiles: dict[str, dict], resolved: list[dict]) -> float:
    """1.0 unless region_id qualifies for a planted relationship on this node."""
    mult = 1.0
    for rel in resolved:
        if rel["taxonomy_node_id"] == taxonomy_node_id and region_id in rel["qualifying_region_ids"]:
            mult *= rel["multiplier"]
    return mult


# ---------------------------------------------------------------------------
# Leakage trap
# ---------------------------------------------------------------------------
# A region_feature key that does NOT exist in 03_region_features.json's
# registry - it must never be treated as a real contract feature. It only
# has rows from LEAKAGE_TRAP_CUTOFF onward, and its value is computed FROM
# the region's *future* (validation-window) RTD-coffee spend_index - i.e.
# it's a stand-in for the classic real-world accident (a "current period
# performance" column that's actually computed after the fact and joined
# back onto historical training rows).
#
# A backtest harness that correctly restricts region_feature reads to
# valid_from <= as_of will simply never see this feature during training
# (as_of < cutoff => no rows exist yet => null). A harness that grabs
# "the latest value regardless of as_of" will pull in a near-perfect
# predictor of the thing it's trying to predict, and Spearman rho on the
# training-period backtest will look suspiciously close to 1.0. That
# mismatch is the detector.
LEAKAGE_TRAP_FEATURE_KEY = "leak_trap_future_rtd_signal"
LEAKAGE_TRAP_CUTOFF = "2026-01-01"
LEAKAGE_TRAP_SOURCE_NODE = "TX-FOOD-BEV-COFFEE-RTD"
LEAKAGE_TRAP_DESCRIPTION = (
    "NOT a real contract feature (absent from 03_region_features.json's feature_registry). "
    "Exists only from valid_from=2026-01-01 onward, and its value is derived from each region's "
    "own 2026-01..2026-06 (validation-window) RTD-coffee spend_index. A correctly as_of-scoped "
    "backtest harness must never see this feature for as_of < 2026-01-01 - if it does (or if a "
    "'get latest feature value' helper is used anywhere), the harness has a leakage bug. "
    "See 03_region_features.json's point_in_time_rule."
)
