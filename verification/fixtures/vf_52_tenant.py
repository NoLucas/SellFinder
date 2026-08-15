"""VF 5.2 - tenant_id must never be accepted from query/body/header.
Contract: 06_governance.md 1.1 -> 400 TENANT_ID_NOT_ALLOWED."""
import os, sys, json
BE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, BE)
os.chdir(BE)
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
A = {"Authorization": "Bearer tnt_demo"}      # owns run_demo01
B = {"Authorization": "Bearer tnt_other"}     # owns nothing

def probe(name, method, url, headers=None, **kw):
    r = getattr(c, method)(url, headers=headers or {}, **kw)
    body = r.text[:110].replace("\n", " ")
    print(f"{name:<52} -> {r.status_code}  {body}")
    return r

print("--- baseline ---")
probe("A, no injection                  /regions", "get", "/v1/predictions/run_demo01/regions", A)
probe("B, no injection (cross-tenant)   /regions", "get", "/v1/predictions/run_demo01/regions", B)
probe("no token                         /regions", "get", "/v1/predictions/run_demo01/regions")

print("\n--- 06_governance 1.1: tenant_id via QUERY (expect 400 TENANT_ID_NOT_ALLOWED) ---")
probe("A + ?tenant_id=tnt_other         /regions", "get", "/v1/predictions/run_demo01/regions?tenant_id=tnt_other", A)
probe("A + ?tenant_id=tnt_demo          /regions", "get", "/v1/predictions/run_demo01/regions?tenant_id=tnt_demo", A)
probe("B + ?tenant_id=tnt_demo          /regions", "get", "/v1/predictions/run_demo01/regions?tenant_id=tnt_demo", B)
probe("A + ?tenant_id=tnt_other         /scores ", "get", "/v1/predictions/run_demo01/scores?tenant_id=tnt_other", A)
probe("A + ?tenantId=tnt_other          /scores ", "get", "/v1/predictions/run_demo01/scores?tenantId=tnt_other", A)

print("\n--- tenant_id via HEADER (expect 400) ---")
probe("A + X-Tenant-Id: tnt_other       /regions", "get", "/v1/predictions/run_demo01/regions", {**A, "X-Tenant-Id": "tnt_other"})
probe("A + Tenant-Id: tnt_other         /scores ", "get", "/v1/predictions/run_demo01/scores", {**A, "Tenant-Id": "tnt_other"})

print("\n--- basemap endpoints ---")
probe("A + ?tenant_id=tnt_other         /basemap", "get", "/v1/basemap/manifest?tenant_id=tnt_other", A)
probe("no token                         /basemap", "get", "/v1/basemap/manifest")
