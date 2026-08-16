"""DISPATCH-2 C-4: every error envelope carries request_id
(04_api_contract.yaml components.responses.BadRequest / schemas.Error:
required: [code, message, request_id]), and every authenticated request
gets an audit log line naming the actor (06_governance.md §4)."""
import logging

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer tnt_audit_test"}


def test_404_error_envelope_has_request_id() -> None:
    resp = client.get("/v1/predictions/run_nope/regions", headers=AUTH)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["request_id"]
    assert resp.headers["x-request-id"] == body["error"]["request_id"]


def test_401_error_envelope_has_request_id() -> None:
    resp = client.get("/v1/predictions/run_nope/regions")
    assert resp.status_code == 401
    assert resp.json()["error"]["request_id"]


def test_422_validation_error_envelope_has_request_id() -> None:
    resp = client.post(
        "/v1/predictions", json={"product_ids": [], "objective": "distribution_push"}, headers=AUTH
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["request_id"]


def test_two_requests_get_different_request_ids() -> None:
    a = client.get("/v1/predictions/run_nope/regions", headers=AUTH)
    b = client.get("/v1/predictions/run_nope/regions", headers=AUTH)
    assert a.json()["error"]["request_id"] != b.json()["error"]["request_id"]


_DEMO_AUTH = {"Authorization": "Bearer tnt_demo"}  # run_demo01's real owner


def test_successful_response_also_carries_x_request_id_header() -> None:
    resp = client.get("/v1/predictions/run_demo01/regions", headers=_DEMO_AUTH)
    assert resp.status_code == 200
    assert resp.headers["x-request-id"]


def test_authenticated_request_emits_an_actor_audit_line(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="sellfinder.audit"):
        client.get("/v1/predictions/run_demo01/regions", headers=_DEMO_AUTH)
    assert "tenant_id=tnt_demo" in caplog.text
    assert "actor" in caplog.text


def test_every_request_emits_a_request_level_audit_line(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="sellfinder.audit"):
        client.get("/v1/predictions/run_demo01/regions", headers=_DEMO_AUTH)
    assert "method=GET" in caplog.text
    assert "path=/v1/predictions/run_demo01/regions" in caplog.text
