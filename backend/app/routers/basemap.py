from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.schemas import BasemapManifestResponse
from app.security import get_tenant_id
from app.services import basemap_registry

router = APIRouter(tags=["reference"])


@router.get("/v1/basemap/regions/manifest", response_model=BasemapManifestResponse)
def get_basemap_manifest(
    response: Response,
    level: str = Query(pattern="^(sido|sigungu|adm_dong)$"),
    vintage: str | None = Query(
        default=None,
        description="생략 시 최신. 저장된 예측을 다시 열 때는 prediction_run.boundary_vintage를 넘겨야 한다.",
    ),
    tenant_id: str = Depends(get_tenant_id),
) -> BasemapManifestResponse:
    """Points to /data-platform's static .pmtiles artifact only — never
    generates or proxies tile content. Authenticated but tenant-independent,
    so the manifest itself is safe to cache — EXCEPT when tile_url carries a
    per-request signature (adm_dong): a shared/CDN cache serving that body to
    a second, unauthenticated requester leaks the signed URL (VF-006,
    06_governance.md §1.5 / ADR-003 §4). Signed responses get
    "private" so only the requester's own client caches them."""
    try:
        manifest = basemap_registry.get_manifest(level, vintage)
    except basemap_registry.NoBoundaryArtifactsError as exc:
        # D-13 / ADR-002 결정 3: A 가 이 level 을 아직 발행하지 않았다. 빈 배열을
        # 돌려주면 "빈티지가 없다"는 거짓 정보가 된다 — 503 + 사유로 명확히 밝힌다.
        raise HTTPException(
            status_code=503,
            detail={
                "code": "BOUNDARY_MANIFEST_NOT_PUBLISHED",
                "message": (
                    f"data-platform 이 아직 level '{level}' 을 발행하지 않았습니다. "
                    f"data-platform/output/manifest/regions-{level}-*.json 이 없습니다."
                ),
            },
        ) from exc
    except basemap_registry.UnknownVintageError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "BOUNDARY_VINTAGE_NOT_FOUND", "message": str(exc)},
        ) from exc

    is_signed = "sig=" in manifest["tile_url"]
    response.headers["Cache-Control"] = (
        "private, max-age=3600" if is_signed else "public, max-age=3600"
    )
    return BasemapManifestResponse(**manifest)
