"""06_governance.md §1.4 - "공용 기저 모델(f1~f7)에는 어떤 테넌트의 tenant_sales도
들어가지 않는다." 지금까지 T1/T2 학습 코드 자체가 없어서 이 조항은 강제할 대상이
없는 구멍이었다. scoring/tenant_layer.py로 학습 코드를 채운 지금, 이 파일이 그
격리를 테스트로 고정한다.

강제하는 것 3가지:
  1. (구조) f1~f7의 입력 경로(FeatureStore.get_features/get_demand, model.py의
     _compute_benchmarks, predict_one/predict_batch)에 tenant_sales를 받을
     파라미터 자체가 없다.
  2. (동작) calibration_profile 유무와 무관하게 f1~f7의 log_contribution이
     바이트 단위로 동일하다 - f8만 달라진다.
  3. (동작) 서로 다른 두 테넌트의 calibration_profile로 같은 지역·기간을 스코어링해도
     f1~f7은 완전히 동일하고 f8만 달라진다 - 한 테넌트의 실적이 다른 테넌트가
     받는 예측(f1~f7)에 조금도 스며들지 않는다.

Run from /intelligence:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import inspect
import unittest

from scoring import factors, model, tenant_layer
from scoring.feature_store import FeatureStore, SyntheticFeatureStore
from synthetic import generate

_RTD_NODE = "TX-FOOD-BEV-COFFEE-RTD"
_PERIODS = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"]


class StructuralIsolationTestCase(unittest.TestCase):
    """f1~f7의 입력 표면(함수 시그니처)에 tenant_sales를 받을 방법 자체가 없는지
    확인한다. 이건 "안 그런다"는 주석이 아니라 코드가 물리적으로 그럴 수 없다는
    증명이다 - 나중에 누군가 f1~f7 함수에 tenant_sales 파라미터를 "편의상" 추가하면
    이 테스트가 즉시 깨진다."""

    _PUBLIC_PATH_CALLABLES = (
        FeatureStore.get_features,
        FeatureStore.get_demand,
        model._compute_benchmarks,
        factors.addressable_demand,
        factors.category_penetration,
        factors.product_affinity,
        factors.price_acceptance,
        factors.competition,
        factors.channel_availability,
        factors.seasonality,
    )

    def test_no_public_path_function_accepts_a_sales_shaped_parameter(self) -> None:
        offenders = []
        for fn in self._PUBLIC_PATH_CALLABLES:
            params = inspect.signature(fn).parameters
            for name in params:
                if "sales" in name.lower() or "tenant_id" in name.lower():
                    offenders.append((fn.__qualname__, name))
        self.assertEqual(
            offenders, [],
            f"f1~f7 경로 함수가 tenant_sales/tenant_id 를 받을 수 있는 파라미터를 가지고 있다: {offenders}",
        )

    def test_tenant_layer_never_accepts_a_tenant_id_or_a_store(self) -> None:
        # scoring/tenant_layer.py 자체가 조회 능력이 없다는 것도 시그니처로 고정한다 -
        # tenant_id를 받는 순간 "그걸로 뭔가를 조회"할 길이 열린다.
        for fn in (tenant_layer.fit_tenant_calibration, tenant_layer.resolve_multiplier):
            params = inspect.signature(fn).parameters
            for name in params:
                self.assertNotIn("tenant_id", name.lower())
                self.assertNotIn("store", name.lower())

    def test_predict_batch_calibration_profile_is_the_only_tenant_derived_parameter(self) -> None:
        params = list(inspect.signature(model.predict_batch).parameters)
        sales_like = [p for p in params if "sales" in p.lower()]
        self.assertEqual(sales_like, [], f"predict_batch가 tenant_sales 모양 파라미터를 직접 받는다: {sales_like}")
        self.assertIn("calibration_profile", params)


class BehavioralIsolationTestCase(unittest.TestCase):
    """실제로 predict_batch를 돌려서, calibration_profile이 f1~f7에 조금도
    영향을 주지 않는지 값으로 증명한다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = generate.generate_all(seed=42, start_period="2025-01", end_period="2026-06")
        cls.store = SyntheticFeatureStore.from_dataset(cls.dataset)
        cls.regions = cls.store.all_adm_dong_ids()[:20]

    def _baseline_by_region_period(self, periods: list[str]) -> dict[tuple[str, str], float]:
        out = {}
        for period in periods:
            as_of = f"{period}-01"
            results = model.predict_batch(
                region_ids=self.regions, taxonomy_node_id=_RTD_NODE, channel="cvs",
                period=period, as_of=as_of, data_tier="T2", store=self.store,
                seasonality_profile=[1.0] * 12,
            )
            for r in results:
                out[(r.region_id, period)] = r.expected_demand_units
        return out

    def _sales_rows(self, baseline_by_rp: dict, scale: float, seed: int) -> list[dict]:
        import random

        rng = random.Random(seed)
        rows = []
        for (region_id, period), baseline in baseline_by_rp.items():
            units = round(baseline * scale * rng.uniform(0.9, 1.1))
            rows.append(
                {"region_id": region_id, "period": period, "units_sold": units,
                 "distribution_points": 5, "is_outlier": False}
            )
        return rows

    def _f1_to_f7(self, factors_list: list[dict]) -> list[dict]:
        return [f for f in factors_list if f["key"] != "tenant_calibration"]

    def test_f1_to_f7_are_byte_identical_with_and_without_calibration(self) -> None:
        baseline_by_rp = self._baseline_by_region_period(_PERIODS)
        sales_rows = self._sales_rows(baseline_by_rp, scale=1.4, seed=1)
        profile = tenant_layer.fit_tenant_calibration(sales_rows, baseline_by_rp, "T2")
        self.assertIsNotNone(profile)

        as_of = "2026-01-01"
        uncalibrated = model.predict_batch(
            region_ids=self.regions, taxonomy_node_id=_RTD_NODE, channel="cvs",
            period="2026-01", as_of=as_of, data_tier="T2", store=self.store,
            seasonality_profile=[1.0] * 12,
        )
        calibrated = model.predict_batch(
            region_ids=self.regions, taxonomy_node_id=_RTD_NODE, channel="cvs",
            period="2026-01", as_of=as_of, data_tier="T2", store=self.store,
            seasonality_profile=[1.0] * 12, calibration_profile=profile,
        )
        self.assertEqual(len(uncalibrated), len(calibrated))
        for u, c in zip(uncalibrated, calibrated):
            self.assertEqual(
                self._f1_to_f7(u.factors), self._f1_to_f7(c.factors),
                f"{u.region_id}: calibration_profile을 준 것만으로 f1~f7이 달라졌다 - 격리 위반",
            )
            tc_u = next(f for f in u.factors if f["key"] == "tenant_calibration")
            tc_c = next(f for f in c.factors if f["key"] == "tenant_calibration")
            self.assertNotEqual(tc_u["log_contribution"], tc_c["log_contribution"], "보정을 줬는데 f8이 그대로다")

    def test_two_different_tenants_calibration_never_leaks_into_each_others_f1_to_f7(self) -> None:
        """가장 날카로운 검사: 완전히 다른 두 테넌트(실적 규모가 다른)의 profile로
        같은 지역·기간을 스코어링해도 f1~f7은 완전히 같아야 한다."""
        baseline_by_rp = self._baseline_by_region_period(_PERIODS)
        tenant_a_rows = self._sales_rows(baseline_by_rp, scale=0.6, seed=11)   # 저조한 테넌트
        tenant_b_rows = self._sales_rows(baseline_by_rp, scale=2.5, seed=22)   # 매우 잘 파는 테넌트
        profile_a = tenant_layer.fit_tenant_calibration(tenant_a_rows, baseline_by_rp, "T2")
        profile_b = tenant_layer.fit_tenant_calibration(tenant_b_rows, baseline_by_rp, "T2")
        self.assertIsNotNone(profile_a)
        self.assertIsNotNone(profile_b)
        self.assertNotAlmostEqual(profile_a.global_scale, profile_b.global_scale, places=2)

        as_of = "2026-01-01"
        results_a = model.predict_batch(
            region_ids=self.regions, taxonomy_node_id=_RTD_NODE, channel="cvs",
            period="2026-01", as_of=as_of, data_tier="T2", store=self.store,
            seasonality_profile=[1.0] * 12, calibration_profile=profile_a,
        )
        results_b = model.predict_batch(
            region_ids=self.regions, taxonomy_node_id=_RTD_NODE, channel="cvs",
            period="2026-01", as_of=as_of, data_tier="T2", store=self.store,
            seasonality_profile=[1.0] * 12, calibration_profile=profile_b,
        )
        diffs = 0
        for ra, rb in zip(results_a, results_b):
            self.assertEqual(
                self._f1_to_f7(ra.factors), self._f1_to_f7(rb.factors),
                f"{ra.region_id}: 테넌트 A의 f1~f7이 테넌트 B와 다르다 - 테넌트별로 공용 모델이 갈라졌다는 뜻",
            )
            tc_a = next(f for f in ra.factors if f["key"] == "tenant_calibration")
            tc_b = next(f for f in rb.factors if f["key"] == "tenant_calibration")
            if tc_a["value"] != tc_b["value"]:
                diffs += 1
        self.assertGreater(diffs, 0, "두 테넌트의 f8이 전 지역에서 동일하다 - calibration이 실제로 적용되지 않았을 수 있다")

    def test_insufficient_sales_data_falls_back_to_neutral_not_fabrication(self) -> None:
        baseline_by_rp = self._baseline_by_region_period(_PERIODS[:1])
        tiny_rows = self._sales_rows(baseline_by_rp, scale=1.5, seed=1)[:2]  # 임계값(3) 미만
        profile = tenant_layer.fit_tenant_calibration(tiny_rows, baseline_by_rp, "T2")
        self.assertIsNone(profile, "표본이 2건뿐인데 profile을 만들어냈다 - 지어낸 것")

        results = model.predict_batch(
            region_ids=self.regions[:5], taxonomy_node_id=_RTD_NODE, channel="cvs",
            period="2026-01", as_of="2026-01-01", data_tier="T2", store=self.store,
            seasonality_profile=[1.0] * 12, calibration_profile=profile,
        )
        for r in results:
            tc = next(f for f in r.factors if f["key"] == "tenant_calibration")
            self.assertIsNone(tc["value"])
            self.assertEqual(tc["log_contribution"], 0.0)

    def test_outlier_rows_are_excluded_from_the_fit(self) -> None:
        baseline_by_rp = self._baseline_by_region_period(_PERIODS)
        clean_rows = self._sales_rows(baseline_by_rp, scale=1.2, seed=5)
        profile_clean = tenant_layer.fit_tenant_calibration(clean_rows, baseline_by_rp, "T2")

        contaminated_rows = list(clean_rows) + [
            {"region_id": self.regions[0], "period": "2025-06", "units_sold": 999_999_999,
             "distribution_points": 5, "is_outlier": True},
        ]
        profile_contaminated = tenant_layer.fit_tenant_calibration(contaminated_rows, baseline_by_rp, "T2")
        self.assertAlmostEqual(profile_clean.global_scale, profile_contaminated.global_scale, places=9)
        self.assertEqual(profile_contaminated.n_rows_excluded_outlier, 1)

    def test_region_residual_takes_priority_over_region_group_and_global(self) -> None:
        baseline_by_rp = self._baseline_by_region_period(_PERIODS)
        rows = self._sales_rows(baseline_by_rp, scale=1.0, seed=3)
        # 한 지역만 의도적으로 훨씬 높게 - region-level residual이 있어야 잡힌다
        target_region = self.regions[0]
        boosted_rows = [
            dict(row, units_sold=round(row["units_sold"] * 3)) if row["region_id"] == target_region else row
            for row in rows
        ]
        profile = tenant_layer.fit_tenant_calibration(boosted_rows, baseline_by_rp, "T2")
        self.assertIn(target_region, profile.region_scale)
        mult_target = tenant_layer.resolve_multiplier(profile, target_region)
        other_region = next(r for r in self.regions if r != target_region)
        mult_other = tenant_layer.resolve_multiplier(profile, other_region)
        self.assertGreater(mult_target, mult_other * 1.5, "3배 부스트한 지역의 보정 배수가 다른 지역과 별 차이가 없다")

    def test_t1_never_produces_a_region_level_residual(self) -> None:
        # 05_scoring_spec.md §2: T1은 "전역 스케일 + 지역군별 보정"까지만 - 지역 단위
        # 잔차(T2 전용)를 T1이 만들면 계약이 정의한 tier 간 정밀도 구분이 무너진다.
        baseline_by_rp = self._baseline_by_region_period(_PERIODS)
        rows = self._sales_rows(baseline_by_rp, scale=1.2, seed=7)
        profile = tenant_layer.fit_tenant_calibration(rows, baseline_by_rp, "T1")
        self.assertEqual(profile.region_scale, {}, "T1인데 region-level residual이 만들어졌다")


if __name__ == "__main__":
    unittest.main()
