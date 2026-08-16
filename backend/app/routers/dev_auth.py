"""Dev-only token issuance (ADR-003 "개발 중 임시 조치").

Registered by app.main.create_app() only when settings.env == "development".
If this router is reachable in a production build, that is an S1 defect
(DECISIONS.md D-17) — the registration gate is what verification checks,
not the handler logic.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.security import issue_dev_token

router = APIRouter(tags=["dev"])


class DevTokenRequest(BaseModel):
    tenant_id: str
    role: str = "analyst"
    region_scope: list[str] = []


class DevTokenResponse(BaseModel):
    access_token: str


@router.post("/v1/dev/token", response_model=DevTokenResponse)
def issue_token(body: DevTokenRequest) -> DevTokenResponse:
    return DevTokenResponse(
        access_token=issue_dev_token(body.tenant_id, body.role, body.region_scope)
    )
