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
    so the response is cacheable."""
    try:
        manifest = basemap_registry.get_manifest(level, vintage)
    except basemap_registry.UnknownVintageError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "BOUNDARY_VINTAGE_NOT_FOUND", "message": str(exc)},
        ) from exc

    response.headers["Cache-Control"] = "public, max-age=3600"
    return BasemapManifestResponse(**manifest)
