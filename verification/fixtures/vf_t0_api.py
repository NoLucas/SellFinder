"""D-03 / 05_scoring_spec 2,8-2 on the API side: no backend test ever creates a
T0 run (prediction_store.py:106 seeds only data_tier='T1'), so the T0 branch at
routers/predictions.py:83 is never exercised. Create one and drive it."""
import os, sys, json
from pathlib import Path
BE = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BE)); os.chdir(BE)
from fastapi.testclient import TestClient
from app.main import app
from app.services import prediction_store

prediction_store.create_run("run_t0probe", tenant_id="tnt_demo", data_tier="T0")
c = TestClient(app); A = {"Authorization": "Bearer tnt_demo"}

r = c.get("/v1/predictions/run_t0probe/regions", headers=A)
rows = r.json()["data"]
print(f"GET /regions (T0) -> {r.status_code}, {len(rows)} rows")
bad = [x for x in rows if x.get("expected_revenue_krw") is not None]
print(f"  rows with non-null expected_revenue_krw : {len(bad)}   (contract: must be 0)")
print(f"  sample row: {json.dumps(rows[0], ensure_ascii=False)[:160]}")

r2 = c.get("/v1/predictions/run_t0probe/scores", headers=A)
b2 = r2.json()
print(f"GET /scores  (T0) -> {r2.status_code}  data_tier={b2['data_tier']}  revenue field present={'expected_revenue_krw' in json.dumps(b2)}")

# and the T1 baseline for contrast
r3 = c.get("/v1/predictions/run_demo01/regions", headers=A)
n = sum(1 for x in r3.json()["data"] if x.get("expected_revenue_krw") is not None)
print(f"GET /regions (T1 baseline) -> rows with revenue: {n}")

print("\n--- 05_scoring_spec 2: T0 confidence.level ceiling is 'medium' ---")
lv = [x["confidence"]["level"] for x in c.get("/v1/predictions/run_t0probe/regions", headers=A).json()["data"]]
print(f"  /regions (T0) confidence levels : {lv}")
print(f"  above ceiling (=='high')        : {lv.count('high')}   (contract: must be 0)")
sc = [row[2] for row in c.get("/v1/predictions/run_t0probe/scores", headers=A).json()["scores"]]
print(f"  /scores  (T0) confidence levels : {sc}")
print(f"  above ceiling (=='high')        : {sc.count('high')}   (contract: must be 0)")
