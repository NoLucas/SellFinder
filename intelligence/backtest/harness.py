"""Step 3 backtest harness: 05_scoring_spec.md §5.

- §5.1: split by TIME, never randomly. A parallel region-holdout split runs
  alongside it, so "scored well" can't just mean "had already seen this
  region during training". `as_of` is pinned to each validation period's
  first day, matching 03_region_features.json's point_in_time_rule.
- §5.2: four metrics, all computed against `expected_demand_units` (units),
  not `expected_revenue_krw` - model.py's Step 2 scope deliberately leaves
  that null (Step 5, once the residual-distribution work lands; see
  model.py's module docstring). Spearman rho and top-decile lift need no
  calibration - they're rank/relative-magnitude only. wMAPE and PI coverage
  need a p50 point estimate and a [p10, p90] interval; since Step 5's real
  tenant-calibration model doesn't exist yet, `_calibrate_pi_multipliers`
  below builds a backtest-only empirical one: it collects actual/predicted
  ratios over the TRAINING periods only and takes their 10th/90th-percentile
  as multipliers on top of the raw `expected_demand_units` point estimate.
  This is not the Step 5 model and must not be presented as one - the model
  card records that distinction explicitly (§5.3's `known_limitations`).

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
_MIN_CALIBRATION_RATIOS = 30  # below this an empirical 10th/90th-percentile estimate is unstable


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


def wmape(predicted: list[float], actual: list[float]) -> float:
    """Sales-weighted MAPE. 05_scoring_spec.md §5.2: MAPE alone is banned
    because a region with actual near zero sends its own term toward
    infinity, and that one region can dominate a plain average, making
    model comparison meaningless. Dividing the total absolute error by
    total actual (rather than averaging per-region percentage errors)
    weights every region by its own sales volume automatically - a region
    with 5 actual units can't swing the score the way one with 5,000 can.
    """
    if len(predicted) != len(actual):
        raise ValueError("wmape: length mismatch")
    total_actual = sum(actual)
    if total_actual <= 0:
        raise ValueError("wmape: total actual is zero or negative - cannot compute")
    total_abs_error = sum(abs(a - p) for p, a in zip(predicted, actual))
    return total_abs_error / total_actual


def pi_coverage(lower: list[float], upper: list[float], actual: list[float]) -> float:
    """Fraction of actual values that fall inside [lower, upper]. 05_scoring_spec.md
    §5.2 v1 target (T2): 0.75-0.85 - if this is far from that band, the
    interval is either too narrow (false confidence) or too wide to be
    useful, and neither should be shown to a user as a confidence range."""
    if not (len(lower) == len(upper) == len(actual)):
        raise ValueError("pi_coverage: length mismatch")
    n = len(actual)
    if n == 0:
        raise ValueError("pi_coverage needs at least 1 point")
    covered = sum(1 for lo, hi, a in zip(lower, upper, actual) if lo <= a <= hi)
    return covered / n


def _quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated empirical quantile (stdlib only, matches the
    convention numpy/percentile-style tools use for 'linear' interpolation).
    """
    if not sorted_values:
        raise ValueError("quantile of an empty sequence")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return sorted_values[int(pos)]
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _collect_residual_ratios(
    store: SyntheticFeatureStore,
    region_ids: list[str],
    taxonomy_node_id: str,
    channel: str,
    periods: list[str],
    price_tier: str,
    product_attributes: dict | None,
    seasonality_profile: list[float] | None,
) -> list[float]:
    """actual / predicted expected_demand_units, collected only over
    `periods` (the caller must pass TRAINING periods - this function does
    not know or enforce which side of the split it's given, same as
    evaluate_period itself)."""
    ratios: list[float] = []
    for period in periods:
        as_of = f"{period}-01"
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
        for r in results:
            act = _actual_transaction_count(store, r.region_id, taxonomy_node_id, channel, period)
            if act is None or r.expected_demand_units <= 0:
                continue
            ratios.append(act / r.expected_demand_units)
    return ratios


