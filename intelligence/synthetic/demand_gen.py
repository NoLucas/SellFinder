"""demand_signal generator.

Covers a curated set of 10 leaf taxonomy nodes (not all 36 - see
synthetic/README.md for why) across their plausible channels, for every
adm_dong region and period. Five of the ten nodes carry a planted
ground_truth relationship (see ground_truth.py); the other five are
plain baseline nodes with no special relationship, for contrast/realism.

Suppression follows 01_domain_model.json's demand_signal.privacy_rule:
cells with too few stores or transactions get coverage_flag='suppressed'
and transaction_count/store_count/spend_index are nulled - only the index
survives elsewhere, and even that is nulled here to stay conservative
(03_region_features.json's source_caveats + 06_governance.md both treat
this as the one rule that must never leak).

ADR-004 / DECISIONS.md D-18: card_mcc (the source spend_krw would come
from) is not licensed, so spend_krw is always null - suppressed or not.
avg_value in NODE_PARAMS stays defined (it documents what card_mcc would
give us) but nothing derives spend_krw from it right now. A generator
that quietly filled spend_krw anyway would make the model look better on
synthetic data than the real pipeline can deliver.
"""
from __future__ import annotations

import random

from . import ground_truth

# node_id -> channel_id -> share of that node's demand routed through the channel
CHANNEL_MIX: dict[str, dict[str, float]] = {
    "TX-FOOD-BEV-COFFEE-RTD": {"cvs": 0.45, "hypermarket": 0.25, "ssm": 0.15, "online_marketplace": 0.15},
    "TX-FOOD-BEV-TEA": {"cvs": 0.4, "hypermarket": 0.3, "online_marketplace": 0.3},
    "TX-FOOD-PROC-HMR": {"cvs": 0.35, "hypermarket": 0.4, "online_marketplace": 0.25},
    "TX-KIDS-BABYFOOD": {"hypermarket": 0.35, "specialty_store": 0.25, "online_marketplace": 0.4},
    "TX-ELEC-LARGE": {"hypermarket": 0.25, "specialty_store": 0.35, "online_marketplace": 0.4},
    "TX-LIVING-PET": {"specialty_store": 0.35, "hypermarket": 0.25, "online_marketplace": 0.4},
    "TX-FNB-CAFE": {"fnb_outlet": 1.0},
    "TX-FASHION-WOMEN": {"specialty_store": 0.3, "department_store": 0.25, "online_marketplace": 0.35, "own_mall": 0.1},
    "TX-BEAUTY-SKINCARE": {"specialty_store": 0.3, "department_store": 0.2, "online_marketplace": 0.4, "own_mall": 0.1},
    "TX-HEALTH-FITNESS": {"specialty_store": 0.6, "online_marketplace": 0.4},
}

# node_id -> (monthly transactions per 1,000 pop, stores per 1,000 pop, avg transaction value KRW)
NODE_PARAMS: dict[str, tuple[float, float, int]] = {
    "TX-FOOD-BEV-COFFEE-RTD": (900, 1.2, 3000),
    "TX-FOOD-BEV-TEA": (500, 0.4, 2800),
    "TX-FOOD-PROC-HMR": (650, 0.3, 7000),
    "TX-KIDS-BABYFOOD": (40, 0.05, 15000),
    "TX-ELEC-LARGE": (3, 0.02, 450000),
    "TX-LIVING-PET": (60, 0.08, 25000),
    "TX-FNB-CAFE": (1800, 0.5, 6500),
    "TX-FASHION-WOMEN": (120, 0.15, 45000),
    "TX-BEAUTY-SKINCARE": (150, 0.1, 28000),
    "TX-HEALTH-FITNESS": (25, 0.03, 60000),
}

CURATED_NODES = list(NODE_PARAMS.keys())

_DENSITY_FACTOR = {"metro": 1.3, "major_city": 1.05, "mid_city": 0.75, "rural": 0.45}
_ONLINE_CHANNELS = {"online_marketplace", "own_mall", "quick_commerce"}

# suppression thresholds per 01_domain_model.json demand_signal.privacy_rule
_MIN_STORE_COUNT = 5
_MIN_TRANSACTION_COUNT = 50


def _seasonality(node: dict, period: str) -> float:
    profile = node.get("seasonality_profile")
    if not profile:
        return 1.0
    month = int(period.split("-")[1])
    return profile[month - 1]


def generate_demand_signal_rows(
    profiles: dict[str, dict],
    taxonomy_leaves_by_id: dict[str, dict],
    periods: list[str],
    resolved_relationships: list[dict],
    rng: random.Random,
    source_id: str,
) -> list[dict]:
    rows: list[dict] = []
    for node_id in CURATED_NODES:
        node = taxonomy_leaves_by_id[node_id]
        txn_rate, store_rate, _avg_value = NODE_PARAMS[node_id]  # avg_value unused - see module docstring
        channel_mix = CHANNEL_MIX[node_id]

        for region_id, profile in profiles.items():
            pop_total = profile["pop_total"]
            density = _DENSITY_FACTOR[profile["region_type"]]
            mult = ground_truth.multiplier_for(region_id, node_id, profiles, resolved_relationships)

            for period in periods:
                season = _seasonality(node, period)
                noise = rng.uniform(0.85, 1.15)
                spend_index = round(100.0 * mult * season * noise, 2)

                for channel, share in channel_mix.items():
                    channel_noise = rng.uniform(0.9, 1.1)
                    transaction_count = round(
                        (pop_total / 1000) * txn_rate * share * (spend_index / 100) * channel_noise
                    )
                    transaction_count = max(0, transaction_count)

                    if channel in _ONLINE_CHANNELS:
                        store_count = None  # not a meaningful concept online; see channel_rules
                    else:
                        store_count = round((pop_total / 1000) * store_rate * share * density * rng.uniform(0.85, 1.15))
                        store_count = max(0, store_count)

                    suppressed = transaction_count < _MIN_TRANSACTION_COUNT or (
                        store_count is not None and store_count < _MIN_STORE_COUNT
                    )
                    if suppressed:
                        coverage_flag = "suppressed"
                        out_txn = None
                        out_store = None
                        out_index = None
                    else:
                        coverage_flag = "estimated" if rng.random() < 0.15 else "actual"
                        out_txn = transaction_count
                        out_store = store_count
                        out_index = spend_index

                    rows.append(
                        {
                            "region_id": region_id,
                            "taxonomy_node_id": node_id,
                            "channel": channel,
                            "period": period,
                            # ADR-004 / D-18: card_mcc not licensed -> always null,
                            # suppressed or not. See module docstring.
                            "spend_krw": None,
                            "transaction_count": out_txn,
                            "store_count": out_store,
                            "spend_index": out_index,
                            "coverage_flag": coverage_flag,
                            "source_id": source_id,
                        }
                    )
    return rows
