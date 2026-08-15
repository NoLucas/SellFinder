import os, sys, json
BE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, BE); os.chdir(BE)
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
A = {"Authorization": "Bearer tnt_demo"}

for q, hdr in [("level=sido", A), ("level=adm_dong", A), ("level=adm_dong&tenant_id=tnt_other", A),
               ("level=adm_dong", {**A, "X-Tenant-Id": "tnt_other"}), ("level=adm_dong", {})]:
    r = c.get(f"/v1/basemap/regions/manifest?{q}", headers=hdr)
    cc = r.headers.get("cache-control")
    url = (r.json().get("tile_url") if r.status_code == 200 else "-")
    signed = "sig=" in (url or "")
    print(f"{q:<42} auth={'yes' if hdr.get('Authorization') else 'NO ':<3} -> {r.status_code}  Cache-Control={cc}  signed={signed}")
    if r.status_code == 200 and signed:
        print(f"    tile_url = {url}")