def calibrate_pi_multipliers(
    store: SyntheticFeatureStore,
    region_ids: list[str],
    taxonomy_node_id: str,
    channel: str,
    train_periods: list[str],
    price_tier: str = "mid",
    product_attributes: dict | None = None,
    seasonality_profile: list[float] | None = None,
) -> tuple[float, float]:
    """Backtest-only empirical PI estimator (see module docstring - this is
    NOT the Step 5 tenant-calibration model). Returns (q10_multiplier,
    q90_multiplier): apply to a validation-period point estimate as
    `predicted * q10_multiplier` / `predicted * q90_multiplier` to get a
    [p10, p90] band. Raises if there isn't enough training-period data to
    calibrate a stable estimate - silently returning a degenerate interval
    would be worse than refusing to score coverage at all.
    """
    ratios = _collect_residual_ratios(
        store, region_ids, taxonomy_node_id, channel, train_periods, price_tier, product_attributes, seasonality_profile
    )
    if len(ratios) < _MIN_CALIBRATION_RATIOS:
        raise ValueError(
            f"only {len(ratios)} training residual ratios available (need >= {_MIN_CALIBRATION_RATIOS}) "
            "to calibrate a prediction interval - widen train_periods or region_ids"
        )
    ordered = sorted(ratios)
    return _quantile(ordered, 0.10), _quantile(ordered, 0.90)


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
    wmape: float
    pi_coverage: float


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
    pi_q10_multiplier: float,
    pi_q90_multiplier: float,
    price_tier: str = "mid",
    product_attributes: dict | None = None,
    seasonality_profile: list[float] | None = None,
) -> SplitResult | None:
    """Score one validation period. `expected_demand_units` (not the still-null
    expected_revenue_krw) is compared against realized transaction_count.
    `pi_q10_multiplier`/`pi_q90_multiplier` come from
    `calibrate_pi_multipliers()` run over the TRAINING side of the split -
    passed in rather than recomputed here so a caller can't accidentally
    calibrate and evaluate on the same periods.
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
    lower = [p * pi_q10_multiplier for p in predicted]
    upper = [p * pi_q90_multiplier for p in predicted]
    return SplitResult(
        period=period,
        n_regions=len(predicted),
        spearman_rho=spearman_rho(predicted, actual),
        top_decile_lift=top_decile_lift(predicted, actual),
        wmape=wmape(predicted, actual),
        pi_coverage=pi_coverage(lower, upper, actual),
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
    train_regions, holdout_regions = region_holdout_split(all_region_ids, seed=region_holdout_seed)

    assert_no_leakage_before_cutoff(store, all_region_ids, train_periods)

    # PI calibration uses only training periods (never validation periods -
    # that would leak the very thing coverage is supposed to measure), and
    # for the holdout run specifically uses only train_regions (never the
    # held-out regions) so the interval isn't calibrated on the same
    # regions its coverage is then evaluated against.
    all_q10, all_q90 = calibrate_pi_multipliers(
        store, all_region_ids, taxonomy_node_id, channel, train_periods,
        price_tier=price_tier, product_attributes=product_attributes, seasonality_profile=seasonality_profile,
    )
    holdout_q10, holdout_q90 = calibrate_pi_multipliers(
        store, train_regions, taxonomy_node_id, channel, train_periods,
        price_tier=price_tier, product_attributes=product_attributes, seasonality_profile=seasonality_profile,
    )

    def _run(region_ids: list[str], q10: float, q90: float) -> list[SplitResult]:
        out = []
        for period in val_periods:
            r = evaluate_period(
                store,
                region_ids,
                taxonomy_node_id,
                channel,
                period,
                q10,
                q90,
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
        "pi_calibration": {
            "all_regions": {"q10_multiplier": all_q10, "q90_multiplier": all_q90},
            "holdout_regions": {"q10_multiplier": holdout_q10, "q90_multiplier": holdout_q90},
        },
        "all_regions": _run(all_region_ids, all_q10, all_q90),
        "holdout_regions": _run(holdout_regions, holdout_q10, holdout_q90),
        "holdout_region_ids": holdout_regions,
    }
