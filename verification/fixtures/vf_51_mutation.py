"""VF 5.1b - mutation test: does intelligence/tests actually CATCH a broken
factor decomposition? Injects faults at runtime (no agent file is modified)
and re-runs the agent's own test suite against the mutated module.

M1 round log_contribution to 2dp  -> factors no longer sum to the true log
M2 corrupt one factor's log_contribution (x0.5) -> decomposition is a lie
M3 drop the last factor from to_dict() output -> user sees 7 of 8 factors
"""
import io, math, os, sys, unittest

INTEL = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "intelligence"))
sys.path.insert(0, INTEL)

MUT = sys.argv[1]

from scoring import factors as F
from scoring import model as M

_orig_post = F.FactorResult.__post_init__
_orig_todict = F.FactorResult.to_dict

if MUT == "M1":
    def patched(self):
        _orig_post(self)
        object.__setattr__(self, "log_contribution", round(self.log_contribution, 2))
    F.FactorResult.__post_init__ = patched

elif MUT == "M2":
    def patched(self):
        _orig_post(self)
        if self.key == "price_acceptance":
            object.__setattr__(self, "log_contribution", self.log_contribution * 0.5)
    F.FactorResult.__post_init__ = patched

elif MUT == "M3":
    _orig_predict = M.predict_one
    def patched_predict(*a, **k):
        r = _orig_predict(*a, **k)
        r.factors = r.factors[:-1]      # drop tenant_calibration from the output
        return r
    M.predict_one = patched_predict

sys.path.insert(0, os.path.join(INTEL, "tests"))
import test_factor_model

suite = unittest.TestLoader().loadTestsFromModule(test_factor_model)
buf = io.StringIO()
res = unittest.TextTestRunner(stream=buf, verbosity=0).run(suite)
print(f"[{MUT}] ran={res.testsRun} failures={len(res.failures)} errors={len(res.errors)}")
for t, _ in res.failures + res.errors:
    print("   CAUGHT BY:", t.id().split(".")[-1])
if not res.failures and not res.errors:
    print("   *** MUTANT SURVIVED - no test detected the broken decomposition ***")
