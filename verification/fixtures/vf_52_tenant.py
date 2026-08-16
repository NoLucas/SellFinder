"""VF 5.2 - tenant_id must never be accepted from query/body/header.
Contract: 06_governance.md 1.1 -> 400 TENANT_ID_NOT_ALLOWED.

--strict (added round 6, for CI 8e047fe): without it this is a diagnostic
printer that always exits 0, same as every other verification/fixtures/
script. --strict tracks which probes are actual injection attempts (expect
400) versus baseline/other probes, and exits 1 if any injection probe did
not get 400 - CI can check the exit code instead of grepping printed
lines for 'tenant' + '-> 200', which was one output-format change away
from silently stopping to catch anything. Default behavior unchanged."""
import argparse
import os
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--strict", action="store_true", help="exit 1 on any violation instead of just printing")
args = ap.parse_args()

BE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, BE)
os.chdir(BE)
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
A = {"Authorization": "Bearer tnt_demo"}      # owns run_demo01
B = {"Authorization": "Bearer tnt_other"}     # owns nothing

violations: list[str] = []


def probe(name, method, url, headers=None, expect_rejection=False, **kw):
    r = getattr(c, method)(url, headers=headers or {}, **kw)
    body = r.text[:110].replace("\n", " ")
    print(f"{name:<52} -> {r.status_code}  {body}")
    if expect_rejection and r.status_code != 400:
        violations.append(f"{name.strip()} -> expected 400 TENANT_ID_NOT_ALLOWED, got {r.status_code}")
    return r


print("--- baseline ---")
probe("A, no injection                  /regions", "get", "/v1/predictions/run_demo01/regions", A)
probe("B, no injection (cross-tenant)   /regions", "get", "/v1/predictions/run_demo01/regions", B)
probe("no token                         /regions", "get", "/v1/predictions/run_demo01/regions")

print("\n--- 06_governance 1.1: tenant_id via QUERY (expect 400 TENANT_ID_NOT_ALLOWED) ---")
probe("A + ?tenant_id=tnt_other         /regions", "get", "/v1/predictions/run_demo01/regions?tenant_id=tnt_other", A, expect_rejection=True)
probe("A + ?tenant_id=tnt_demo          /regions", "get", "/v1/predictions/run_demo01/regions?tenant_id=tnt_demo", A, expect_rejection=True)
probe("B + ?tenant_id=tnt_demo          /regions", "get", "/v1/predictions/run_demo01/regions?tenant_id=tnt_demo", B, expect_rejection=True)
probe("A + ?tenant_id=tnt_other         /scores ", "get", "/v1/predictions/run_demo01/scores?tenant_id=tnt_other", A, expect_rejection=True)
probe("A + ?tenantId=tnt_other          /scores ", "get", "/v1/predictions/run_demo01/scores?tenantId=tnt_other", A, expect_rejection=True)

print("\n--- tenant_id via HEADER (expect 400) ---")
probe("A + X-Tenant-Id: tnt_other       /regions", "get", "/v1/predictions/run_demo01/regions", {**A, "X-Tenant-Id": "tnt_other"}, expect_rejection=True)
probe("A + Tenant-Id: tnt_other         /scores ", "get", "/v1/predictions/run_demo01/scores", {**A, "Tenant-Id": "tnt_other"}, expect_rejection=True)

print("\n--- basemap endpoints ---")
# Note: this hits /v1/basemap/manifest, not the real /v1/basemap/regions/manifest
# route - it 404s regardless of the tenant_id guard, so it's not a real
# injection probe (kept as-is for historical continuity with round 1/2's
# findings; not counted toward --strict).
probe("A + ?tenant_id=tnt_other         /basemap", "get", "/v1/basemap/manifest?tenant_id=tnt_other", A)
probe("no token                         /basemap", "get", "/v1/basemap/manifest")

if args.strict:
    if violations:
        print(f"\nSTRICT: {len(violations)} violation(s):")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)
    print("\nSTRICT: no violations")
    sys.exit(0)
