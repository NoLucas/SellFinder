"""The 8-factor multiplicative model. 05_scoring_spec.md §1 - exactly these
8 keys, no more:

    addressable_demand, category_penetration, product_affinity,
    price_acceptance, competition, channel_availability, seasonality,
    tenant_calibration

Every factor function returns a FactorResult whose `log_contribution` is
math.log(multiplier) computed at full float precision - never round that
field. Only `display_effect` (the "+52%" string) is for humans. Rounding
log_contribution before returning it is exactly how the
Σ log_contribution == ln(total_multiplier) invariant (tested in
tests/test_factor_model.py) quietly breaks.

Pattern used throughout: each factor computes a `value` for the region
and compares it to a `benchmark` (the peer average across the region set
being scored in this run - see model.py). multiplier = value / benchmark.
This mirrors 04_api_contract.yaml's example_prediction_response.json
(every factor there also carries value + benchmark), and it's also *why*
factors.py never hardcodes a "national average" constant - the benchmark
is always computed from whatever region set the caller passed in.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

FACTOR_KEYS = (
    "addressable_demand",
    "category_penetration",
    "product_affinity",
    "price_acceptance",
    "competition",
    "channel_availability",
    "seasonality",
    "tenant_calibration",
)

_FACTOR_LABELS = {
    "addressable_demand": "수요 규모",
    "category_penetration": "카테고리 침투율",
    "product_affinity": "제품 적합도",
    "price_acceptance": "가격 수용도",
    "competition": "경쟁 강도",
    "channel_availability": "채널 접근성",
    "seasonality": "계절성",
    "tenant_calibration": "자사 실적 보정",
}

_MIN_MULTIPLIER = 1e-6  # floor so log() never sees 0 or a negative


@dataclass(frozen=True)
class FactorResult:
    key: str
    multiplier: float
    value: float | None
    benchmark: float | None
    evidence: str
    label: str = field(init=False)
    log_contribution: float = field(init=False)
    display_effect: str = field(init=False)

    def __post_init__(self) -> None:
        if self.key not in FACTOR_KEYS:
            raise ValueError(f"invalid factor key {self.key!r} - only {FACTOR_KEYS} are allowed")
        m = max(self.multiplier, _MIN_MULTIPLIER)
        object.__setattr__(self, "label", _FACTOR_LABELS[self.key])
        object.__setattr__(self, "log_contribution", math.log(m))
        pct = (m - 1.0) * 100
        object.__setattr__(self, "display_effect", f"{'+' if pct >= 0 else ''}{pct:.0f}%")

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "log_contribution": self.log_contribution,
            "display_effect": self.display_effect,
            "value": self.value,
            "benchmark": self.benchmark,
            "evidence": self.evidence,
        }


def _safe_ratio(value: float, benchmark: float) -> float:
    if benchmark is None or benchmark <= 0:
        return 1.0
    if value is None:
        return 1.0
    return value / benchmark


def age_share(pop_age_dist: dict | None, target_ages: list[str] | None) -> float | None:
    if pop_age_dist is None:
        return None
    if not target_ages:
        return 1.0  # no age targeting on the product -> whole population is the audience
    return sum(pop_age_dist.get(a, 0.0) for a in target_ages)


# ---------------------------------------------------------------------------
# f1 addressable_demand
# ---------------------------------------------------------------------------
def addressable_demand(
    pop_total: float | None,
    pop_age_dist: dict | None,
    daytime_pop: float | None,
    target_ages: list[str] | None,
    benchmark_value: float | None,
) -> FactorResult:
    if pop_total is None:
        return FactorResult(
            "addressable_demand", 1.0, None, benchmark_value,
            "인구 데이터 없음 - 중립(1.0)으로 처리",
        )
    share = age_share(pop_age_dist, target_ages)
    relevant_pop = pop_total * (share if share is not None else 1.0)
    # daytime_pop captures office-district demand (e.g. cvs/fnb near workplaces)
    # that resident-only population misses - blend it in lightly.
    if daytime_pop:
        relevant_pop = 0.7 * relevant_pop + 0.3 * daytime_pop * (share if share is not None else 1.0)
    mult = _safe_ratio(relevant_pop, benchmark_value)
    age_note = f"({'+'.join(target_ages)} 비중 {share:.1%})" if target_ages and share is not None else ""
    evidence = f"타깃 인구 규모 {relevant_pop:,.0f}명 {age_note} - 비교대상 지역 평균 {benchmark_value:,.0f}명 대비 {mult:.2f}배".strip()
    return FactorResult("addressable_demand", mult, relevant_pop, benchmark_value, evidence)


# ---------------------------------------------------------------------------
# f2 category_penetration
# ---------------------------------------------------------------------------
def category_penetration(spend_index: float | None) -> FactorResult:
    if spend_index is None:
        return FactorResult(
            "category_penetration", 1.0, None, 100.0,
            "해당 지역·채널의 소비 신호 데이터 없음(또는 suppressed) - 중립(1.0)으로 처리",
        )
    mult = spend_index / 100.0  # spend_index is already index-to-100=national-average by contract
    evidence = f"카테고리 소비지수 {spend_index:.0f} (전국 평균 100)"
    return FactorResult("category_penetration", mult, spend_index, 100.0, evidence)


# ---------------------------------------------------------------------------
# f3 product_affinity
# ---------------------------------------------------------------------------
def product_affinity(
    product_attributes: dict,
    pop_age_dist: dict | None,
    income_decile: float | None,
    benchmark_age_share: float | None,
    benchmark_income_decile: float | None,
) -> FactorResult:
    """Fit, not scale: local *share* of the target group vs peer-average
    share (unlike addressable_demand, which uses absolute headcount).
    A small region with a concentrated target audience should score well
    here even though it loses on addressable_demand.
    """
    sub_ratios: list[float] = []
    notes: list[str] = []

    target_ages = product_attributes.get("target_age")
    if target_ages and pop_age_dist is not None and benchmark_age_share:
        local_share = sum(pop_age_dist.get(a, 0.0) for a in target_ages)
        ratio = _safe_ratio(local_share, benchmark_age_share)
        sub_ratios.append(ratio)
        notes.append(f"{'+'.join(target_ages)} 인구 비중 {local_share:.1%} (비교지역 평균 {benchmark_age_share:.1%})")

    if product_attributes.get("premium_ingredient") and income_decile is not None and benchmark_income_decile:
        ratio = _safe_ratio(income_decile, benchmark_income_decile)
        sub_ratios.append(ratio)
        notes.append(f"소득 {income_decile:.0f}분위 (비교지역 평균 {benchmark_income_decile:.1f}분위) - 프리미엄 원료 제품")

    if not sub_ratios:
        return FactorResult(
            "product_affinity", 1.0, None, None,
            "제품 속성과 연결할 수 있는 지역 프로파일 신호 없음 - 중립(1.0)으로 처리",
        )
    # geometric mean of sub-ratios so no single attribute dominates
    mult = math.exp(sum(math.log(max(r, _MIN_MULTIPLIER)) for r in sub_ratios) / len(sub_ratios))
    evidence = "; ".join(notes)
    return FactorResult("product_affinity", mult, mult, 1.0, evidence)


# ---------------------------------------------------------------------------
# f4 price_acceptance
# ---------------------------------------------------------------------------
_PRICE_TIER_SENSITIVITY = {"value": 0.25, "mid": 0.55, "premium": 0.95, "luxury": 1.4}


def price_acceptance(
    price_tier: str,
    income_decile: float | None,
    benchmark_income_decile: float | None,
) -> FactorResult:
    if income_decile is None:
        return FactorResult(
            "price_acceptance", 1.0, None, benchmark_income_decile,
            "소득분위 데이터 없음 - 중립(1.0)으로 처리",
        )
    sensitivity = _PRICE_TIER_SENSITIVITY.get(price_tier, 0.55)
    benchmark = benchmark_income_decile if benchmark_income_decile else 5.5
    deviation = (income_decile - benchmark) / benchmark
    mult = max(0.3, 1 + deviation * sensitivity)
    evidence = f"소득 {income_decile:.0f}분위 (비교지역 평균 {benchmark:.1f}분위), 가격대 '{price_tier}'"
    return FactorResult("price_acceptance", mult, income_decile, benchmark, evidence)


# ---------------------------------------------------------------------------
# f5 competition - ALWAYS <= 1. Never uses foot_traffic/competitor_density
# for online channels (channel_rules in 02_taxonomy.json).
# ---------------------------------------------------------------------------
def competition(
    channel_type: str,
    store_count: int | None,
    pop_total: float | None,
    benchmark_density: float | None,
) -> FactorResult:
    if channel_type == "online":
        return FactorResult(
            "competition", 1.0, None, None,
            "온라인 채널은 경쟁 강도(competitor_density)를 사용하지 않음 (02_taxonomy.json channel_rules)",
        )
    if store_count is None or pop_total is None or not pop_total:
        return FactorResult(
            "competition", 1.0, None, benchmark_density,
            "점포수 데이터 없음(또는 suppressed) - 경쟁 감쇄 없음(1.0)으로 처리",
        )
    density = store_count / (pop_total / 1000)  # stores per 1,000 pop
    if not benchmark_density or benchmark_density <= 0:
        mult = 1.0
    else:
        # more stores than peer average => penalty (< 1); never a bonus (> 1)
        mult = min(1.0, benchmark_density / density) if density > 0 else 1.0
    evidence = f"인구 1,000명당 점포 {density:.2f}개 (비교지역 평균 {benchmark_density:.2f}개)" if benchmark_density else "경쟁 밀도 비교 기준 없음"
    return FactorResult("competition", mult, density, benchmark_density, evidence)


# ---------------------------------------------------------------------------
# f6 channel_availability
# ---------------------------------------------------------------------------
def channel_availability(
    channel_type: str,
    store_count: int | None,
    pop_total: float | None,
    ecommerce_order_density: float | None,
    benchmark_value: float | None,
) -> FactorResult:
    if channel_type == "online":
        if ecommerce_order_density is None:
            return FactorResult(
                "channel_availability", 1.0, None, benchmark_value,
                "이커머스 주문 밀도 데이터 없음 - 중립(1.0)으로 처리",
            )
        mult = _safe_ratio(ecommerce_order_density, benchmark_value)
        evidence = f"이커머스 주문 밀도 {ecommerce_order_density:.1f} (비교지역 평균 {benchmark_value:.1f})"
        return FactorResult("channel_availability", mult, ecommerce_order_density, benchmark_value, evidence)

    if store_count is None or pop_total is None or not pop_total:
        return FactorResult(
            "channel_availability", 1.0, None, benchmark_value,
            "채널 점포수 데이터 없음(또는 suppressed) - 중립(1.0)으로 처리",
        )
    density = store_count / (pop_total / 10_000)  # stores per 10,000 pop
    mult = _safe_ratio(density, benchmark_value)
    evidence = f"인구 1만명당 채널 점포 {density:.2f}개 (비교지역 평균 {benchmark_value:.2f}개)"
    return FactorResult("channel_availability", mult, density, benchmark_value, evidence)


# ---------------------------------------------------------------------------
# f7 seasonality
# ---------------------------------------------------------------------------
def seasonality(seasonality_profile: list[float] | None, months: list[int]) -> FactorResult:
    if not seasonality_profile:
        return FactorResult("seasonality", 1.0, None, 1.0, "계절성 프로필 없음 - 중립(1.0)으로 처리")
    values = [seasonality_profile[m - 1] for m in months]
    mult = sum(values) / len(values)
    month_range = f"{months[0]}~{months[-1]}월" if len(months) > 1 else f"{months[0]}월"
    evidence = f"예측 구간({month_range}) 계절 지수 평균 {mult:.2f}"
    return FactorResult("seasonality", mult, mult, 1.0, evidence)


# ---------------------------------------------------------------------------
# f8 tenant_calibration - T0 is HARD-FIXED at 1.0. See model.py's
# assert_t0_revenue_null for the paired output-side guard.
# ---------------------------------------------------------------------------
def tenant_calibration(data_tier: str) -> FactorResult:
    if data_tier == "T0":
        return FactorResult(
            "tenant_calibration", 1.0, None, None,
            "T0 테넌트 - 자사 실적 데이터 없음, 보정 없음(1.0 고정)",
        )
    # T1/T2 residual-model calibration is 05_scoring_spec.md §2's Step 5 scope
    # (needs tenant_sales + the Step 3 backtest residual distribution). Until
    # that lands, T1/T2 also get a neutral 1.0 rather than an invented number.
    return FactorResult(
        "tenant_calibration", 1.0, None, None,
        f"{data_tier} 테넌트 보정 모델 미구현 (5단계 예정) - 임시로 중립(1.0) 처리",
    )
