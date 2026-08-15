from fastapi import APIRouter, Depends

from app.schemas import BasemapManifestResponse
from app.security import get_tenant_id
from app.services import basemap_registry

router = APIRouter(tags=["reference"])


@router.get("/v1/basemap/regions/manifest", response_model=BasemapManifestResponse)
def get_basemap_manifest(tenant_id: str = Depends(get_tenant_id)) -> BasemapManifestResponse:
    """Returns pointer URLs to /data-platform's boundary artifacts only —
    never generates or proxies geometry/tiles."""
    return BasemapManifestResponse(**basemap_registry.get_manifest())
