"""Tenant identity + auth claims extraction — single verification point (ADR-003).

verify_token(raw) -> TokenClaims is the one place Authorization headers get
parsed. Application code must never read tokens anywhere else, so swapping
in a real IdP later only touches this function (ADR-003 §3).

Today there is no real IdP: verify_token decodes tokens minted by this same
service's /v1/dev/token endpoint (issue_dev_token below), and falls back to
treating the raw bearer value as a literal tenant_id for the placeholder
scheme predating ADR-003 that existing fixtures/tests still use.

06_governance.md §1.1 requires tenant_id be *rejected* (400
TENANT_ID_NOT_ALLOWED), not silently ignored, if it arrives via query
param or header — it must only ever come from the verified token.
"""

import base64
import json
import logging
import time
from dataclasses import dataclass, field

from fastapi import Header, HTTPException, Request

_FORBIDDEN_TENANT_QUERY_KEYS = {"tenant_id", "tenantId"}
_FORBIDDEN_TENANT_HEADER_NAMES = {"x-tenant-id", "tenant-id"}

audit_logger = logging.getLogger("sellfinder.audit")


@dataclass(frozen=True)
class TokenClaims:
    sub: str
    tenant_id: str
    role: str
    region_scope: list[str] = field(default_factory=list)
    exp: int | None = None


def issue_dev_token(tenant_id: str, role: str = "analyst", region_scope: list[str] | None = None) -> str:
    """Mints a placeholder token for the dev-only /v1/dev/token endpoint
    (ADR-003 "개발 중 임시 조치"). Not a real JWT — unsigned, base64 JSON.
    Never register the endpoint that calls this outside development."""
    claims = {
        "sub": f"usr_dev_{tenant_id}",
        "tenant_id": tenant_id,
        "role": role,
        "region_scope": region_scope or [],
        "exp": int(time.time()) + 3600,
    }
    return base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()


def verify_token(raw: str) -> TokenClaims:
    """Single verification point (ADR-003 §3). Every route reaches tenant_id
    only through this function's return value, never by re-parsing the
    Authorization header itself."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
        if not isinstance(payload, dict) or "tenant_id" not in payload:
            raise ValueError("not a claims payload")
        return TokenClaims(
            sub=payload.get("sub", f"usr_{payload['tenant_id']}"),
            tenant_id=payload["tenant_id"],
            role=payload.get("role", "analyst"),
            region_scope=payload.get("region_scope") or [],
            exp=payload.get("exp"),
        )
    except Exception:
        # Backward-compat placeholder scheme: bearer value itself is the
        # tenant_id. Used by fixtures/tests predating ADR-003.
        return TokenClaims(sub=f"usr_{raw}", tenant_id=raw, role="analyst", region_scope=[])


def _reject_tenant_id_injection(request: Request) -> None:
    offending_query = _FORBIDDEN_TENANT_QUERY_KEYS & set(request.query_params.keys())
    offending_header = _FORBIDDEN_TENANT_HEADER_NAMES & {h.lower() for h in request.headers.keys()}
    if offending_query or offending_header:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "TENANT_ID_NOT_ALLOWED",
                "message": "tenant_id 는 요청 파라미터로 전달할 수 없습니다. 액세스 토큰에서 파생됩니다.",
            },
        )


async def get_tenant_id(request: Request, authorization: str | None = Header(default=None)) -> str:
    _reject_tenant_id_injection(request)

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Bearer 토큰이 필요합니다."},
        )

    raw = authorization.removeprefix("Bearer ").strip()
    if not raw:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Bearer 토큰이 비어 있습니다."},
        )
    tenant_id = verify_token(raw).tenant_id

    # 06_governance.md §4 감사(audit): "누가 언제 어떤 예측을 어떤 파라미터로
    # 실행했는가". This is the one place identity is ever resolved (ADR-003
    # §3), so it's the one place that can honestly log "who" without
    # re-parsing the token elsewhere. request_id ties this line to the
    # per-request line app.main's middleware already logs.
    audit_logger.info(
        "actor tenant_id=%s method=%s path=%s request_id=%s",
        tenant_id,
        request.method,
        request.url.path,
        getattr(request.state, "request_id", None),
    )
    return tenant_id
