"""region_feature generator.

Two passes, by design:

1. build_region_profiles() draws ONE stable "profile" per region (income
   decile, age mix, single-household ratio, etc.), correlated with the
   region's synthetic type (metro/major_city/mid_city/rural). This profile
   is what ground_truth.py's planted relationships condition on - keeping
   conditioning on a stable per-region value (not a noisy monthly draw)
   is what makes the plant checkable later.
2. generate_region_feature_rows() turns each profile into a monthly time
   series per feature_key, adding small period-to-period drift/noise on
   top of the stable base, plus missingness (never 0-fill - see
   feature_quality_rules in 03_region_features.json).

spend_index_by_node and store_count_by_node are deliberately NOT
generated here as independent random values: 03_region_features.json
says spend_index_by_node "demand_signal에서 파생" (derived from
demand_signal), so this module exposes `attach_derived_from_demand()`
that fills those two keys in from the already-generated demand_signal
rows, to keep the two data products internally consistent.
"""
from __future__ import annotations

import random
from datetime import date

from . import contracts, ground_truth

AGE_BUCKETS = ["0_9", "10s", "20s", "30s", "40s", "50s", "60plus"]

# Base missing-rate per feature_key. Features that are described in
# 03_region_features.json as license-gated or telco-derived (foot
# traffic, card spend) are the ones real pipelines actually struggle to
# fill, so they get the highest miss rates. Everything else gets a small
# baseline so "no missingness at all" never happens.
_MISS_RATE_OVERRIDES = {
    "foot_traffic_weekday": 0.30,
    "foot_traffic_weekend": 0.30,
    "foot_traffic_peak_hour": 0.35,
    "card_spend_per_capita": 0.40,
    "transit_boarding_daily": 0.20,
    "quick_commerce_coverage": 0.25,
    "ecommerce_order_density": 0.20,
    "online_penetration_by_node": 0.25,
}
_DEFAULT_MISS_RATE = 0.08
# rural regions are the sparsest-collected in real pipelines too
_RURAL_EXTRA_MISS = 0.15


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def build_region_profiles(
    adm_dong_ids_by_type: dict[str, list[str]],
    pop_by_region: dict[str, int],
    rng: random.Random,
) -> dict[str, dict]:
    """One stable profile per adm_dong region."""
    profiles: dict[str, dict] = {}

    income_range = {"metro": (6, 10), "major_city": (4, 9), "mid_city": (3, 8), "rural": (1, 6)}
    single_hh_range = {"metro": (0.35, 0.55), "major_city": (0.28, 0.48), "mid_city": (0.22, 0.4), "rural": (0.15, 0.32)}
    daytime_factor_range = {"metro": (0.9, 1.7), "major_city": (0.8, 1.3), "mid_city": (0.7, 1.1), "rural": (0.6, 1.0)}
    young_skew = {"metro": 1.35, "major_city": 1.15, "mid_city": 0.95, "rural": 0.55}
    subway_range = {"metro": (2, 9), "major_city": (0, 4), "mid_city": (0, 1), "rural": (0, 0)}
    apt_price_range = {"metro": (55, 100), "major_city": (35, 70), "mid_city": (20, 45), "rural": (8, 25)}
    grade_pool = {
        "metro": ["A", "A", "B"],
        "major_city": ["A", "B", "B", "C"],
        "mid_city": ["B", "C", "C"],
        "rural": ["C", "D", "D"],
    }

    for region_type, region_ids in adm_dong_ids_by_type.items():
        for region_id in region_ids:
            pop_total = pop_by_region[region_id]
            household_size = rng.uniform(1.8, 2.4) if region_type in ("metro", "major_city") else rng.uniform(2.4, 3.3)
            household_count = round(pop_total / household_size)

            # age distribution: sample unnormalized weights skewed by region type, then normalize to sum=1.0
            base_weights = [0.09, 0.11, 0.16, 0.16, 0.16, 0.15, 0.17]
            skew = young_skew[region_type]
            weights = [
                base_weights[0] * rng.uniform(0.8, 1.2),
                base_weights[1] * rng.uniform(0.8, 1.2),
                base_weights[2] * skew * rng.uniform(0.85, 1.15),
                base_weights[3] * skew * rng.uniform(0.85, 1.15),
                base_weights[4] * rng.uniform(0.85, 1.15),
                base_weights[5] * rng.uniform(0.85, 1.15),
                base_weights[6] * (2.0 - skew) * rng.uniform(0.85, 1.15),
            ]
            total_w = sum(weights)
            pop_age_dist = {b: round(w / total_w, 4) for b, w in zip(AGE_BUCKETS, weights)}
            # fix rounding drift onto the largest bucket so it still sums to 1.0
            drift = round(1.0 - sum(pop_age_dist.values()), 4)
            largest = max(pop_age_dist, key=pop_age_dist.get)
            pop_age_dist[largest] = round(pop_age_dist[largest] + drift, 4)

            income_lo, income_hi = income_range[region_type]
            income_decile = rng.randint(income_lo, income_hi)

            single_lo, single_hi = single_hh_range[region_type]
            single_household_ratio = round(rng.uniform(single_lo, single_hi), 3)

            dt_lo, dt_hi = daytime_factor_range[region_type]
            daytime_factor = rng.uniform(dt_lo, dt_hi)
            daytime_pop = round(pop_total * daytime_factor)

            young_adult_share = pop_age_dist["20s"] + pop_age_dist["30s"]
            birth_count_12m = round(pop_total * young_adult_share * rng.uniform(0.006, 0.02))

            pet_rate = rng.uniform(0.03, 0.16)
            pet_registered_count = round(household_count * pet_rate)

            apt_lo, apt_hi = apt_price_range[region_type]
            apartment_price_index = round(_clamp(rng.uniform(apt_lo, apt_hi) + income_decile * 1.5, 5, 120), 1)

            card_spend_per_capita = round(180_000 + income_decile * 42_000 * rng.uniform(0.85, 1.2))

            new_apt_base = rng.choices([0, rng.randint(50, 400), rng.randint(400, 2200)], weights=[0.55, 0.3, 0.15])[0]
            new_apartment_units_12m = new_apt_base if isinstance(new_apt_base, int) else 0
            redevelopment_flag = new_apartment_units_12m > 1000 and rng.random() < 0.6

            pop_growth_rate_36m = round(
                rng.uniform(-0.12, 0.05) if region_type == "rural" else rng.uniform(-0.03, 0.14), 4
            )

            sub_lo, sub_hi = subway_range[region_type]
            subway_station_count = rng.randint(sub_lo, sub_hi) if sub_hi > 0 else 0
            transit_boarding_daily = round(
                pop_total * rng.uniform(0.15, 0.45) + subway_station_count * rng.uniform(3000, 9000)
            )
            parking_capacity = round(rng.uniform(300, 1200) * (1.4 if region_type in ("mid_city", "rural") else 0.8))
            road_accessibility_score = round(_clamp(rng.uniform(0.4, 0.95) - (0.1 if region_type == "rural" else 0), 0, 1), 3)

            store_open_rate_12m = round(rng.uniform(0.03, 0.14), 3)
            store_close_rate_12m = round(
                rng.uniform(0.02, 0.10) if region_type != "rural" else rng.uniform(0.05, 0.18), 3
            )
            avg_rent_krw_per_m2 = round(apartment_price_index * rng.uniform(2800, 4200))
            trade_area_grade = rng.choice(grade_pool[region_type])
            anchor_facility_count = {
                "university": rng.choices([0, 1, 2], weights=[0.6, 0.3, 0.1])[0],
                "hospital": rng.choices([0, 1, 2, 3], weights=[0.3, 0.4, 0.2, 0.1])[0],
                "government_office": rng.choices([0, 1, 2], weights=[0.5, 0.4, 0.1])[0],
                "large_office": rng.choices([0, 1, 2, 3], weights=[0.5, 0.25, 0.15, 0.1] if region_type in ("metro", "major_city") else [0.85, 0.1, 0.04, 0.01])[0],
            }

            foot_traffic_weekday = round(pop_total * rng.uniform(0.25, 0.55) * daytime_factor)
            foot_traffic_weekend = round(foot_traffic_weekday * rng.uniform(0.7, 1.3))
            foot_traffic_peak_hour = {
                "morning_6_9": round(rng.uniform(0.10, 0.20), 3),
                "lunch_11_14": round(rng.uniform(0.18, 0.30), 3),
                "evening_17_20": round(rng.uniform(0.20, 0.32), 3),
                "night_20_24": round(rng.uniform(0.08, 0.22), 3),
            }
            ecommerce_order_density = round(rng.uniform(40, 220) * rng.uniform(0.9, 1.1), 1)
            quick_commerce_coverage = round(
                _clamp(rng.uniform(0.5, 1.0) if region_type in ("metro", "major_city") else rng.uniform(0.0, 0.35), 0, 1), 3
            )
            online_penetration_base = round(_clamp(rng.uniform(0.25, 0.55), 0, 1), 3)

            profiles[region_id] = {
                "region_type": region_type,
                "pop_total": pop_total,
                "household_count": household_count,
                "pop_age_dist": pop_age_dist,
                "income_decile": income_decile,
                "single_household_ratio": single_household_ratio,
                "daytime_pop": daytime_pop,
                "daytime_night_ratio": round(daytime_pop / pop_total, 3),
                "birth_count_12m": birth_count_12m,
                "pet_registered_count": pet_registered_count,
                "apartment_price_index": apartment_price_index,
                "card_spend_per_capita": card_spend_per_capita,
                "new_apartment_units_12m": new_apartment_units_12m,
                "redevelopment_flag": redevelopment_flag,
                "pop_growth_rate_36m": pop_growth_rate_36m,
                "subway_station_count": subway_station_count,
                "transit_boarding_daily": transit_boarding_daily,
                "parking_capacity": parking_capacity,
                "road_accessibility_score": road_accessibility_score,
                "store_open_rate_12m": store_open_rate_12m,
                "store_close_rate_12m": store_close_rate_12m,
                "avg_rent_krw_per_m2": avg_rent_krw_per_m2,
                "trade_area_grade": trade_area_grade,
                "anchor_facility_count": anchor_facility_count,
                "foot_traffic_weekday": foot_traffic_weekday,
                "foot_traffic_weekend": foot_traffic_weekend,
                "foot_traffic_peak_hour": foot_traffic_peak_hour,
                "ecommerce_order_density": ecommerce_order_density,
                "quick_commerce_coverage": quick_commerce_coverage,
                "online_penetration_base": online_penetration_base,
            }
    return profiles


