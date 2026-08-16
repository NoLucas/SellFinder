"""Step 3 backtest harness: 05_scoring_spec.md §5.

- §5.1: split by TIME, never randomly. A parallel region-holdout split runs
  alongside it, so "scored well" can't just mean "had already seen this
  region during training". `as_of` is pinned to each validation period's
  first day, matching 03_region_features.json's point_in_time_rule.
- §5.2: Spearman rho (rank correlation) and top-decile lift are implemented
  below on ranks/relative magnitude, so neither needs calibrated revenue
  units. wMAPE and prediction-interval coverage need a real p10/p50/p90
  revenue estimate, which Step 2 deliberately does not produce yet
  (model.py's module docstring says so explicitly - that's Step 5 scope,
  once the residual-distribution work lands). Not implemented here rather
  than faked against a number that doesn't exist.

Leakage guard: `assert_no_leakage_before_cutoff` is not a claim in a
docstring, it is a function that runs against the real store on every
`run_backtest` call and raises if the planted trap
(synthetic/ground_truth.py's LEAKAGE_TRAP_FEATURE_KEY) is ever visible
before its cutoff. `tests/test_backtest.py` additionally proves the guard
has teeth by running it against `_leaky_latest_value`, a deliberately
broken as_of-ignoring accessor - see that module for the mutation-style
proof (mirrors how VF-001 was closed for the factor decomposition).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from scoring import model
from scoring.feature_store import SyntheticFeatureStore
from synthetic import ground_truth

_MIN_SCORABLE_REGIONS = 10  # below this a rank correlation is too noisy to mean anything


class LeakageDetectedError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# splits
# ---------------------------------------------------------------------------
def time_split(periods: list[str], cutoff: str) -> tuple[list[str], list[str]]:
    """05_scoring_spec.md §5.1: time-based split only, never random.
    `cutoff` is the first validation period; everything before it is train.
    """
    train = [p for p in periods if p < cutoff]
    validate = [p for p in periods if p >= cutoff]
    if not train or not validate:
        raise ValueError(f"cutoff {cutoff!r} produced an empty split: train={len(train)} validate={len(validate)}")
    return train, validate


def region_holdout_split(region_ids: list[str], seed: int, holdout_frac: float = 0.2) -> tuple[list[str], list[str]]:
    """05_scoring_spec.md §5.1: a region holdout reported alongside the time
    split. Sorted before shuffling so the split is reproducible regardless
    of the caller's set/dict iteration order.
    """
    ids = sorted(region_ids)
    rng = random.Random(seed)
    rng.shuffle(ids)
    cut = max(1, round(len(ids) * holdout_frac))
    holdout = sorted(ids[:cut])
    train = sorted(ids[cut:])
    return train, holdout


# ---------------------------------------------------------------------------
# metrics (05_scoring_spec.md §5.2)
# ---------------------------------------------------------------------------
def _ranks(values: list[float]) -> list[float]:
    """1-indexed ranks with ties resolved to their average rank (the
    standard Spearman convention)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman_rho(predicted: list[float], actual: list[float]) -> float:
    """Stdlib-only rank correlation - this repo has no scipy dependency
    anywhere else, so this doesn't introduce the first one."""
    if len(predicted) != len(actual):
        raise ValueError("spearman_rho: length mismatch")
    n = len(predicted)
    if n < 2:
        raise ValueError("spearman_rho needs at least 2 points")
    ra, rb = _ranks(predicted), _ranks(actual)
    mean_ra, mean_rb = sum(ra) / n, sum(rb) / n
    cov = sum((x - mean_ra) * (y - mean_rb) for x, y in zip(ra, rb))
    var_a = sum((x - mean_ra) ** 2 for x in ra)
    var_b = sum((y - mean_rb) ** 2 for y in rb)
    if var_a == 0 or var_b == 0:
        return 0.0
    return cov / math.sqrt(var_a * var_b)


def top_decile_lift(predicted: list[float], actual: list[float]) -> float:
    """Mean actual value among the top decile of predicted vs the overall
    mean actual value. 05_scoring_spec.md §5.2 v1 target (T2): >= 2.0."""
    if len(predicted) != len(actual):
        raise ValueError("top_decile_lift: length mismatch")
    n = len(predicted)
    if n == 0:
        raise ValueError("top_decile_lift needs at least 1 point")
    overall_mean = sum(actual) / n
    if overall_mean == 0:
        return 0.0
    order = sorted(range(n), key=lambda i: predicted[i], reverse=True)
    top_n = max(1, round(n * 0.1))
    top_mean = sum(actual[i] for i in order[:top_n]) / top_n
    return top_mean / overall_mean


