"""RegionFeatureFileStore tests. DISPATCH-2.md B-2: the real feature-store
reader for data-platform(A)'s eventual output, tested against a fixture
matching 01_domain_model.json's region_feature schema exactly (A has not
published a real artifact yet - see feature_store.py's class docstring).

The one thing this file exists to prove, per B-2's completion bar: as_of
is never bypassed. There is no "latest value" fallback anywhere.

Run from /intelligence:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scoring.feature_store import RegionFeatureFileStore

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "region_features_fixture"


class RegionFeatureFileStoreLoadingTestCase(unittest.TestCase):
    def test_from_directory_raises_if_no_files_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                RegionFeatureFileStore.from_directory(tmp)

    def test_from_directory_loads_every_json_file_in_the_directory(self) -> None:
        store = RegionFeatureFileStore.from_directory(_FIXTURE_DIR)
        # rows from both 91001001.json and 91001002.json must be present
        feats = store.get_features(["91001001", "91001002"], ["pop_total", "pop_age_dist"], "2026-01-01")
        self.assertIsNotNone(feats["91001001"]["pop_total"])
        self.assertIsNotNone(feats["91001002"]["pop_age_dist"])

    def test_non_list_json_file_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "bad.json"
            bad_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                RegionFeatureFileStore.from_directory(tmp)

    def test_row_missing_required_field_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "bad.json"
            bad_row = {
                "region_id": "91001001",
                "feature_key": "pop_total",
                "value_num": 100,
                "value_json": None,
                "valid_from": "2025-01-01",
                "valid_to": None,
                # source_id and ingested_at omitted on purpose
            }
            bad_path.write_text(json.dumps([bad_row]), encoding="utf-8")
            with self.assertRaises(ValueError):
                RegionFeatureFileStore.from_directory(tmp)

    def test_get_demand_is_not_implemented_rather_than_faked(self) -> None:
        store = RegionFeatureFileStore.from_directory(_FIXTURE_DIR)
        with self.assertRaises(NotImplementedError):
            store.get_demand(["91001001"], "TX-FOOD-BEV-COFFEE-RTD", "cvs", "2025-06")


class PointInTimeTestCase(unittest.TestCase):
    """The actual B-2 completion bar: as_of is never bypassed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.store = RegionFeatureFileStore.from_directory(_FIXTURE_DIR)

    def test_as_of_before_the_earliest_valid_from_returns_none_not_the_earliest_row(self) -> None:
        # income_decile's only row starts 2024-01-01 - querying before that
        # must come back None, NOT silently hand back that row as "the
        # closest available value". That silent hand-back is exactly the
        # "get latest value" helper 03_region_features.json's
        # point_in_time_rule forbids.
        feats = self.store.get_features(["91001001"], ["income_decile"], "2020-01-01")
        self.assertIsNone(feats["91001001"]["income_decile"])

    def test_as_of_exactly_at_valid_from_is_inclusive(self) -> None:
        feats = self.store.get_features(["91001001"], ["income_decile"], "2024-01-01")
        self.assertEqual(feats["91001001"]["income_decile"], 6)

    def test_as_of_within_the_first_window_returns_the_first_value(self) -> None:
        # pop_total: 50000 valid [2025-01-01, 2025-07-01), 52000 valid [2025-07-01, )
        feats = self.store.get_features(["91001001"], ["pop_total"], "2025-04-01")
        self.assertEqual(feats["91001001"]["pop_total"], 50000)

    def test_as_of_before_the_first_pop_total_row_returns_none(self) -> None:
        feats = self.store.get_features(["91001001"], ["pop_total"], "2024-12-31")
        self.assertIsNone(feats["91001001"]["pop_total"])

    def test_as_of_at_the_transition_boundary_returns_the_new_value_not_the_old_one(self) -> None:
        # valid_to is exclusive on the old row, valid_from is inclusive on
        # the new one - 2025-07-01 must see the NEW value, not the old one
        # still hanging around one day too long.
        feats = self.store.get_features(["91001001"], ["pop_total"], "2025-07-01")
        self.assertEqual(feats["91001001"]["pop_total"], 52000)

    def test_as_of_one_day_before_the_transition_still_sees_the_old_value(self) -> None:
        feats = self.store.get_features(["91001001"], ["pop_total"], "2025-06-30")
        self.assertEqual(feats["91001001"]["pop_total"], 50000)

    def test_as_of_long_after_an_open_ended_row_still_returns_it(self) -> None:
        # valid_to=None means "currently valid" - a far-future as_of should
        # still see it (this is not a leak - it is not a FUTURE row, it is
        # the currently-open one).
        feats = self.store.get_features(["91001001"], ["pop_total"], "2030-01-01")
        self.assertEqual(feats["91001001"]["pop_total"], 52000)

    def test_value_json_branch_returns_the_dict_not_value_num(self) -> None:
        feats = self.store.get_features(["91001002"], ["pop_age_dist"], "2025-06-01")
        dist = feats["91001002"]["pop_age_dist"]
        self.assertIsInstance(dist, dict)
        self.assertAlmostEqual(sum(dist.values()), 1.0, places=6)

    def test_unknown_region_or_key_returns_none_not_a_crash(self) -> None:
        feats = self.store.get_features(["99999999"], ["pop_total"], "2025-06-01")
        self.assertIsNone(feats["99999999"]["pop_total"])
        feats2 = self.store.get_features(["91001001"], ["nonexistent_feature_key"], "2025-06-01")
        self.assertIsNone(feats2["91001001"]["nonexistent_feature_key"])


if __name__ == "__main__":
    unittest.main()