# feature_key -> function(profile, period_index, rng) -> raw value (pre-missingness)
def _make_generators() -> dict:
    def drift(base: float, period_index: int, rng: random.Random, pct: float = 0.02) -> float:
        # small monotonic-ish drift + noise so time series aren't flat, but
        # stay close to the stable profile the ground-truth conditions on.
        return base * (1 + rng.uniform(-pct, pct) + 0.0015 * period_index)

    return {
        "pop_total": lambda p, i, r: round(drift(p["pop_total"], i, r, 0.005)),
        "pop_age_dist": lambda p, i, r: p["pop_age_dist"],
        "household_count": lambda p, i, r: round(drift(p["household_count"], i, r, 0.005)),
        "single_household_ratio": lambda p, i, r: round(_clamp(drift(p["single_household_ratio"], i, r, 0.02), 0, 1), 3),
        "daytime_pop": lambda p, i, r: round(drift(p["daytime_pop"], i, r, 0.01)),
        "daytime_night_ratio": lambda p, i, r: p["daytime_night_ratio"],
        "birth_count_12m": lambda p, i, r: max(0, round(drift(p["birth_count_12m"], i, r, 0.06))),
        "pet_registered_count": lambda p, i, r: max(0, round(drift(p["pet_registered_count"], i, r, 0.02))),
        "income_decile": lambda p, i, r: p["income_decile"],
        "card_spend_per_capita": lambda p, i, r: round(drift(p["card_spend_per_capita"], i, r, 0.015)),
        "apartment_price_index": lambda p, i, r: round(drift(p["apartment_price_index"], i, r, 0.01), 1),
        "foot_traffic_weekday": lambda p, i, r: max(0, round(drift(p["foot_traffic_weekday"], i, r, 0.05))),
        "foot_traffic_weekend": lambda p, i, r: max(0, round(drift(p["foot_traffic_weekend"], i, r, 0.06))),
        "foot_traffic_peak_hour": lambda p, i, r: p["foot_traffic_peak_hour"],
        "transit_boarding_daily": lambda p, i, r: max(0, round(drift(p["transit_boarding_daily"], i, r, 0.03))),
        "subway_station_count": lambda p, i, r: p["subway_station_count"],
        "parking_capacity": lambda p, i, r: round(p["parking_capacity"]),
        "road_accessibility_score": lambda p, i, r: p["road_accessibility_score"],
        "store_open_rate_12m": lambda p, i, r: max(0, round(drift(p["store_open_rate_12m"], i, r, 0.1), 3)),
        "store_close_rate_12m": lambda p, i, r: max(0, round(drift(p["store_close_rate_12m"], i, r, 0.1), 3)),
        "avg_rent_krw_per_m2": lambda p, i, r: round(drift(p["avg_rent_krw_per_m2"], i, r, 0.01)),
        "trade_area_grade": lambda p, i, r: p["trade_area_grade"],
        "anchor_facility_count": lambda p, i, r: p["anchor_facility_count"],
        "new_apartment_units_12m": lambda p, i, r: p["new_apartment_units_12m"],
        "redevelopment_flag": lambda p, i, r: 1.0 if p["redevelopment_flag"] else 0.0,
        "pop_growth_rate_36m": lambda p, i, r: p["pop_growth_rate_36m"],
        "ecommerce_order_density": lambda p, i, r: max(0, round(drift(p["ecommerce_order_density"], i, r, 0.04), 1)),
        "quick_commerce_coverage": lambda p, i, r: p["quick_commerce_coverage"],
        # placeholder; real values attached from demand_signal by attach_derived_from_demand()
        "online_penetration_by_node": lambda p, i, r: {},
        "spend_index_by_node": lambda p, i, r: {},
        "store_count_by_node": lambda p, i, r: {},
    }