# ---------------------------------------------------------------------------
# leakage guard
# ---------------------------------------------------------------------------
def assert_no_leakage_before_cutoff(
    store: SyntheticFeatureStore, region_ids: list[str], train_periods: list[str]
) -> None:
    """For every as_of in the training window, the leakage trap feature
    (synthetic/ground_truth.py's LEAKAGE_TRAP_FEATURE_KEY, valid_from=
    LEAKAGE_TRAP_CUTOFF) must come back None through the real,
    as_of-scoped store. Raises LeakageDetectedError if it doesn't - this is
    what actually enforces 05_scoring_spec.md §5.1's leakage rule at
    backtest time, not just a comment claiming it's true.
    """
    probe_regions = region_ids[: min(len(region_ids), 25)]
    for period in train_periods:
        as_of = f"{period}-01"
        if as_of >= ground_truth.LEAKAGE_TRAP_CUTOFF:
            continue  # a train period whose as_of is already at/after the cutoff legitimately may see it
        feats = store.get_features(probe_regions, [ground_truth.LEAKAGE_TRAP_FEATURE_KEY], as_of)
        leaked = {
            rid: row[ground_truth.LEAKAGE_TRAP_FEATURE_KEY]
            for rid, row in feats.items()
            if row[ground_truth.LEAKAGE_TRAP_FEATURE_KEY] is not None
        }
        if leaked:
            sample = dict(list(leaked.items())[:3])
            raise LeakageDetectedError(
                f"as_of={as_of} (training period {period!r}, before "
                f"{ground_truth.LEAKAGE_TRAP_CUTOFF}) saw a non-null "
                f"{ground_truth.LEAKAGE_TRAP_FEATURE_KEY} for {len(leaked)} region(s): {sample} ... "
                "- point-in-time leakage."
            )


def _leaky_latest_value(store: SyntheticFeatureStore, region_id: str, feature_key: str) -> object:
    """Deliberately broken accessor that ignores as_of and returns whatever
    row happens to be last (a stand-in for the classic "get the latest
    value" helper 03_region_features.json's point_in_time_rule forbids).
    Exists only so tests can prove the leakage guard has teeth against a
    real bug shape - never call this from run_backtest.
    """
    rows = store._by_region_feature.get((region_id, feature_key), [])
    if not rows:
        return None
    last = rows[-1]
    return last["value_json"] if last["value_json"] is not None else last["value_num"]


# ---------------------------------------------------------------------------
# per-period evaluation + full run
# ---------------------------------------------------------------------------
@dataclass
class SplitResult:
    period: str
    n_regions: int
    spearman_rho: float
    top_decile_lift: float


def _actual_transaction_count(
    store: SyntheticFeatureStore, region_id: str, taxonomy_node_id: str, channel: str, period: str
) -> float | None:
    demand = store.get_demand([region_id], taxonomy_node_id, channel, period)[region_id]
    if demand is None:
        return None
    return demand["transaction_count"]  # None on suppressed cells - propagates, never 0-filled


def evaluate_period(
    store: SyntheticFeatureStore,
    region_ids: list[str],
    taxonomy_node_id: str,
    channel: str,
    period: str,
    price_tier: str = "mid",
    product_attributes: dict | None = None,
    seasonality_profile: list[float] | None = None,
) -> SplitResult | None:
    """Score one validation period. `expected_demand_units` (not the still-null
    expected_revenue_krw) is compared against realized transaction_count -
    both metrics below are rank/relative-magnitude based so unmatched units
    don't distort them.
    """
    as_of = f"{period}-01"  # §5.1: as_of pinned to the target period's start
    results = model.predict_batch(
        region_ids=region_ids,
        taxonomy_node_id=taxonomy_node_id,
        channel=channel,
        period=period,
        as_of=as_of,
        data_tier="T0",
        store=store,
        product_attributes=product_attributes or {},
        price_tier=price_tier,
        seasonality_profile=seasonality_profile,
        horizon_months=1,
    )
    predicted: list[float] = []
    actual: list[float] = []
    for r in results:
        act = _actual_transaction_count(store, r.region_id, taxonomy_node_id, channel, period)
        if act is None:
            continue  # suppressed or no demand row for this cell - excluded, never 0-filled
        predicted.append(r.expected_demand_units)
        actual.append(act)
    if len(predicted) < _MIN_SCORABLE_REGIONS:
        return None
    return SplitResult(
        period=period,
        n_regions=len(predicted),
        spearman_rho=spearman_rho(predicted, actual),
        top_decile_lift=top_decile_lift(predicted, actual),
    )


def run_backtest(
    dataset: dict,
    store: SyntheticFeatureStore,
    taxonomy_node_id: str,
    channel: str,
    train_cutoff: str,
    price_tier: str = "mid",
    product_attributes: dict | None = None,
    seasonality_profile: list[float] | None = None,
    region_holdout_seed: int = 42,
) -> dict:
    """Full §5.1 harness: time split + region holdout, scored only on the
    validation side of the time split (that's what "backtest" means - never
    the periods the model's benchmarks were computed over).
    """
    periods = dataset["manifest"]["periods"]
    train_periods, val_periods = time_split(periods, train_cutoff)
    all_region_ids = store.all_adm_dong_ids()
    _, holdout_regions = region_holdout_split(all_region_ids, seed=region_holdout_seed)

    assert_no_leakage_before_cutoff(store, all_region_ids, train_periods)

    def _run(region_ids: list[str]) -> list[SplitResult]:
        out = []
        for period in val_periods:
            r = evaluate_period(
                store,
                region_ids,
                taxonomy_node_id,
                channel,
                period,
                price_tier=price_tier,
                product_attributes=product_attributes,
                seasonality_profile=seasonality_profile,
            )
            if r is not None:
                out.append(r)
        return out

    return {
        "train_periods": train_periods,
        "validation_periods": val_periods,
        "all_regions": _run(all_region_ids),
        "holdout_regions": _run(holdout_regions),
        "holdout_region_ids": holdout_regions,
    }
