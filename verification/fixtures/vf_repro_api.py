"""05_scoring_spec.md 8 item 7 - same run_id re-read must be byte-identical (C side)."""
import hashlib, os, sys
from pathlib import Path
BE = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BE)); os.chdir(BE)
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app); A = {"Authorization": "Bearer tnt_demo"}
for path in ("/v1/predictions/run_demo01/scores", "/v1/predictions/run_demo01/regions"):
    digests = {hashlib.sha256(c.get(path, headers=A).content).hexdigest() for _ in range(5)}
    print(f"{path:<42} 5x -> {len(digests)} distinct body hash(es)  {'IDENTICAL' if len(digests)==1 else 'DIFFERS'}")
# basemap manifest carries a time-based signature
d = {hashlib.sha256(c.get("/v1/basemap/regions/manifest?level=adm_dong", headers=A).content).hexdigest() for _ in range(5)}
print(f"{'/v1/basemap/regions/manifest (adm_dong)':<42} 5x -> {len(d)} distinct body hash(es)  {'IDENTICAL' if len(d)==1 else 'DIFFERS (signed url)'}")
