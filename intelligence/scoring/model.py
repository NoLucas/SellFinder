"""Step 2 model skeleton: orchestrates the 8 factors into one prediction.

Scope note: this implements 05_scoring_spec.md §1 (the factor model) only.
It deliberately does NOT implement:
  - opportunity_score (needs the full requested region set + percentile
    ranking - that's tied up with §3's per-objective ranking, Step 6)
  - expected_revenue_krw as an actual p10/p50/p90 estimate (needs the
    Step 3 backtest's residual distribution - Step 5)
  - the SKU classifier's taxonomy_node_id/price_tier assignment (Step 4)
So callers pass taxonomy_node_id/channel/price_tier in directly for now
rather than a full `product` domain object.

What it DOES guarantee (see tests/test_factor_model.py):
  - Σ factors[].log_contribution == ln(total_multiplier), to float precision
  - competition is always <= 1
  - online channels never see foot_traffic/competitor_density inputs
  - T0 => expected_revenue_krw is null (enforced by assert_t0_revenue_null,
    not just "happens to be None")
  - identical inputs => byte-identical output (no hidden randomness)

T1/T2 tenant_calibration (f8, 05_scoring_spec.md §2) is implemented via an
optional `calibration_profile` param (tenant_layer.TenantCalibrationProfile)
threaded through predict_one/predict_batch. It reaches ONLY f8 - see
tenant_layer.py's module docstring and tests/test_tenant_isolation.py for
06_governance.md §1.4's isolation guarantee.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import factors, tenant_layer
from .feature_store import FeatureStore

_CHANNEL_TYPE_CACHE: dict[str, str] | None = None


def channel_type_of(channel: str) -> str:
    """Looks up 'offline'/'online'/'b2b' from 02_taxonomy.json's channels -
    single source of truth, so callers never have to hardcode it (and can't
    accidentally mislabel an online channel as offline and slip past the
    competition/channel_availability guards)."""
    global _CHANNEL_TYPE_CACHE
    if _CHANNEL_TYPE_CACHE is None:
        from synthetic import contracts

        _CHANNEL_TYPE_CACHE = {
            cid: meta["type"] for cid, meta in contracts.channels().items() if not cid.startswith("$")
        }
    return _CHANNEL_TYPE_CACHE[channel]


REGION_FEATURE_KEYS = [
    "pop_total",
    "pop_age_dist",
    "daytime_pop",
    "income_decile",
]

# fallback assumptions for taxonomy nodes with no curated demand_gen params
# (see synthetic/demand_gen.py's NODE_PARAMS for the curated set) - matches
# 02_taxonomy.json's own escape hatch: "매핑이 비어있는 노드는... '데이터
# 부족'으로 표기" - base_volume here is intentionally small/generic rather
# than invented-precise.
_DEFAULT_TXN_RATE_PER_1000POP = 40.0


class ExpectedRevenueOnT0Error(ValueError):
    pass


def assert_t0_revenue_null(data_tier: str, expected_revenue_krw: dict | None) -> None:
    """05_scoring_spec.md §2 / §8: T0 tenants must never receive a revenue
    estimate. This is called unconditionally by predict_one() - it isn't
    just "the code happens not to compute one for T0", it's an assertion
    that fires even if a future change accidentally starts computing one.
    """
    if data_tier == "T0" and expected_revenue_krw is not None:
        raise ExpectedRevenueOnT0Error(
            "T0 tenant must never receive expected_revenue_krw (must be null) - "
            "see 05_scoring_spec.md §2 and 00_product_spec.md §4.2"
        )


def base_volume(node_id: str, channel: str, benchmark_pop: float) -> float:
    """Expected monthly transaction count for a *benchmark-average* region,
    before any of the 8 factors adjust it away from that average.
    """
    try:
        from synthetic.demand_gen import CHANNEL_MIX, NODE_PARAMS

        txn_rate, _store_rate, _avg_value = NODE_PARAMS.get(node_id, (None, None, None))
        share = CHANNEL_MIX.get(node_id, {}).get(channel)
    except ImportError:
        txn_rate, share = None, None

    if txn_rate is None:
        txn_rate = _DEFAULT_TXN_RATE_PER_1000POP
    if share is None:
        share = 1.0
    return (benchmark_pop / 1000) * txn_rate * share


@dataclass
class PredictionResult:
    region_id: str
    taxonomy_node_id: str
    channel: str
    period: str
    data_tier: str
    factors: list[dict]
    total_log_multiplier: float
    total_multiplier: float
    expected_demand_units: float
    expected_revenue_krw: dict | None

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "taxonomy_node_id": self.taxonomy_node_id,
            "channel": self.channel,
            "period": self.period,
            "data_tier": self.data_tier,
            "factors": self.factors,
            "total_log_multiplier": self.total_log_multiplier,
            "total_multiplier": self.total_multiplier,
            "expected_demand_units": self.expected_demand_units,
            "expected_revenue_krw": self.expected_revenue_krw,
        }


def _months_for_horizon(period: str, horizon_months: int) -> list[int]:
    start_month = int(period.split("-")[1])
    return [((start_month - 1 + i) % 12) + 1 for i in range(horizon_months)]


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def _compute_benchmarks(
    region_ids: list[str],
    region_features: dict[str, dict],
    demand_by_region: dict[str, dict | None],
    target_ages: list[str] | None,
) -> dict:
    relevant_pops, age_shares, income_deciles, densities, channel_densities = [], [], [], [], []
    for rid in region_ids:
        feats = region_features.get(rid, {})
        pop_total = feats.get("pop_total")
        pop_age_dist = feats.get("pop_age_dist")
        income_decile = feats.get("income_decile")
        daytime_pop = feats.get("daytime_pop")

        share = factors.age_share(pop_age_dist, target_ages)
        if pop_total is not None:
            relevant_pop = pop_total * (share if share is not None else 1.0)
            if daytime_pop:
                relevant_pop = 0.7 * relevant_pop + 0.3 * daytime_pop * (share if share is not None else 1.0)
            relevant_pops.append(relevant_pop)
        if share is not None:
            age_shares.append(share)
        if income_decile is not None:
            income_deciles.append(income_decile)

        d = demand_by_region.get(rid)
        if d and d.get("store_count") is not None and pop_total:
            densities.append(d["store_count"] / (pop_total / 1000))
            channel_densities.append(d["store_count"] / (pop_total / 10_000))

    return {
        "relevant_pop": _mean(relevant_pops),
        "age_share": _mean(age_shares),
        "income_decile": _mean(income_deciles),
        "competition_density": _mean(densities),
        "channel_density": _mean(channel_densities),
        # spend_index and ecommerce_order_density benchmarks computed by caller
        # (they're per-node/channel, handled where that data is fetched)
    }


def predict_one(
    region_id: str,
    taxonomy_node_id: str,
    channel: str,
    period: str,
    as_of: str,
    data_tier: str,
    product_attributes: dict,
    price_tier: str,
    seasonality_profile: list[float] | None,
    horizon_months: int,
    region_features: dict[str, dict],
    demand_by_region: dict[str, dict | None],
    benchmarks: dict,
    ecommerce_benchmark: float | None,
    spend_index_benchmark: float | None,
    calibration_profile: tenant_layer.TenantCalibrationProfile | None = None,
) -> PredictionResult:
    channel_type = channel_type_of(channel)
    feats = region_features.get(region_id, {})
    demand = demand_by_region.get(region_id)
    target_ages = product_attributes.get("target_age")
    # 06_governance.md §1.4: calibration_profile is the ONLY tenant-derived
    # input anywhere in this function, and it only ever reaches f8 below -
    # region_features/demand_by_region/benchmarks (f1~f7's entire input
    # surface) come exclusively from the shared FeatureStore and were
    # computed before this function was even called. See tenant_layer.py's
    # module docstring and tests/test_tenant_isolation.py.
    calibration_multiplier = (
        tenant_layer.resolve_multiplier(calibration_profile, region_id) if calibration_profile is not None else None
    )

    f_list = [
        factors.addressable_demand(
            pop_total=feats.get("pop_total"),
            pop_age_dist=feats.get("pop_age_dist"),
            daytime_pop=feats.get("daytime_pop"),
            target_ages=target_ages,
            benchmark_value=benchmarks["relevant_pop"],
        ),
        factors.category_penetration(spend_index=demand.get("spend_index") if demand else None),
        factors.product_affinity(
            product_attributes=product_attributes,
            pop_age_dist=feats.get("pop_age_dist"),
            income_decile=feats.get("income_decile"),
            benchmark_age_share=benchmarks["age_share"],
            benchmark_income_decile=benchmarks["income_decile"],
        ),
        factors.price_acceptance(
            price_tier=price_tier,
            income_decile=feats.get("income_decile"),
            benchmark_income_decile=benchmarks["income_decile"],
        ),
        factors.competition(
            channel_type=channel_type,
            store_count=demand.get("store_count") if demand else None,
            pop_total=feats.get("pop_total"),
            benchmark_density=benchmarks["competition_density"],
        ),
        factors.channel_availability(
            channel_type=channel_type,
            store_count=demand.get("store_count") if demand else None,
            pop_total=feats.get("pop_total"),
            ecommerce_order_density=feats.get("ecommerce_order_density"),
            benchmark_value=ecommerce_benchmark if channel_type == "online" else benchmarks["channel_density"],
        ),
        factors.seasonality(seasonality_profile, _months_for_horizon(period, horizon_months)),
        factors.tenant_calibration(
            data_tier,
            calibration_multiplier,
            calibration_profile.n_rows_used if calibration_profile is not None else None,
        ),
    ]

    assert [f.key for f in f_list] == list(factors.FACTOR_KEYS)  # order/coverage guard

    total_log_multiplier = sum(f.log_contribution for f in f_list)
    total_multiplier = math.exp(total_log_multiplier)

    benchmark_pop = benchmarks["relevant_pop"] or 1.0
    volume = base_volume(taxonomy_node_id, channel, benchmark_pop)
    expected_demand_units = volume * total_multiplier

    # Step 2 does not implement revenue estimation (needs Step 3's backtest
    # residual distribution) - always null for now. The guard below is what
    # actually enforces the T0 rule; this isn't just today's default.
    expected_revenue_krw = None
    assert_t0_revenue_null(data_tier, expected_revenue_krw)

    return PredictionResult(
        region_id=region_id,
        taxonomy_node_id=taxonomy_node_id,
        channel=channel,
        period=period,
        data_tier=data_tier,
        factors=[f.to_dict() for f in f_list],
        total_log_multiplier=total_log_multiplier,
        total_multiplier=total_multiplier,
        expected_demand_units=expected_demand_units,
        expected_revenue_krw=expected_revenue_krw,
    )


def predict_batch(
    region_ids: list[str],
    taxonomy_node_id: str,
    channel: str,
    period: str,
    as_of: str,
    data_tier: str,
    store: FeatureStore,
    product_attributes: dict | None = None,
    price_tier: str = "mid",
    seasonality_profile: list[float] | None = None,
    horizon_months: int = 1,
    calibration_profile: tenant_layer.TenantCalibrationProfile | None = None,
) -> list[PredictionResult]:
    """Score `region_ids` for one (product, channel, period). Benchmarks are
    computed once across this exact region set - per 01_domain_model.json,
    opportunity_score is normalized "요청 결과 집합 내" (within the requested
    result set), and factor benchmarks follow the same scoping so a factor's
    "vs. peer average" evidence means the peers actually being compared here,
    not some fixed global constant baked into the code.

    `calibration_profile` (05_scoring_spec.md §2, T1/T2 only - build one with
    tenant_layer.fit_tenant_calibration()) is the only tenant-derived input
    here. It is passed straight to predict_one() and never touches
    `store.get_features`/`store.get_demand`/`_compute_benchmarks` above -
    those three calls are f1~f7's entire input surface and run identically
    whether or not a calibration_profile is given (06_governance.md §1.4).
    """
    product_attributes = product_attributes or {}
    target_ages = product_attributes.get("target_age")

    region_features = store.get_features(region_ids, REGION_FEATURE_KEYS, as_of)
    demand_by_region = store.get_demand(region_ids, taxonomy_node_id, channel, period)

    benchmarks = _compute_benchmarks(region_ids, region_features, demand_by_region, target_ages)

    ecommerce_feats = store.get_features(region_ids, ["ecommerce_order_density"], as_of)
    ecommerce_benchmark = _mean([v.get("ecommerce_order_density") for v in ecommerce_feats.values()])
    spend_index_benchmark = _mean(
        [d.get("spend_index") for d in demand_by_region.values() if d is not None]
    )

    results = []
    for region_id in region_ids:
        results.append(
            predict_one(
                region_id=region_id,
                taxonomy_node_id=taxonomy_node_id,
                channel=channel,
                period=period,
                as_of=as_of,
                data_tier=data_tier,
                product_attributes=product_attributes,
                price_tier=price_tier,
                seasonality_profile=seasonality_profile,
                horizon_months=horizon_months,
                region_features=region_features,
                demand_by_region=demand_by_region,
                benchmarks=benchmarks,
                ecommerce_benchmark=ecommerce_benchmark,
                spend_index_benchmark=spend_index_benchmark,
                calibration_profile=calibration_profile,
            )
        )
    return results