_GENERATORS = _make_generators()

# keys attach_derived_from_demand() fills; skip independent generation for these
_DERIVED_FROM_DEMAND = {"spend_index_by_node", "store_count_by_node"}


def period_list(start: str, end: str) -> list[str]:
    y0, m0 = map(int, start.split("-")[:2])
    y1, m1 = map(int, end.split("-")[:2])
    out = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m = 1
            y += 1
    return out


def generate_region_feature_rows(
    profiles: dict[str, dict],
    start_period: str,
    end_period: str,
    rng: random.Random,
    source_ids: dict[str, str],
    demand_rows: list[dict] | None = None,
    include_leakage_trap: bool = True,
) -> list[dict]:
    registry = contracts.load_feature_registry()
    periods = period_list(start_period, end_period)
    rows: list[dict] = []
    ingested_at = f"{end_period}-01T00:00:00Z"

    for region_id, profile in profiles.items():
        region_type = profile["region_type"]
        for feature_key, meta in registry.items():
            if feature_key in _DERIVED_FROM_DEMAND:
                continue  # attached later from demand_signal
            gen = _GENERATORS.get(feature_key)
            if gen is None:
                continue  # not yet modeled (e.g. online_penetration_by_node handled via demand)
            feature_type = meta.get("type")
            miss_rate = _MISS_RATE_OVERRIDES.get(feature_key, _DEFAULT_MISS_RATE)
            if region_type == "rural":
                miss_rate = min(0.85, miss_rate + _RURAL_EXTRA_MISS)
            source_id = source_ids.get(meta["_category"], source_ids["default"])

            for period_index, period in enumerate(periods):
                valid_from = f"{period}-01"
                missing = rng.random() < miss_rate
                if missing:
                    value_num, value_json = None, None
                else:
                    val = gen(profile, period_index, rng)
                    if feature_type == "json":
                        value_num, value_json = None, val
                    elif feature_type == "string":
                        # region_feature only has value_num/value_json - categorical
                        # strings (e.g. trade_area_grade: A/B/C/D) go into value_json,
                        # wrapped so it stays a JSON *object* per the contract's typing.
                        value_num, value_json = None, {"value": val}
                    else:
                        value_num, value_json = float(val), None
                rows.append(
                    {
                        "region_id": region_id,
                        "feature_key": feature_key,
                        "value_num": value_num,
                        "value_json": value_json,
                        "valid_from": valid_from,
                        "valid_to": None,  # chained below
                        "source_id": source_id,
                        "ingested_at": ingested_at,
                    }
                )

    _chain_valid_to(rows)

    if include_leakage_trap:
        rows.extend(
            _generate_leakage_trap_rows(profiles, periods, demand_rows or [], source_ids["default"], ingested_at)
        )
        _chain_valid_to(rows, only_key=ground_truth.LEAKAGE_TRAP_FEATURE_KEY)

    return rows


