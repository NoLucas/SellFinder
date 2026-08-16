"""Step 3 backtest harness tests. 05_scoring_spec.md §5.

Run from /intelligence:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from backtest import harness
from scoring.feature_store import SyntheticFeatureStore
from synthetic import generate, ground_truth

_RTD_NODE = "TX-FOOD-BEV-COFFEE-RTD"
_RTD_ATTRS = {"target_age": ["20s", "30s"], "sugar_free": True}
_RTD_SEASONALITY = [0.92, 0.90, 0.98, 1.02, 1.08, 1.14, 1.18, 1.16, 1.04, 0.96, 0.92, 0.90]
_TRAIN_CUTOFF = ground_truth.LEAKAGE_TRAP_CUTOFF[:7]  # "2026-01"


class SplitTestCase(unittest.TestCase):
    def test_time_split_is_chronological_not_random(self) -> None:
        periods = ["2025-01", "2025-06", "2025-12", "2026-01", "2026-03", "2026-06"]
        train, validate = harness.time_split(periods, "2026-01")
        self.assertEqual(train, ["2025-01", "2025-06", "2025-12"])
        self.assertEqual(validate, ["2026-01", "2026-03", "2026-06"])

    def test_time_split_rejects_a_cutoff_that_empties_a_side(self) -> None:
        periods = ["2025-01", "2025-06"]
        with self.assertRaises(ValueError):
            harness.time_split(periods, "2020-01")  # everything lands in validate
        with self.assertRaises(ValueError):
            harness.time_split(periods, "2030-01")  # everything lands in train

    def test_region_holdout_is_a_true_partition(self) -> None:
        region_ids = [f"R{i:03d}" for i in range(100)]
        train, holdout = harness.region_holdout_split(region_ids, seed=42, holdout_frac=0.2)
        self.assertEqual(len(holdout), 20)
        self.assertEqual(len(train), 80)
        self.assertEqual(set(train) | set(holdout), set(region_ids))
        self.assertEqual(set(train) & set(holdout), set())

    def test_region_holdout_is_reproducible_for_a_fixed_seed(self) -> None:
        region_ids = [f"R{i:03d}" for i in range(50)]
        a = harness.region_holdout_split(region_ids, seed=7)
        b = harness.region_holdout_split(region_ids, seed=7)
        self.assertEqual(a, b)

    def test_region_holdout_ignores_input_order(self) -> None:
        region_ids = [f"R{i:03d}" for i in range(50)]
        shuffled = list(reversed(region_ids))
        a = harness.region_holdout_split(region_ids, seed=7)
        b = harness.region_holdout_split(shuffled, seed=7)
        self.assertEqual(a, b)


class MetricTestCase(unittest.TestCase):
    def test_spearman_rho_is_one_for_a_monotonic_relationship(self) -> None:
        predicted = [1, 2, 3, 4, 5]
        actual = [10, 20, 30, 40, 50]
        self.assertAlmostEqual(harness.spearman_rho(predicted, actual), 1.0, places=9)

    def test_spearman_rho_is_minus_one_for_a_reversed_relationship(self) -> None:
        predicted = [1, 2, 3, 4, 5]
        actual = [50, 40, 30, 20, 10]
        self.assertAlmostEqual(harness.spearman_rho(predicted, actual), -1.0, places=9)

    def test_spearman_rho_is_near_zero_for_unrelated_ranks(self) -> None:
        predicted = [1, 2, 3, 4, 5, 6]
        actual = [3, 6, 1, 5, 2, 4]  # deliberately scrambled, not correlated
        self.assertLess(abs(harness.spearman_rho(predicted, actual)), 0.6)

    def test_spearman_rho_handles_ties_via_average_rank(self) -> None:
        # a known worked example: ties get the average of the ranks they span
        predicted = [1, 2, 2, 4]
        actual = [1, 2, 2, 4]
        self.assertAlmostEqual(harness.spearman_rho(predicted, actual), 1.0, places=9)

    def test_top_decile_lift_is_near_one_when_predicted_is_uncorrelated_with_actual(self) -> None:
        import random

        rng = random.Random(11)
        n = 200
        predicted = [rng.random() for _ in range(n)]
        actual = [rng.random() * 100 for _ in range(n)]  # independently drawn - no relationship to predicted
        lift = harness.top_decile_lift(predicted, actual)
        # with enough points, an uncorrelated "top decile" samples close to the overall mean
        self.assertLess(abs(lift - 1.0), 0.4, f"lift={lift:.3f} - unexpectedly far from 1.0 for unrelated ranks")

    def test_top_decile_lift_exceeds_one_when_predicted_tracks_actual(self) -> None:
        predicted = [float(i) for i in range(20)]
        actual = [float(i) for i in range(20)]
        self.assertGreater(harness.top_decile_lift(predicted, actual), 1.0)


class LeakageGuardTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = generate.generate_all(seed=42, start_period="2025-01", end_period="2026-06")
        cls.store = SyntheticFeatureStore.from_dataset(cls.dataset)
        cls.region_ids = cls.store.all_adm_dong_ids()
        cls.train_periods, cls.val_periods = harness.time_split(
            cls.dataset["manifest"]["periods"], _TRAIN_CUTOFF
        )

    def test_trap_feature_actually_exists_in_the_dataset(self) -> None:
        # sanity check on the fixture itself - if this generator ever stops
        # planting the trap, every other test in this class would pass
        # vacuously and stop meaning anything.
        keys = {row["feature_key"] for row in self.dataset["region_features"]}
        self.assertIn(ground_truth.LEAKAGE_TRAP_FEATURE_KEY, keys)

    def test_correctly_scoped_store_never_sees_the_trap_before_cutoff(self) -> None:
        # this is the actual guard the harness runs on every backtest.
        harness.assert_no_leakage_before_cutoff(self.store, self.region_ids, self.train_periods)  # must not raise

    def test_leaky_accessor_actually_leaks_the_trap_value(self) -> None:
        # proves _leaky_latest_value is a real bug shape, not a strawman:
        # for the same (region, as_of) the correct store says None and the
        # broken one returns the planted future value.
        as_of = f"{self.train_periods[-1]}-01"
        region_id = self.region_ids[0]
        correct = self.store.get_features([region_id], [ground_truth.LEAKAGE_TRAP_FEATURE_KEY], as_of)[region_id][
            ground_truth.LEAKAGE_TRAP_FEATURE_KEY
        ]
        leaky = harness._leaky_latest_value(self.store, region_id, ground_truth.LEAKAGE_TRAP_FEATURE_KEY)
        self.assertIsNone(correct)
        self.assertIsNotNone(leaky)

    def test_guard_actually_fires_against_a_store_with_the_bug(self) -> None:
        # the completion bar: does the harness CATCH the trap, not just
        # define one. Swap in a broken get_features (mirrors _leaky_latest_value)
        # on a throwaway store instance and confirm the guard raises.
        leaky_store = SyntheticFeatureStore.from_dataset(self.dataset)

        def broken_get_features(region_ids, feature_keys, as_of):
            out = {}
            for region_id in region_ids:
                out[region_id] = {
                    key: harness._leaky_latest_value(leaky_store, region_id, key) for key in feature_keys
                }
            return out

        leaky_store.get_features = broken_get_features
        with self.assertRaises(harness.LeakageDetectedError):
            harness.assert_no_leakage_before_cutoff(leaky_store, self.region_ids, self.train_periods)


class RunBacktestTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = generate.generate_all(seed=42, start_period="2025-01", end_period="2026-06")
        cls.store = SyntheticFeatureStore.from_dataset(cls.dataset)

    def test_run_backtest_recovers_the_planted_relationship_out_of_sample(self) -> None:
        # 05_scoring_spec.md §5.2: Spearman rho is the headline metric.
        # This is the actual bar B-4's Step 1 planted coefficient promised
        # would be recoverable "through the model" (test_factor_model.py's
        # in-sample version of this claim) - here it's out-of-sample,
        # via a time split + as_of-pinned re-fetch, exactly as §5.1 requires.
        result = harness.run_backtest(
            self.dataset,
            self.store,
            taxonomy_node_id=_RTD_NODE,
            channel="cvs",
            train_cutoff=_TRAIN_CUTOFF,
            price_tier="mid",
            product_attributes=_RTD_ATTRS,
            seasonality_profile=_RTD_SEASONALITY,
        )
        self.assertEqual(result["train_periods"][-1] < _TRAIN_CUTOFF, True)
        self.assertTrue(all(p >= _TRAIN_CUTOFF for p in result["validation_periods"]))

        all_splits = result["all_regions"]
        self.assertGreater(len(all_splits), 0, "no validation period produced a scorable split")
        mean_rho = sum(s.spearman_rho for s in all_splits) / len(all_splits)
        mean_lift = sum(s.top_decile_lift for s in all_splits) / len(all_splits)
        self.assertGreater(mean_rho, 0.3, f"mean out-of-sample Spearman rho too low: {mean_rho:.3f}")
        self.assertGreater(mean_lift, 1.2, f"mean out-of-sample top-decile lift too low: {mean_lift:.3f}")

    def test_run_backtest_holdout_regions_are_disjoint_from_the_full_set_report(self) -> None:
        result = harness.run_backtest(
            self.dataset,
            self.store,
            taxonomy_node_id=_RTD_NODE,
            channel="cvs",
            train_cutoff=_TRAIN_CUTOFF,
            product_attributes=_RTD_ATTRS,
            seasonality_profile=_RTD_SEASONALITY,
        )
        holdout_ids = set(result["holdout_region_ids"])
        all_ids = set(self.store.all_adm_dong_ids())
        self.assertTrue(holdout_ids.issubset(all_ids))
        self.assertLess(len(holdout_ids), len(all_ids))
        self.assertGreater(len(result["holdout_regions"]), 0, "holdout split produced no scorable validation period")


if __name__ == "__main__":
    unittest.main()
