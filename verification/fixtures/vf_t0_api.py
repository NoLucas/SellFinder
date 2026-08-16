"""D-03 / 05_scoring_spec 2,8-2 on the API side: no backend test ever creates a
T0 run (prediction_store.py:106 seeds only data_tier='T1'), so the T0 branch at
routers/predictions.py:83 is never exercised. Create one and drive it.

--strict (added round 6, for CI 8e047fe): without it this is a diagnostic
printer that always exits 0, same as every other verification/fixtures/
script - a human or CI reads the printed numbers. CI was grepping those
numbers out of stdout to decide pass/fail, which breaks silently if this
script's wording ever changes. --strict makes the same checks explicit
assertions and exits 1 on the first violation, so CI can check the exit
code instead of parsing text. Default behavior (no flag) is unchanged.

Round 7 addition - the first scenario below (run_t0probe via plain
create_run(), which goes through the real compute_regions()/predict_batch
pipeline) is currently VACUOUS as a regression check: confidence_level is
hardcoded "low" in prediction_store.compute_regions() (confidence scoring
isn't built yet - Step 4/5) and expected_revenue_krw is None for every
tier today (Step 5 not built), so removing the T0 clamp/redact code
entirely still prints "0 violations" here - there is nothing in the real
pipeline's output that WOULD exceed the ceiling or carry a value to null
out. Confirmed by directly reverting _confidence_for_tier and the T0
early-return in routers/predictions.py in an isolated worktree and rerunning
this exact scenario: still 0/0, false green (verification round 7).
A second scenario below explicitly seeds a region (bypassing
compute_regions() via create_run(..., regions=[...])) with
confidence_level='high' and non-null revenue, so the clamp/redact code
itself is exercised regardless of whether today's pipeline can produce
that input yet. Keep both: the first documents what the live pipeline
currently does, the second is what actually guards the invariant."""
import argparse
import os
import sys
import json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--strict", action="store_true", help="exit 1 on any violation instead of just printing")
args = ap.parse_args()

BE = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BE)); os.chdir(BE)
from fastapi.testclient import TestClient
from app.main import app
from app.services import prediction_store

violations: list[str] = []

prediction_store.create_run("run_t0probe", tenant_id="tnt_demo", data_tier="T0")
c = TestClient(app); A = {"Authorization": "Bearer tnt_demo"}

r = c.get("/v1/predictions/run_t0probe/regions", headers=A)
rows = r.json()["data"]
print(f"GET /regions (T0) -> {r.status_code}, {len(rows)} rows")
bad = [x for x in rows if x.get("expected_revenue_krw") is not None]
print(f"  rows with non-null expected_revenue_krw : {len(bad)}   (contract: must be 0)")
print(f"  sample row: {json.dumps(rows[0], ensure_ascii=False)[:160]}")
if bad:
    violations.append(f"T0 /regions returned {len(bad)} row(s) with non-null expected_revenue_krw (D-03)")

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
if lv.count("high") > 0:
    violations.append(f"T0 /regions returned {lv.count('high')} row(s) with confidence.level=='high' (05_scoring_spec.md §2 ceiling is medium)")

sc = [row[2] for row in c.get("/v1/predictions/run_t0probe/scores", headers=A).json()["scores"]]
print(f"  /scores  (T0) confidence levels : {sc}")
print(f"  above ceiling (=='high')        : {sc.count('high')}   (contract: must be 0)")
if sc.count("high") > 0:
    violations.append(f"T0 /scores returned {sc.count('high')} row(s) with confidence_level=='high' (05_scoring_spec.md §2 ceiling is medium)")

print("\n--- explicit-seed scenario (round 7): exercises the clamp/redact code")
print("    directly, independent of whether compute_regions() can produce a")
print("    high-confidence / non-null-revenue row yet ---")
seeded_region = prediction_store.RegionScore(
    region_id="99001001",
    region_name="explicit-seed",
    rank=1,
    opportunity_score=99.0,
    score_percentile=0.99,
    expected_revenue_p10=100_000_000,
    expected_revenue_p50=200_000_000,
    expected_revenue_p90=300_000_000,
    confidence_level="high",
    data_coverage=0.95,
    coverage_flag="actual",
)
prediction_store.create_run(
    "run_t0probe_seeded", tenant_id="tnt_demo", data_tier="T0", regions=[seeded_region]
)
seeded_rows = c.get("/v1/predictions/run_t0probe_seeded/regions", headers=A).json()["data"]
seeded_row = seeded_rows[0]
print(f"  seeded row: {json.dumps(seeded_row, ensure_ascii=False)}")
if seeded_row.get("expected_revenue_krw") is not None:
    violations.append(
        "T0 /regions (explicit-seed) returned non-null expected_revenue_krw for a region "
        "whose raw store value was non-null (D-03) - the clamp code itself is broken, "
        "not just untested"
    )
if seeded_row["confidence"]["level"] == "high":
    violations.append(
        "T0 /regions (explicit-seed) returned confidence.level=='high' for a region whose "
        "raw store value was 'high' (05_scoring_spec.md §2 ceiling is medium) - the clamp "
        "code itself is broken, not just untested"
    )
seeded_scores = c.get("/v1/predictions/run_t0probe_seeded/scores", headers=A).json()["scores"]
seeded_score_conf = seeded_scores[0][2]
print(f"  seeded /scores confidence_level: {seeded_score_conf!r}")
if seeded_score_conf == "high":
    violations.append(
        "T0 /scores (explicit-seed) returned confidence_level=='high' for a region whose raw "
        "store value was 'high' - the clamp code itself is broken, not just untested"
    )

if args.strict:
    if violations:
        print(f"\nSTRICT: {len(violations)} violation(s):")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)
    print("\nSTRICT: no violations")
    sys.exit(0)
