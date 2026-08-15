"""VF 5.6d - boundary_vintage / level agreement between A (real artifacts)
and C (basemap registry). ADR-001 D-08."""
import json, os, sys
from pathlib import Path
R = Path(__file__).resolve().parents[2]
BE = R / "backend"
sys.path.insert(0, str(BE)); os.chdir(BE)
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app); A = {"Authorization": "Bearer tnt_demo"}

a_man = json.loads((R / "data-platform/output/tiles/manifest.json").read_text(encoding="utf-8"))
print("A (data-platform) actually publishes:")
for lvl, meta in a_man["levels"].items():
    print(f"  level={lvl:<10} vintages={sorted(meta['vintages'])}  latest={meta['latest_vintage']}")

print("\nC (backend) advertises:")
for lvl in ("sido", "sigungu", "adm_dong"):
    r = c.get(f"/v1/basemap/regions/manifest?level={lvl}", headers=A)
    j = r.json()
    print(f"  level={lvl:<10} vintages={j.get('available_vintages')}  latest={j.get('boundary_vintage')}")

print("\nCross-check — ask C for each vintage A really built:")
for lvl, meta in a_man["levels"].items():
    for v in sorted(meta["vintages"]):
        r = c.get(f"/v1/basemap/regions/manifest?level={lvl}&vintage={v}", headers=A)
        code = r.json().get("error", {}).get("code", "") if r.status_code != 200 else "OK"
        print(f"  C.get(level={lvl}, vintage={v}) -> {r.status_code} {code}")

print("\nCross-check — ask A for each vintage C advertises (level=sido):")
r = c.get("/v1/basemap/regions/manifest?level=sido", headers=A)
for v in r.json().get("available_vintages", []):
    exists = v in a_man["levels"].get("sido", {}).get("vintages", {})
    print(f"  C advertises sido/{v} -> A has it? {exists}")

print("\nzoom range, sido:")
print(f"  A manifest : minzoom={a_man['levels']['sido']['vintages']['2026-01-01']['minzoom']} maxzoom={a_man['levels']['sido']['vintages']['2026-01-01']['maxzoom']}")
print(f"  C response : minzoom={r.json()['minzoom']} maxzoom={r.json()['maxzoom']}")
