"""Suppressed-cell guard — single choke point (06_governance.md §2.3,
05_scoring_spec.md §8-6).

`demand_signal` cells below the k-anonymity threshold get
`coverage_flag='suppressed'` (01_domain_model.json). Their raw value must
never reach "API 응답, 로그, 내보내기 파일 어디에도" (06_governance.md §2.3,
verbatim). VF-005 already showed what happens when a rule like this gets
enforced in only one place: T0's expected_revenue_krw was correctly nulled,
but confidence.level wasn't, so T0 runs still leaked "high" confidence.
Don't repeat that here for the three surfaces the CHARTER names — response,
log, error message — by routing every one of them through this module
instead of letting each call site re-implement the check.

Nothing in /backend consumes a real `demand_signal` feed yet (B's
coverage_flag → API wiring is still open, see backend/RECONCILIATION.md).
This module doesn't guess that shape — it's the generic redact/guard
primitive any future call site (a region-detail endpoint, an xlsx/csv
export) plugs into, so the rule is enforced by construction instead of by
every new endpoint remembering to re-check coverage_flag.
"""

import logging

logger = logging.getLogger("sellfinder.privacy")

SUPPRESSED = "suppressed"


class SuppressedValueError(ValueError):
    """Raised in place of a normal ValueError anywhere code would otherwise
    have interpolated a suppressed cell's raw value into an exception
    message. __str__ carries only the region_id/field it happened on — never
    the value — so a caller can't leak it just by logging or re-raising."""

    def __init__(self, *, region_id: str, field: str):
        self.region_id = region_id
        self.field = field
        super().__init__(
            f"region '{region_id}'의 '{field}' 값은 coverage_flag=suppressed 라서 "
            "원시값을 노출할 수 없습니다 (06_governance.md §2.3)."
        )


def redact(value, coverage_flag: str | None, *, region_id: str, field: str):
    """The one place a demand-signal-derived value is allowed to cross into
    a response. Returns `value` unchanged unless coverage_flag=='suppressed',
    in which case it returns None and logs that a redaction happened —
    logging the fact, deliberately never the value itself, so the log line
    can't become the leak."""
    if coverage_flag != SUPPRESSED:
        return value
    logger.info(
        "suppressed cell redacted region_id=%s field=%s (value withheld, not logged)",
        region_id,
        field,
    )
    return None


def guard_or_raise(value, coverage_flag: str | None, *, region_id: str, field: str):
    """For call sites that must reject rather than null out — e.g. a
    validation path that would otherwise format the raw value into an error
    message. Raises SuppressedValueError instead, whose message never
    contains `value`."""
    if coverage_flag == SUPPRESSED:
        raise SuppressedValueError(region_id=region_id, field=field)
    return value
