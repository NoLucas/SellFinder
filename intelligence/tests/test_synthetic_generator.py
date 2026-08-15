"""Invariant tests for the Step 1 synthetic data generator.

Run from /intelligence:
    python -m unittest discover -s tests -v

Stdlib-only (unittest, not pytest) so nobody needs to install anything
just to run this.
"""
from __future__ import annotations

import statistics
import unittest

from synthetic import contracts, demand_gen, generate, ground_truth


class GeneratedDatasetTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = generate.generate_all(seed=42, start_period="2025-01", end_period="2026-06")
        cls.registry = contracts.load_feature_registry()
        cls.periods = cls.dataset["manifest"]["periods"]

    # ------------------------------------------------------------------
    # region_feature conforms to the contract
    # ------------------------------------------------------------------
    def test_feature_keys_are_registry_keys_or_the_declared_leakage_trap(self) -> None:
        allowed = set(self.registry.keys()) | {ground_truth.LEAKAGE_TRAP_FEATURE_KEY}
        seen_keys = {row["feature_key"] for row in self.dataset["region_features"]}
        self.assertTrue(seen_keys.issubset(allowed), f"unexpected feature keys: {seen_keys - allowed}")
        # and every non-trap key must be real (guards against typos silently
        # inventing a new key that happens to slip past the check above)
        non_trap_keys = seen_keys - {ground_truth.LEAKAGE_TRAP_FEATURE_KEY}
        self.assertTrue(non_trap_keys.issubset(self.registry.keys()))

    def test_no_tenant_scoped_features_leaked_into_the_shared_store(self) -> None:
        # tenant_scoped keys per 03_region_features.json must never appear here
        tenant_scoped_keys = {"own_store_count_2km", "own_distribution_points", "own_share_of_category"}
        seen_keys = {row["feature_key"] for row in self.dataset["region_features"]}
        self.assertFalse(seen_keys & tenant_scoped_keys)

    def test_missingness_present_but_never_zero_filled(self) -> None:
        rows = self.dataset["region_features"]
        null_rows = [r for r in rows if r["value_num"] is None and r["value_json"] is None]
        self.assertGreater(len(null_rows), 0, "generator produced no missingness at all")
        self.assertLess(len(null_rows) / len(rows), 0.5, "missingness rate implausibly high")
        # pop_total is a basic, cheap-to-collect feature - if it's present it
        # should never have been silently coerced to 0 as a missing-value stand-in
        pop_total_values = [r["value_num"] for r in rows if r["feature_key"] == "pop_total" and r["value_num"] is not None]
        self.assertTrue(all(v > 0 for v in pop_total_values))

    def test_pop_age_dist_sums_to_one_when_present(self) -> None:
        rows = [r for r in self.dataset["region_features"] if r["feature_key"] == "pop_age_dist" and r["value_json"]]
        self.assertGreater(len(rows), 0)
        for r in rows:
            total = sum(r["value_json"].values())
            self.assertAlmostEqual(total, 1.0, delta=0.01, msg=r)

    def test_valid_from_valid_to_chain_without_overlap(self) -> None:
        rows = self.dataset["region_features"]
        groups: dict[tuple, list[dict]] = {}
        for r in rows:
            groups.setdefault((r["region_id"], r["feature_key"]), []).append(r)
        for key, group_rows in groups.items():
            ordered = sorted(group_rows, key=lambda r: r["valid_from"])
            for a, b in zip(ordered, ordered[1:]):
                self.assertLess(a["valid_from"], b["valid_from"], key)
                self.assertEqual(a["valid_to"], b["valid_from"], f"gap/overlap in {key}")
            self.assertIsNone(ordered[-1]["valid_to"], f"last row of {key} should still be open-ended")

    # ------------------------------------------------------------------
    # leakage trap
    # ------------------------------------------------------------------
    def test_leakage_trap_absent_before_cutoff_present_after(self) -> None:
        trap_rows = [r for r in self.dataset["region_features"] if r["feature_key"] == ground_truth.LEAKAGE_TRAP_FEATURE_KEY]
        self.assertGreater(len(trap_rows), 0)
        self.assertTrue(all(r["valid_from"] >= ground_truth.LEAKAGE_TRAP_CUTOFF for r in trap_rows))
        # and it must genuinely be absent (no row at all), not present-but-null,
        # for every period before the cutoff
        pre_cutoff_periods = [p for p in self.periods if f"{p}-01" < ground_truth.LEAKAGE_TRAP_CUTOFF]
        trap_periods_seen = {r["valid_from"][:7] for r in trap_rows}
        self.assertFalse(set(pre_cutoff_periods) & trap_periods_seen)

    def test_leakage_trap_key_is_not_a_real_contract_feature(self) -> None:
        self.assertNotIn(ground_truth.LEAKAGE_TRAP_FEATURE_KEY, self.registry)

    def test_leakage_trap_value_is_genuinely_derived_from_future_demand(self) -> None:
        # not just correlated - the trap's value for a region must equal that
        # region's own average RTD spend_index over the validation window, so
        # a harness that leaks it is leaking the real future target, not a proxy.
        validation_periods = {p for p in self.periods if f"{p}-01" >= ground_truth.LEAKAGE_TRAP_CUTOFF}
        future_avg: dict[str, float] = {}
        by_region: dict[str, list[float]] = {}
        for r in self.dataset["demand_signal"]:
            if (
                r["taxonomy_node_id"] == ground_truth.LEAKAGE_TRAP_SOURCE_NODE
                and r["period"] in validation_periods
                and r["spend_index"] is not None
            ):
                by_region.setdefault(r["region_id"], []).append(r["spend_index"])
        for region_id, values in by_region.items():
            future_avg[region_id] = sum(values) / len(values)

        trap_rows = [r for r in self.dataset["region_features"] if r["feature_key"] == ground_truth.LEAKAGE_TRAP_FEATURE_KEY]
        checked = 0
        for r in trap_rows:
            expected = future_avg.get(r["region_id"])
            if expected is None:
                continue  # region had every validation cell suppressed - generator falls back, nothing to check
            self.assertAlmostEqual(r["value_num"], expected, delta=0.01)
            checked += 1
        self.assertGreater(checked, 0, "no trap rows had matching demand_signal data to verify against")

    # ------------------------------------------------------------------
    # region size distribution
    # ------------------------------------------------------------------
    def test_region_population_spans_required_extremes(self) -> None:
        adm_dong = [r for r in self.dataset["regions"] if r["level"] == "adm_dong"]
        pops = {r["region_id"]: None for r in adm_dong}
        # pop_total lives in region_features, not the region record itself
        latest_pop_rows = [r for r in self.dataset["region_features"] if r["feature_key"] == "pop_total"]
        by_region_latest = {}
        for r in latest_pop_rows:
            if r["value_num"] is None:
                continue
            prev = by_region_latest.get(r["region_id"])
            if prev is None or r["valid_from"] > prev["valid_from"]:
                by_region_latest[r["region_id"]] = r
        values = [r["value_num"] for r in by_region_latest.values()]
        self.assertLess(min(values), 30_000)
        self.assertGreater(max(values), 400_000)
        under_30k = [v for v in values if v < 30_000]
        self.assertGreaterEqual(len(under_30k), 5, "need enough small adm_dong to exercise the pop<30k confidence rule")

    def test_region_hierarchy_referential_integrity(self) -> None:
        by_id = {r["region_id"]: r for r in self.dataset["regions"]}
        for r in self.dataset["regions"]:
            if r["parent_id"] is not None:
                self.assertIn(r["parent_id"], by_id, f"{r['region_id']} points to missing parent {r['parent_id']}")

    # ------------------------------------------------------------------
    # demand_signal / suppression
    # ------------------------------------------------------------------
    def test_suppressed_cells_never_expose_raw_values(self) -> None:
        rows = self.dataset["demand_signal"]
        suppressed = [r for r in rows if r["coverage_flag"] == "suppressed"]
        self.assertGreater(len(suppressed), 0, "generator produced no suppressed cells at all")
        for r in suppressed:
            self.assertIsNone(r["spend_krw"])
            self.assertIsNone(r["transaction_count"])
            self.assertIsNone(r["store_count"])
            self.assertIsNone(r["spend_index"])

    def test_curated_nodes_exist_in_real_taxonomy(self) -> None:
        leaves = {leaf["node_id"] for leaf in contracts.flatten_taxonomy_leaves()}
        for node_id in demand_gen.CURATED_NODES:
            self.assertIn(node_id, leaves, f"{node_id} is not a real node_id in 02_taxonomy.json")

    def test_online_channels_have_no_store_count(self) -> None:
        rows = self.dataset["demand_signal"]
        for r in rows:
            if r["channel"] in demand_gen._ONLINE_CHANNELS:
                self.assertIsNone(r["store_count"])

    # ------------------------------------------------------------------
    # ground truth relationships actually show up in the data
    # ------------------------------------------------------------------
    def test_planted_relationships_are_recoverable_in_spend_index(self) -> None:
        demand_by_node_region: dict[tuple, list[float]] = {}
        for r in self.dataset["demand_signal"]:
            if r["spend_index"] is None:
                continue
            demand_by_node_region.setdefault((r["taxonomy_node_id"], r["region_id"]), []).append(r["spend_index"])

        for rel in self.dataset["ground_truth"]["planted_relationships"]:
            node_id = rel["taxonomy_node_id"]
            qualifying = set(rel["qualifying_region_ids"])
            qual_values, other_values = [], []
            for (nid, rid), values in demand_by_node_region.items():
                if nid != node_id:
                    continue
                avg = statistics.mean(values)
                (qual_values if rid in qualifying else other_values).append(avg)
            self.assertTrue(qual_values and other_values, f"missing data to check {rel['id']}")
            qual_mean = statistics.mean(qual_values)
            other_mean = statistics.mean(other_values)
            observed_ratio = qual_mean / other_mean
            # noise + seasonality mean this won't hit the multiplier exactly;
            # just check the plant clearly shows up in the expected direction
            # and rough magnitude.
            self.assertGreater(
                observed_ratio,
                rel["multiplier"] * 0.6,
                f"{rel['id']}: planted multiplier {rel['multiplier']}x not recoverable (observed {observed_ratio:.2f}x)",
            )

    # ------------------------------------------------------------------
    # reproducibility
    # ------------------------------------------------------------------
    def test_same_seed_is_fully_reproducible(self) -> None:
        a = generate.generate_all(seed=123, start_period="2025-06", end_period="2025-09")
        b = generate.generate_all(seed=123, start_period="2025-06", end_period="2025-09")
        self.assertEqual(a["regions"], b["regions"])
        self.assertEqual(a["region_features"], b["region_features"])
        self.assertEqual(a["demand_signal"], b["demand_signal"])

    def test_different_seed_changes_output(self) -> None:
        a = generate.generate_all(seed=1, start_period="2025-06", end_period="2025-07")
        b = generate.generate_all(seed=2, start_period="2025-06", end_period="2025-07")
        self.assertNotEqual(a["region_features"], b["region_features"])


if __name__ == "__main__":
    unittest.main()
