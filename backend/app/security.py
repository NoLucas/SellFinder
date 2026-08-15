"""Tenant identity extraction.

Real OAuth2/JWT verification is tracked as RECONCILIATION.md #5 step 1 and
not built yet. Until then, the bearer token's value *is* the tenant_id, so
every route already goes through this one dependency and tenant_id is never
read from a query/body param anywhere in the codebase (06_governance.md
§1 — TENANT_ID_NOT_ALLOWED). Swapping in real token verification later only
touches this function.
"""

from fastapi import Header, HTTPException


async def get_tenant_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Bearer 토큰이 필요합니다."},
        )

    tenant_id = authorization.removeprefix("Bearer ").strip()
    if not tenant_id:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Bearer 토큰이 비어 있습니다."},
        )
    return tenant_id
