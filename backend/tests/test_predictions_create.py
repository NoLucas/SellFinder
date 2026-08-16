"""DISPATCH-2 C-1: POST /v1/predictions must return 202 without waiting for
the prediction job to finish. 00_product_spec.md Anti-goals explicitly bans
synchronous prediction APIs. This is enforced by wall-clock timing against
app.services.job_runner's deliberate delay - reading the code isn't enough,
since a handler could call the job function directly (not via a thread) and
still "look" async while actually blocking."""
import time

from fastapi.testclient import TestClient

from app.main import app
from app.services import job_runner, prediction_store

client = TestClient(app)
AUTH = {"Authorization": "Bearer tnt_create_test"}

_REQUEST_BODY = {
    "product_ids": ["prd_test01"],
    "objective": "distribution_push",
    "region_level": "sigungu",
}


def test_create_prediction_returns_202_immediately() -> None:
    started = time.monotonic()
    resp = client.post("/v1/predictions", json=_REQUEST_BODY, headers=AUTH)
    elapsed = time.monotonic() - started

    assert resp.status_code == 202
    # the fake job body sleeps for job_runner._FAKE_JOB_DELAY_SECONDS - the
    # HTTP response must come back in a small fraction of that.
    assert elapsed < job_runner._FAKE_JOB_DELAY_SECONDS / 2

    body = resp.json()
    assert body["status"] == "queued"
    assert body["run_id"].startswith("run_")
    assert body["data_tier"] == "T1"


def test_run_is_still_queued_right_after_the_response_comes_back() -> None:
    """Direct proof at the store layer, not just response timing: the run
    the handler just created must not have regions yet the instant control
    returns to the caller."""
    resp = client.post("/v1/predictions", json=_REQUEST_BODY, headers=AUTH)
    run_id = resp.json()["run_id"]

    run = prediction_store.get_run(run_id, "tnt_create_test")
    assert run is not None
    assert run.status == "queued"
    assert run.regions == []


def test_run_eventually_completes_and_regions_become_available() -> None:
    resp = client.post("/v1/predictions", json=_REQUEST_BODY, headers=AUTH)
    run_id = resp.json()["run_id"]

    deadline = time.monotonic() + job_runner._FAKE_JOB_DELAY_SECONDS * 5
    run = prediction_store.get_run(run_id, "tnt_create_test")
    while run.status == "queued" and time.monotonic() < deadline:
        time.sleep(0.02)
        run = prediction_store.get_run(run_id, "tnt_create_test")

    assert run.status == "succeeded"
    assert len(run.regions) > 0

    # seam test (DISPATCH-2 §1): the job's output must actually reach
    # /scores in the real response shape, not just sit in the store.
    scores_resp = client.get(f"/v1/predictions/{run_id}/scores", headers=AUTH)
    assert scores_resp.status_code == 200
    scores_body = scores_resp.json()
    assert scores_body["schema"] == ["region_id", "opportunity_score", "confidence_level"]
    assert len(scores_body["scores"]) == len(run.regions)


def test_create_prediction_requires_auth() -> None:
    resp = client.post("/v1/predictions", json=_REQUEST_BODY)
    assert resp.status_code == 401


def test_create_prediction_rejects_invalid_objective() -> None:
    resp = client.post(
        "/v1/predictions",
        json={**_REQUEST_BODY, "objective": "not_a_real_objective"},
        headers=AUTH,
    )
    assert resp.status_code == 422


def test_create_prediction_rejects_empty_product_ids() -> None:
    resp = client.post(
        "/v1/predictions", json={**_REQUEST_BODY, "product_ids": []}, headers=AUTH
    )
    assert resp.status_code == 422


def test_create_prediction_rejects_tenant_id_injection() -> None:
    resp = client.post(
        "/v1/predictions?tenant_id=tnt_other", json=_REQUEST_BODY, headers=AUTH
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TENANT_ID_NOT_ALLOWED"


def test_idempotency_key_reuses_the_same_run() -> None:
    key = "idem-key-001"
    first = client.post(
        "/v1/predictions", json=_REQUEST_BODY, headers={**AUTH, "Idempotency-Key": key}
    )
    second = client.post(
        "/v1/predictions", json=_REQUEST_BODY, headers={**AUTH, "Idempotency-Key": key}
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]


def test_idempotency_key_is_scoped_per_tenant() -> None:
    key = "idem-key-shared"
    a = client.post(
        "/v1/predictions", json=_REQUEST_BODY, headers={**AUTH, "Idempotency-Key": key}
    )
    b = client.post(
        "/v1/predictions",
        json=_REQUEST_BODY,
        headers={"Authorization": "Bearer tnt_other_idem", "Idempotency-Key": key},
    )
    assert a.json()["run_id"] != b.json()["run_id"]


def test_without_idempotency_key_each_request_makes_a_new_run() -> None:
    a = client.post("/v1/predictions", json=_REQUEST_BODY, headers=AUTH)
    b = client.post("/v1/predictions", json=_REQUEST_BODY, headers=AUTH)
    assert a.json()["run_id"] != b.json()["run_id"]
