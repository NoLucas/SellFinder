"""Step 2 invariant tests, per 05_scoring_spec.md §8 (the subset this step
owns - as_of leakage detection is Step 3's backtest harness, not here).

Run from /intelligence:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import math
import unittest

from scoring import factors, model
from scoring.feature_store import SyntheticFeatureStore
from synthetic import generate

_RTD_NODE = "TX-FOOD-BEV-COFFEE-RTD"
_RTD_ATTRS = {"target_age": ["20s", "30s"], "sugar_free": True}
_RTD_SEASONALITY = [0.92, 0.90, 0.98, 1.02, 1.08, 1.14, 1.18, 1.16, 1.04, 0.96, 0.92, 0.90]


class FactorModelTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = generate.generate_all(seed=42, start_period="2025-01", end_period="2026-06")
        cls.store = SyntheticFeatureStore.from_dataset(cls.dataset)
        cls.all_regions = cls.store.all_adm_dong_ids()

    def _predict(self, **overrides) -> list[model.PredictionResult]:
        kwargs = dict(
            region_ids=self.all_regions,
            taxonomy_node_id=_RTD_NODE,
            channel="cvs",
            period="2025-06",
            as_of="2025-06-01",
            data_tier="T0",
            store=self.store,
            product_attributes=_RTD_ATTRS,
            price_tier="mid",
            seasonality_profile=_RTD_SEASONALITY,
            horizon_months=1,
        )
        kwargs.update(overrides)
        return model.predict_batch(**kwargs)

    # ------------------------------------------------------------------
    # the one invariant that must never break (05_scoring_spec.md §1, D-04)
    #
    # VF-001: the sum-vs-total assertion right below is a TAUTOLOGY on its
    # own - model.py computes total_multiplier as exp(sum(log_contribution)),
    # so the equality holds even when the decomposition shown to the user is
    # a lie. It stays (it still guards the wiring: total_log_multiplier must
    # equal what was actually summed), but the teeth are in the three tests
    # after it - each compares log_contribution against a witness that is NOT
    # derived from the sum: the factor's own multiplier, its display_effect
    # string, and its published value/benchmark ratio. Mutation harness that
    # decides whether these have teeth: verification/fixtures/vf_51_mutation.py
    # (M1 and M2 must both produce failures>0).
    # ------------------------------------------------------------------
    def test_log_contribution_sum_matches_log_of_total_multiplier(self) -> None:
        results = self._predict()
        self.assertGreater(len(results), 0)
        for r in results:
            summed = sum(f["log_contribution"] for f in r.factors)
            self.assertAlmostEqual(summed, math.log(r.total_multiplier), delta=1e-6)
            self.assertAlmostEqual(summed, r.total_log_multiplier, delta=1e-9)

    # factors whose contract definition is literally multiplier = value /
    # benchmark. competition inverts+clamps the ratio and tenant_calibration
    # carries no value/benchmark pair - those are covered by the other two
    # independent-witness tests below instead.
    _RATIO_FACTORS = frozenset(
        {
            "addressable_demand",
            "category_penetration",
            "product_affinity",
            "channel_availability",
            "seasonality",
        }
    )

    def _factor_battery(self) -> list[factors.FactorResult]:
        """One direct call per factor key, with inputs chosen so each comes
        out non-neutral. A factor sitting at exactly 1.0 can't reveal a
        distortion, so the non-neutral count below fails if the battery
        ever drifts back to all-neutral."""
        age_dist = {"20s": 0.21, "30s": 0.19, "40s": 0.20, "50s": 0.18}
        return [
            factors.addressable_demand(
                pop_total=52_000,
                pop_age_dist=age_dist,
                daytime_pop=31_000,
                target_ages=["20s", "30s"],
                benchmark_value=12_000.0,
            ),
            factors.category_penetration(spend_index=137.0),
            factors.product_affinity(
                product_attributes={"target_age": ["20s", "30s"], "premium_ingredient": True},
                pop_age_dist=age_dist,
                income_decile=8.0,
                benchmark_age_share=0.32,
                benchmark_income_decile=5.5,
            ),
            factors.price_acceptance(price_tier="premium", income_decile=8.0, benchmark_income_decile=5.5),
            factors.competition(
                channel_type="offline", store_count=44, pop_total=52_000, benchmark_density=0.61
            ),
            factors.channel_availability(
                channel_type="offline",
                store_count=44,
                pop_total=52_000,
                ecommerce_order_density=None,
                benchmark_value=6.2,
            ),
            factors.seasonality(_RTD_SEASONALITY, [6, 7, 8]),
            factors.tenant_calibration("T0"),
        ]

    def test_log_contribution_matches_each_factors_own_multiplier(self) -> None:
        """External witness #1: the multiplier the factor itself computed.

        multiplier is a constructor input - it is never recomputed from
        log_contribution and the sum-vs-total test above never touches it.
        If exp(log_contribution) drifts from it, the exported decomposition
        is not the arithmetic that actually produced the score.
        """
        battery = self._factor_battery()
        self.assertEqual([f.key for f in battery], list(factors.FACTOR_KEYS))

        non_neutral = 0
        for f in battery:
            self.assertAlmostEqual(
                math.exp(f.log_contribution) / f.multiplier,
                1.0,
                delta=1e-9,
                msg=(
                    f"{f.key}: exports exp(log_contribution)={math.exp(f.log_contribution):.9f} "
                    f"but the factor measured multiplier={f.multiplier:.9f}"
                ),
            )
            if abs(f.log_contribution) > 1e-3:
                non_neutral += 1
        self.assertGreaterEqual(
            non_neutral,
            6,
            "factor battery came out neutral - it can no longer detect a distorted factor",
        )

    def test_display_effect_agrees_with_exported_log_contribution(self) -> None:
        """External witness #2: the string the user is actually shown.

        display_effect is rendered from the multiplier at construction time,
        so within one payload it independently witnesses the log_contribution
        shipped beside it. A drifted decomposition shows the user one number
        while the API returns another. Tolerance is the display rounding
        quantum itself (display_effect rounds to a whole percent) plus float
        slack, not a judgement call.
        """
        results = self._predict(price_tier="premium")
        self.assertGreater(len(results), 0)
        checked = 0
        for r in results:
            for f in r.factors:
                shown_ratio = float(f["display_effect"].rstrip("%")) / 100.0 + 1.0
                self.assertAlmostEqual(
                    math.exp(f["log_contribution"]),
                    shown_ratio,
                    delta=0.005 + 1e-9,
                    msg=(
                        f"{r.region_id}/{f['key']}: shows {f['display_effect']} to the user but exports "
                        f"exp(log_contribution)={math.exp(f['log_contribution']):.6f}"
                    ),
                )
                checked += 1
        self.assertGreater(checked, 0)

    def test_value_over_benchmark_reconstructs_log_contribution(self) -> None:
        """External witness #3: the evidence numbers carried in the same dict.

        For the ratio-defined factors the contract says multiplier = value /
        benchmark, and 05_scoring_spec.md §6 already requires both to be
        published in the evidence. Recomputing the ratio from those two
        published numbers is independent of the sum, so it catches a
        decomposition that was rounded or scaled after construction.
        """
        results = self._predict(price_tier="premium")
        checked = 0
        non_neutral = 0
        for r in results:
            for f in r.factors:
                if f["key"] not in self._RATIO_FACTORS:
                    continue
                value, benchmark = f["value"], f["benchmark"]
                if value is None or not benchmark:
                    continue  # neutral fallback - nothing published to reconstruct from
                ratio = value / benchmark
                self.assertAlmostEqual(
                    math.exp(f["log_contribution"]) / ratio,
                    1.0,
                    delta=1e-9,
                    msg=(
                        f"{r.region_id}/{f['key']}: evidence says {value} / {benchmark} = {ratio:.9f} "
                        f"but exports exp(log_contribution)={math.exp(f['log_contribution']):.9f}"
                    ),
                )
                checked += 1
                if abs(f["log_contribution"]) > 1e-3:
                    non_neutral += 1
        self.assertGreater(checked, 0)
        self.assertGreaterEqual(
            non_neutral,
            len(results),
            "every reconstructable ratio factor came out neutral - this test would pass on a broken model",
        )

    def test_exactly_eight_factor_keys_in_contract_order(self) -> None:
        results = self._predict()
        for r in results:
            keys = [f["key"] for f in r.factors]
            self.assertEqual(keys, list(factors.FACTOR_KEYS))

    # ------------------------------------------------------------------
    # competition <= 1
    # ------------------------------------------------------------------
    def test_competition_never_exceeds_one(self) -> None:
        for channel in ("cvs", "hypermarket", "online_marketplace"):
            for r in self._predict(channel=channel):
                comp = next(f for f in r.factors if f["key"] == "competition")
                self.assertLessEqual(comp["log_contribution"], 1e-9, f"{channel}/{r.region_id}: {comp}")

    # ------------------------------------------------------------------
    # online channels never see foot_traffic / competitor_density
    # ------------------------------------------------------------------
    def test_online_channel_excludes_foot_traffic_and_competitor_density(self) -> None:
        online_results = self._predict(channel="online_marketplace")
        for r in online_results:
            comp = next(f for f in r.factors if f["key"] == "competition")
            avail = next(f for f in r.factors if f["key"] == "channel_availability")
            # competition must be neutral and explicitly not store/foot-traffic-based online
            self.assertAlmostEqual(math.exp(comp["log_contribution"]), 1.0, places=9)
            self.assertIsNone(comp["value"])
            self.assertIn("channel_rules", comp["evidence"])
            # channel_availability for online must be driven by ecommerce density, not store_count
            self.assertIn("이커머스", avail["evidence"])
            self.assertNotIn("점포", avail["evidence"])

    def test_offline_channel_competition_uses_store_density_not_ecommerce(self) -> None:
        offline_results = self._predict(channel="cvs")
        for r in offline_results:
            avail = next(f for f in r.factors if f["key"] == "channel_availability")
            self.assertNotIn("이커머스", avail["evidence"])

    # ------------------------------------------------------------------
    # T0 => expected_revenue_krw is null (guard-enforced, not incidental)
    # ------------------------------------------------------------------
    def test_t0_expected_revenue_is_null(self) -> None:
        for r in self._predict(data_tier="T0"):
            self.assertIsNone(r.expected_revenue_krw)

    def test_t0_guard_actually_raises_on_misuse(self) -> None:
        model.assert_t0_revenue_null("T1", {"p50": 100})  # must not raise
        with self.assertRaises(model.ExpectedRevenueOnT0Error):
            model.assert_t0_revenue_null("T0", {"p50": 100})

    def test_t0_tenant_calibration_is_hard_fixed_at_one(self) -> None:
        for r in self._predict(data_tier="T0"):
            tc = next(f for f in r.factors if f["key"] == "tenant_calibration")
            self.assertEqual(tc["log_contribution"], 0.0)

    # ------------------------------------------------------------------
    # reproducibility
    # ------------------------------------------------------------------
    def test_identical_inputs_produce_identical_output(self) -> None:
        a = self._predict()
        b = self._predict()
        self.assertEqual([r.to_dict() for r in a], [r.to_dict() for r in b])

    def test_deep_copied_inputs_do_not_change_output(self) -> None:
        # guards against a factor function accidentally mutating a shared
        # dict/list it was handed (product_attributes, seasonality_profile)
        attrs = copy.deepcopy(_RTD_ATTRS)
        a = self._predict(product_attributes=attrs)
        self.assertEqual(attrs, _RTD_ATTRS)
        b = self._predict(product_attributes=copy.deepcopy(_RTD_ATTRS))
        self.assertEqual([r.to_dict() for r in a], [r.to_dict() for r in b])

    # ------------------------------------------------------------------
    # small-sample domination check
    # ------------------------------------------------------------------
    def test_small_population_adm_dong_do_not_dominate_top_ranks(self) -> None:
        results = self._predict()
        ranked = sorted(results, key=lambda r: r.total_multiplier, reverse=True)
        top_n = 10
        top_region_ids = {r.region_id for r in ranked[:top_n]}

        region_features = self.store.get_features(self.all_regions, ["pop_total"], "2025-06-01")
        small_pop_ids = {
            rid for rid, feats in region_features.items() if feats["pop_total"] is not None and feats["pop_total"] < 30_000
        }
        overall_share = len(small_pop_ids) / len(self.all_regions)
        top_small_count = len(top_region_ids & small_pop_ids)
        top_share = top_small_count / top_n

        self.assertLessEqual(
            top_share,
            overall_share * 2.0 + 0.05,
            f"pop<30k regions are {top_share:.0%} of the top {top_n} vs {overall_share:.0%} of all regions - "
            "addressable_demand isn't dampening small regions enough",
        )

    # ------------------------------------------------------------------
    # Step 1's planted coefficient must be recoverable through the model
    # ------------------------------------------------------------------
    def test_planted_rtd_relationship_recoverable_via_category_penetration(self) -> None:
        rel = next(
            r for r in self.dataset["ground_truth"]["planted_relationships"] if r["id"] == "rtd_coffee_young_affluent"
        )
        qualifying = set(rel["qualifying_region_ids"])
        results = self._predict()

        def cat_pen(r):
            return next(f for f in r.factors if f["key"] == "category_penetration")["log_contribution"]

        qual_vals = [cat_pen(r) for r in results if r.region_id in qualifying]
        other_vals = [cat_pen(r) for r in results if r.region_id not in qualifying]
        self.assertTrue(qual_vals and other_vals)
        qual_mean = sum(qual_vals) / len(qual_vals)
        other_mean = sum(other_vals) / len(other_vals)
        # in log space, ln(1.6) ~= 0.47 should separate the two groups
        self.assertGreater(qual_mean - other_mean, math.log(rel["multiplier"]) * 0.5)


if __name__ == "__main__":
    unittest.main()
