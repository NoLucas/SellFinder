"""DISPATCH-2 §1: "이음매는 만든 사람이 아니라 이음매 자체가 테스트를 가진다."
VF-003 happened because A and D were each individually correct but nobody
tested the join between them until a verification round caught it by hand.
B<->C is the same shape of risk (BRIEF-B 해소2 / DISPATCH-2 C-2) - this test
calls B's real predict_batch directly (ground truth), drives the exact same
request through C's job worker + HTTP layer, and asserts the two agree.
If C ever swaps back to a fake/hardcoded job body, this fails."""
import time

from fastapi.testclient import TestClient

from app.main import app
from app.services import intelligence_client, job_runner, prediction_store

client = TestClient(app)
AUTH = {"Authorization": "Bearer tnt_seam_test"}


def test_predict_batch_ground_truth_is_not_degenerate() -> None:
    """Sanity check on the seam test's own premise: the candidate region
    set must actually produce differentiated scores, or "the pipeline
    returns B's real values" would be trivially true even for a broken
    pipeline (everything neutral 1.0 either way)."""
    region_ids = intelligence_client.region_ids_for_level("adm_dong")
    results = intelligence_client.run_prediction(region_ids, data_tier="T1")
    multipliers = {r.total_multiplier for r in results}
    assert len(multipliers) > 1, "candidate regions all scored identically - test would be meaningless"


def test_scores_response_matches_predict_batch_ranking() -> None:
    region_level = "adm_dong"
    data_tier = "T1"

    # Ground truth: call B directly, the same way job_runner does.
    region_ids = intelligence_client.region_ids_for_level(region_level)
    ground_truth = intelligence_client.run_prediction(region_ids, data_tier=data_tier)
    ground_truth.sort(key=lambda r: r.total_multiplier, reverse=True)
    expected_order = [r.region_id for r in ground_truth]

    # Drive the exact same request through the real HTTP + job worker path.
    resp = client.post(
        "/v1/predictions",
        json={
            "product_ids": ["prd_seam_test"],
            "objective": "distribution_push",
            "region_level": region_level,
        },
        headers=AUTH,
    )
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    deadline = time.monotonic() + job_runner._FAKE_JOB_DELAY_SECONDS * 10
    run = prediction_store.get_run(run_id, "tnt_seam_test")
    while run.status == "queued" and time.monotonic() < deadline:
        time.sleep(0.02)
        run = prediction_store.get_run(run_id, "tnt_seam_test")
    assert run.status == "succeeded", f"job did not complete in time: {run.status}"

    scores_resp = client.get(f"/v1/predictions/{run_id}/scores", headers=AUTH)
    assert scores_resp.status_code == 200
    actual_order = [row[0] for row in scores_resp.json()["scores"]]

    # The seam: /scores' ranking must be B's real ranking, not a
    # coincidence or a fake table that happens to have the same length.
    assert actual_order == expected_order
    assert set(actual_order) == set(intelligence_client.region_ids_for_level(region_level))
