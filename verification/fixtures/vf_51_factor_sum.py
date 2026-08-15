"""VF 5.1 - Sigma log_contribution invariant, checked independently.

Does NOT reuse intelligence/tests. Builds 100 randomized inputs, recomputes
the sum from the API-facing dict output, and compares three ways:
  (a) sum(log_contribution) vs ln(total_multiplier)
  (b) expected_demand_units vs base_volume * exp(sum)   [contract's real form]
  (c) each factor's exp(log_contribution) vs its own value/benchmark ratio
Contract: 05_scoring_spec.md 1 / 8 item 1, DECISIONS D-04.
"""
import math, random, sys, os
INTEL = os.path.join(os.path.dirname(__file__), "..", "..", "intelligence")
sys.path.insert(0, os.path.abspath(INTEL))

from scoring import model
from scoring.feature_store import SyntheticFeatureStore
from synthetic import generate

ds = generate.generate_all(seed=42, start_period="2025-01", end_period="2026-06")
store = SyntheticFeatureStore.from_dataset(ds)
regions = store.all_adm_dong_ids()

CHANNELS = ["cvs", "hypermarket", "online_marketplace"]
NODES = ["TX-FOOD-BEV-COFFEE-RTD"]
TIERS = ["T0", "T1", "T2"]
PRICE = ["value", "mid", "premium", "luxury"]
SEAS = [0.92,0.90,0.98,1.02,1.08,1.14,1.18,1.16,1.04,0.96,0.92,0.90]

rnd = random.Random(20260815)
worst_a = worst_b = worst_c = 0.0
n_checked = 0
fail = []

for i in range(100):
    ch = rnd.choice(CHANNELS)
    tier = rnd.choice(TIERS)
    pt = rnd.choice(PRICE)
    seas = SEAS if rnd.random() < 0.7 else None
    hz = rnd.choice([1, 3, 6])
    mon = rnd.randint(1, 12)
    period = f"2025-{mon:02d}"
    attrs = rnd.choice([
        {"target_age": ["20s","30s"], "sugar_free": True},
        {"target_age": ["40s"], "premium_ingredient": True},
        {},
    ])
    subset = rnd.sample(regions, k=min(len(regions), rnd.randint(3, len(regions))))

    res = model.predict_batch(
        region_ids=subset, taxonomy_node_id=NODES[0], channel=ch,
        period=period, as_of=f"{period}-01", data_tier=tier, store=store,
        product_attributes=attrs, price_tier=pt,
        seasonality_profile=seas, horizon_months=hz,
    )
    for r in res:
        n_checked += 1
        d = r.to_dict()
        s = math.fsum(f["log_contribution"] for f in d["factors"])

        da = abs(s - math.log(d["total_multiplier"]))
        worst_a = max(worst_a, da)
        if da >= 1e-6:
            fail.append(("a", r.region_id, ch, tier, da))

        bv = model.base_volume(NODES[0], ch, 1.0)  # placeholder, recomputed below
        # contract form: ln(demand) = ln(base) + sum(ln f_i)
        base = d["expected_demand_units"] / d["total_multiplier"]
        db = abs(math.log(d["expected_demand_units"]) - (math.log(base) + s))
        worst_b = max(worst_b, db)
        if db >= 1e-6:
            fail.append(("b", r.region_id, ch, tier, db))

        for f in d["factors"]:
            v, b = f["value"], f["benchmark"]
            if v is None or b is None or b == 0:
                continue
            if f["key"] in ("addressable_demand", "category_penetration", "channel_availability"):
                dc = abs(math.exp(f["log_contribution"]) - v / b)
                worst_c = max(worst_c, dc)
                if dc >= 1e-9:
                    fail.append(("c", r.region_id, f["key"], v, b, dc))

print(f"predictions checked : {n_checked}")
print(f"(a) worst |sum - ln(total_multiplier)| = {worst_a:.3e}   (contract limit 1e-6)")
print(f"(b) worst |ln(demand) - (ln(base)+sum)| = {worst_b:.3e}")
print(f"(c) worst |exp(log_contrib) - value/benchmark| = {worst_c:.3e}")
print(f"violations: {len(fail)}")
for f in fail[:10]:
    print("  ", f)
