"""Tenant-isolated calibration layer - f8 (tenant_calibration), T1/T2.

06_governance.md 1.4: "공용 기저 모델(f1~f7)에는 어떤 테넌트의 tenant_sales도
들어가지 않는다." This module is the ONE place in scoring/ allowed to read
tenant_sales-shaped rows. Nowhere else does - factors.py's f1~f7 functions
and model.py's _compute_benchmarks()/get_features()/get_demand() calls have
no tenant_sales parameter at all. That absence is the actual enforcement
mechanism, not a comment (see tests/test_tenant_isolation.py's structural
signature check).

This module never queries anything and never accepts a tenant_id. It has
no store, no database handle, no way to fetch "all sales for tenant X" -
it only ever sees the exact rows the caller (C's backend, which already
derives tenant_id from the auth token alone per ADR-003/D-17) hands it.
If a caller ever merged two tenants' rows into one call here, this module
could not detect that - the isolation guarantee is architectural: predict_one/
predict_batch in model.py never fetch tenant_sales themselves, they only
accept an already-fitted, opaque TenantCalibrationProfile.

Two phases, matching how a real calibration would be versioned
(prediction_run.model_version in 01_domain_model.json):
  1. fit_tenant_calibration() - called once per tenant (offline/periodically,
     not on every prediction request). Reads sales rows the caller already
     scoped to a single tenant, produces a small aggregated
     TenantCalibrationProfile.
  2. resolve_multiplier() applies an already-fitted profile per region at
     prediction time via factors.tenant_calibration() - the hot prediction
     path never sees a raw tenant_sales row, only the profile's aggregated
     numbers.

05_scoring_spec.md 2:
  T1 = "전역 스케일 + 지역군별 보정" (global scale + region-group correction)
  T2 = "테넌트 전용 잔차 모델" (tenant-exclusive residual model, region-level)
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

# 05_scoring_spec.md 2 doesn't give an explicit minimum sample size. Below
# these thresholds a "fit" is noise dressed up as a number - refuse rather
# than fabricate (same principle as DISPATCH-2.md 9: "모르면 null이나
# 질문이지, 추측이 아니다").
_MIN_ROWS_FOR_GLOBAL_SCALE = 3
_MIN_ROWS_FOR_REGION_RESIDUAL = 3


@dataclass(frozen=True)
class TenantCalibrationProfile:
    data_tier: str
    global_scale: float
    region_group_scale: dict = field(default_factory=dict)  # T1: sido-level correction, relative to global_scale
    region_scale: dict = field(default_factory=dict)        # T2: per-region_id residual, relative to global_scale
    n_rows_used: int = 0
    n_rows_excluded_outlier: int = 0
    n_rows_excluded_missing_baseline: int = 0


def _region_group(region_id: str) -> str:
    """지역군 = 시도 단위(region_id 앞 2자리). 05_scoring_spec.md 2의
    "지역군별 보정"을 adm_dong 개별보다 한 단계 굵게 구체화한 것."""
    return region_id[:2]


def _residual_ratios(
    sales_rows: list[dict], baseline_by_region_period: dict[tuple[str, str], float]
) -> tuple[list[tuple[str, float]], int, int]:
    """(region_id, ratio) 쌍의 리스트를 만든다. ratio = 실판매(units_sold) /
    공용 모델(f1~f7, calibration 없이)이 그 (지역,기간)에 대해 이미 예측한 값.
    저장되는 건 원시 판매 숫자가 아니라 "공용 모델 대비 보정 배수"뿐이다."""
    pairs: list[tuple[str, float]] = []
    excluded_outlier = 0
    excluded_missing = 0
    for row in sales_rows:
        if row.get("is_outlier"):
            excluded_outlier += 1  # 01_domain_model.json tenant_sales.is_outlier: "학습에서 제외"
            continue
        units = row.get("units_sold")
        baseline = baseline_by_region_period.get((row["region_id"], row["period"]))
        if units is None or baseline is None or baseline <= 0:
            excluded_missing += 1
            continue
        pairs.append((row["region_id"], units / baseline))
    return pairs, excluded_outlier, excluded_missing


def fit_tenant_calibration(
    sales_rows: list[dict],
    baseline_by_region_period: dict[tuple[str, str], float],
    data_tier: str,
) -> TenantCalibrationProfile | None:
    """`sales_rows`와 `baseline_by_region_period`는 호출자가 이미 정확히
    한 테넌트로 스코핑해 넘겨야 한다 - 이 함수는 tenant_id를 받지 않고,
    더 가져올 방법도 없다.

    데이터가 부족하면(§ 아래 임계값 미만) None을 반환한다 - 호출자는 None을
    받으면 중립(1.0)으로 처리해야 한다(factors.tenant_calibration이 이미
    그렇게 한다). 몇 개 안 되는 잡음 섞인 값으로 배수를 지어내지 않는다.
    """
    if data_tier not in ("T1", "T2"):
        return None

    pairs, n_outlier, n_missing = _residual_ratios(sales_rows, baseline_by_region_period)
    if len(pairs) < _MIN_ROWS_FOR_GLOBAL_SCALE:
        return None

    ratios = [r for _, r in pairs]
    global_scale = statistics.median(ratios)

    region_group_scale: dict[str, float] = {}
    by_group: dict[str, list[float]] = {}
    for region_id, ratio in pairs:
        by_group.setdefault(_region_group(region_id), []).append(ratio)
    for group, group_ratios in by_group.items():
        if len(group_ratios) >= _MIN_ROWS_FOR_GLOBAL_SCALE:
            region_group_scale[group] = statistics.median(group_ratios) / global_scale

    region_scale: dict[str, float] = {}
    if data_tier == "T2":
        by_region: dict[str, list[float]] = {}
        for region_id, ratio in pairs:
            by_region.setdefault(region_id, []).append(ratio)
        for region_id, region_ratios in by_region.items():
            if len(region_ratios) >= _MIN_ROWS_FOR_REGION_RESIDUAL:
                region_scale[region_id] = statistics.median(region_ratios) / global_scale

    return TenantCalibrationProfile(
        data_tier=data_tier,
        global_scale=global_scale,
        region_group_scale=region_group_scale,
        region_scale=region_scale,
        n_rows_used=len(pairs),
        n_rows_excluded_outlier=n_outlier,
        n_rows_excluded_missing_baseline=n_missing,
    )


def resolve_multiplier(profile: TenantCalibrationProfile | None, region_id: str) -> float | None:
    """profile이 None이면 None을 반환한다 - factors.tenant_calibration이
    그걸 중립(1.0)으로 처리한다. 우선순위: region 단위 잔차(T2, 데이터가
    충분한 지역만) > 지역군 보정(T1/T2 공통 폴백) > 전역 스케일 단독."""
    if profile is None:
        return None
    mult = profile.global_scale
    if region_id in profile.region_scale:
        mult *= profile.region_scale[region_id]
    elif _region_group(region_id) in profile.region_group_scale:
        mult *= profile.region_group_scale[_region_group(region_id)]
    return mult
