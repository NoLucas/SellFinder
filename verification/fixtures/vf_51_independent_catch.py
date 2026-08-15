"""VF 5.1c - proves the gap is closable: an INDEPENDENT check (log_contribution
vs the factor's own value/benchmark, which is NOT derived from the sum) catches
M2, which the agent's own suite let through."""
import math, os, sys
INTEL = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "intelligence"))
sys.path.insert(0, INTEL)
from scoring import factors as F

MUT = len(sys.argv) > 1 and sys.argv[1] == "M2"
_orig = F.FactorResult.__post_init__
if MUT:
    def patched(self):
        _orig(self)
        if self.key == "price_acceptance":
            object.__setattr__(self, "log_contribution", self.log_contribution * 0.5)
    F.FactorResult.__post_init__ = patched

from scoring import model
from scoring.feature_store import SyntheticFeatureStore
from synthetic import generate

ds = generate.generate_all(seed=42, start_period="2025-01", end_period="2026-06")
store = SyntheticFeatureStore.from_dataset(ds)
res = model.predict_batch(
    region_ids=store.all_adm_dong_ids(), taxonomy_node_id="TX-FOOD-BEV-COFFEE-RTD",
    channel="cvs", period="2025-06", as_of="2025-06-01", data_tier="T0", store=store,
    product_attributes={"target_age": ["20s","30s"]}, price_tier="premium",
    seasonality_profile=[0.92,0.90,0.98,1.02,1.08,1.14,1.18,1.16,1.04,0.96,0.92,0.90],
    horizon_months=1,
)
# tautological check (what the agent's test does)
taut = max(abs(math.fsum(f["log_contribution"] for f in r.to_dict()["factors"])
               - math.log(r.total_multiplier)) for r in res)
# independent check: display_effect is computed from the REAL multiplier, so it
# is an outside witness of what log_contribution should have been
indep = 0.0
for r in res:
    for f in r.to_dict()["factors"]:
        shown = float(f["display_effect"].rstrip("%")) / 100 + 1.0
        indep = max(indep, abs(math.exp(f["log_contribution"]) - shown))
print(f"mutation applied      : {MUT}")
print(f"tautological check    : worst dev = {taut:.3e}  -> {'FAIL' if taut>=1e-6 else 'pass'}")
print(f"independent check     : worst dev = {indep:.3e}  -> {'FAIL' if indep>=0.01 else 'pass'}")
