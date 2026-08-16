"""VF-010: 06_governance.md §2.3 requires a suppressed demand_signal cell's
raw value stay out of the API response, the log, and any error message —
all three, not just one (VF-005 already showed what happens when only one
of two required checks lands: T0 money was blocked, T0 confidence wasn't).

Nothing in /backend consumes a real demand_signal feed yet (B's
coverage_flag -> API interface is still open, RECONCILIATION.md). These
tests build the smallest real scenario the current code can carry a
coverage_flag through — a region on a prediction_run — so the guard is
exercised through the actual response-serialization path, not just as an
isolated unit."""
import logging

from fastapi.testclient import TestClient

from app.main import app
from app.services import prediction_store, privacy

client = TestClient(app)
AUTH = {"Authorization": "Bearer tnt_privacy"}

RAW_SUPPRESSED_VALUE = 918273645  # distinctive marker: must never surface anywhere

_SUPPRESSED_REGION = prediction_store.RegionScore(
    region_id="11290",
    region_name="서울특별시 성북구",
    rank=1,
    opportunity_score=70.0,
    score_percentile=0.7,
    expected_revenue_p10=RAW_SUPPRESSED_VALUE - 1000,
    expected_revenue_p50=RAW_SUPPRESSED_VALUE,
    expected_revenue_p90=RAW_SUPPRESSED_VALUE + 1000,
    confidence_level="medium",
    data_coverage=0.6,
    coverage_flag="suppressed",
)
_NORMAL_REGION = prediction_store.RegionScore(
    region_id="11305",
    region_name="서울특별시 강북구",
    rank=2,
    opportunity_score=55.0,
    score_percentile=0.5,
    expected_revenue_p10=10_000_000,
    expected_revenue_p50=20_000_000,
    expected_revenue_p90=30_000_000,
    confidence_level="medium",
    data_coverage=0.6,
    coverage_flag="actual",
)

prediction_store.create_run(
    "run_privacy_test",
    tenant_id="tnt_privacy",
    data_tier="T1",
    regions=[_SUPPRESSED_REGION, _NORMAL_REGION],
)


# ─────────────────── response leg ───────────────────


def test_suppressed_region_money_is_null_in_regions_response() -> None:
    resp = client.get("/v1/predictions/run_privacy_test/regions", headers=AUTH)
    assert resp.status_code == 200
    assert str(RAW_SUPPRESSED_VALUE) not in resp.text

    rows = {r["region_id"]: r for r in resp.json()["data"]}
    assert rows["11290"]["expected_revenue_krw"] is None
    # the unaffected region in the same response is untouched by the guard
    assert rows["11305"]["expected_revenue_krw"]["p50"] == 20_000_000


def test_suppressed_region_money_absent_from_scores_response() -> None:
    # /scores never carries money at all (D-07) - confirms the suppressed
    # marker doesn't leak through this surface either, for the same run.
    resp = client.get("/v1/predictions/run_privacy_test/scores", headers=AUTH)
    assert resp.status_code == 200
    assert str(RAW_SUPPRESSED_VALUE) not in resp.text


# ─────────────────── log leg ───────────────────


def test_redact_logs_the_fact_not_the_value(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="sellfinder.privacy"):
        result = privacy.redact(
            RAW_SUPPRESSED_VALUE, "suppressed", region_id="11290", field="expected_revenue_p50"
        )
    assert result is None
    assert str(RAW_SUPPRESSED_VALUE) not in caplog.text
    assert "region_id=11290" in caplog.text
    assert "field=expected_revenue_p50" in caplog.text


def test_redact_passes_through_non_suppressed_values() -> None:
    assert privacy.redact(12345, "actual", region_id="x", field="f") == 12345
    assert privacy.redact(12345, None, region_id="x", field="f") == 12345


# ─────────────────── error-message leg ───────────────────


def test_suppressed_value_error_message_never_contains_the_value() -> None:
    try:
        privacy.guard_or_raise(
            RAW_SUPPRESSED_VALUE, "suppressed", region_id="11290", field="expected_revenue_p50"
        )
        assert False, "expected SuppressedValueError"
    except privacy.SuppressedValueError as exc:
        assert str(RAW_SUPPRESSED_VALUE) not in str(exc)
        assert exc.region_id == "11290"
        assert exc.field == "expected_revenue_p50"


def test_guard_or_raise_passes_through_non_suppressed_values() -> None:
    assert privacy.guard_or_raise(999, "actual", region_id="x", field="f") == 999


def test_unhandled_exception_never_echoes_str_exc(monkeypatch) -> None:
    """End-to-end: if some future call site raised SuppressedValueError (or
    any other exception) without catching it, app.main's generic handler
    must still not leak str(exc) to the client. Simulates that by making
    the /regions handler itself raise mid-request."""

    def _boom(*args, **kwargs):
        raise privacy.SuppressedValueError(
            region_id="11290", field="expected_revenue_p50"
        ) from None

    monkeypatch.setattr(prediction_store, "get_run", _boom)
    # TestClient's default raise_server_exceptions=True re-raises to the
    # test even after a registered handler builds a response (it's meant to
    # surface bugs during development) - use a client that behaves like a
    # real deployed server so this actually exercises app.main's handler.
    unraising_client = TestClient(app, raise_server_exceptions=False)
    resp = unraising_client.get("/v1/predictions/run_privacy_test/regions", headers=AUTH)
    assert resp.status_code == 500
    assert "11290" not in resp.text  # region_id from the exception must not leak either
    body = resp.json()
    assert body["error"]["code"] == "internal_error"
    assert "suppressed" not in body["error"]["message"].lower()