def _chain_valid_to(rows: list[dict], only_key: str | None = None) -> None:
    """Set valid_to[n] = valid_from[n+1] for consecutive rows of the same (region_id, feature_key)."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        if only_key is not None and row["feature_key"] != only_key:
            continue
        groups.setdefault((row["region_id"], row["feature_key"]), []).append(row)
    for group_rows in groups.values():
        group_rows.sort(key=lambda r: r["valid_from"])
        for a, b in zip(group_rows, group_rows[1:]):
            a["valid_to"] = b["valid_from"]
        group_rows[-1]["valid_to"] = None


def _generate_leakage_trap_rows(
    profiles: dict[str, dict], periods: list[str], demand_rows: list[dict], source_id: str, ingested_at: str
) -> list[dict]:
    """See ground_truth.py's LEAKAGE_TRAP_* docstring for the mechanism.

    The trap value is the region's own average RTD-coffee spend_index over
    the validation window (LEAKAGE_TRAP_CUTOFF onward), pulled straight out
    of demand_rows - i.e. it really is "this region's future performance",
    not just something correlated with it. Every row in the trap window
    carries the same value (a single future-window summary joined onto
    every month) - that's the realistic shape of the real-world mistake
    this is modeling (a "current-quarter actuals" column computed once
    and joined back across the period).
    """
    trap_periods = [p for p in periods if f"{p}-01" >= ground_truth.LEAKAGE_TRAP_CUTOFF]
    if not trap_periods:
        return []
    trap_period_set = set(trap_periods)

    future_values: dict[str, list[float]] = {}
    for d in demand_rows:
        if (
            d["taxonomy_node_id"] == ground_truth.LEAKAGE_TRAP_SOURCE_NODE
            and d["period"] in trap_period_set
            and d["spend_index"] is not None
        ):
            future_values.setdefault(d["region_id"], []).append(d["spend_index"])

    rows = []
    for region_id, profile in profiles.items():
        values = future_values.get(region_id)
        if values:
            proxy = sum(values) / len(values)
        else:
            # region had every validation-window cell suppressed (rare, small
            # regions) - fall back to the same signals the planted
            # relationship itself uses, so the trap still exists everywhere.
            proxy = 100 * (1 + profile["pop_age_dist"]["20s"] + profile["pop_age_dist"]["30s"])
        for period in trap_periods:
            rows.append(
                {
                    "region_id": region_id,
                    "feature_key": ground_truth.LEAKAGE_TRAP_FEATURE_KEY,
                    "value_num": round(proxy, 4),
                    "value_json": None,
                    "valid_from": f"{period}-01",
                    "valid_to": None,
                    "source_id": source_id,
                    "ingested_at": ingested_at,
                    "_is_leakage_trap": True,
                }
            )
    return rows


def attach_derived_from_demand(
    feature_rows: list[dict], demand_rows: list[dict], source_ids: dict[str, str]
) -> list[dict]:
    """Build spend_index_by_node / store_count_by_node rows from demand_signal.

    03_region_features.json: "spend_index_by_node: ... demand_signal에서 파생."
    Rather than generate these independently (and risk contradicting
    demand_signal), derive them straight from it so the two data products
    agree by construction.
    """
    by_region_period: dict[tuple, dict[str, dict]] = {}
    for d in demand_rows:
        key = (d["region_id"], d["period"])
        bucket = by_region_period.setdefault(key, {"spend_index_by_node": {}, "store_count_by_node": {}})
        node_id = d["taxonomy_node_id"]
        # spend_index is identical across a node's channels for the same
        # (region, period) in this generator - only suppression varies by
        # channel. Prefer a real value over a suppressed-channel None so one
        # suppressed channel doesn't clobber a value another channel gave us;
        # if every channel is suppressed it correctly stays null (never 0).
        if d["spend_index"] is not None:
            bucket["spend_index_by_node"][node_id] = d["spend_index"]
        else:
            bucket["spend_index_by_node"].setdefault(node_id, None)
        if d["coverage_flag"] != "suppressed" and d["store_count"] is not None:
            bucket["store_count_by_node"][node_id] = d["store_count"]

    ingested_at = feature_rows[-1]["ingested_at"] if feature_rows else "2026-08-01T00:00:00Z"
    new_rows = []
    for (region_id, period), bucket in by_region_period.items():
        valid_from = f"{period}-01"
        new_rows.append(
            {
                "region_id": region_id,
                "feature_key": "spend_index_by_node",
                "value_num": None,
                "value_json": bucket["spend_index_by_node"],
                "valid_from": valid_from,
                "valid_to": None,
                "source_id": source_ids["default"],
                "ingested_at": ingested_at,
            }
        )
        new_rows.append(
            {
                "region_id": region_id,
                "feature_key": "store_count_by_node",
                "value_num": None,
                "value_json": bucket["store_count_by_node"],
                "valid_from": valid_from,
                "valid_to": None,
                "source_id": source_ids["default"],
                "ingested_at": ingested_at,
            }
        )
    _chain_valid_to(new_rows, only_key="spend_index_by_node")
    _chain_valid_to(new_rows, only_key="store_count_by_node")
    return feature_rows + new_rows
