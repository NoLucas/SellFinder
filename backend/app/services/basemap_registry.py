"""Points the console at /data-platform's region boundary artifacts.

/backend never generates or proxies tile/geometry data — it only returns
URLs, signed when the artifact requires it. /data-platform hasn't published
real boundary artifacts yet (data-platform/RECONCILIATION.md #5 step 1 is
still "region model" work-in-progress), so `_ARTIFACTS` below is a
placeholder. Swap it for a real lookup (e.g. a data_source-backed registry)
once A ships boundary storage — the manifest shape and signing contract stay
the same.
"""

import hashlib
import hmac
import time
from dataclasses import dataclass

from app.config import settings

# Single vintage for the whole manifest: all levels are published together.
# Recorded onto prediction_run at creation time (see prediction_store.py) so
# that a run's region_ids can always be traced back to the boundary version
# they were computed against, even after A republishes a newer vintage.
BOUNDARY_VINTAGE = "2026-08"


@dataclass(frozen=True)
class BasemapArtifact:
    level: str
    format: str
    url: str
    requires_signing: bool = False


_ARTIFACTS: list[BasemapArtifact] = [
    BasemapArtifact(
        level="sido",
        format="geojson",
        url="https://data-platform.sellfinder.internal/boundaries/sido/2026-08.geojson",
    ),
    BasemapArtifact(
        level="sigungu",
        format="geojson",
        url="https://data-platform.sellfinder.internal/boundaries/sigungu/2026-08.geojson",
    ),
    BasemapArtifact(
        level="adm_dong",
        format="geojson",
        url="https://data-platform.sellfinder.internal/boundaries/adm_dong/2026-08.geojson",
        requires_signing=True,
    ),
]


def sign_url(url: str) -> str:
    expires_at = int(time.time()) + settings.basemap_signed_url_ttl_seconds
    payload = f"{url}:{expires_at}".encode()
    signature = hmac.new(
        settings.basemap_signing_secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}expires={expires_at}&sig={signature}"


def get_manifest() -> dict:
    return {
        "boundary_vintage": BOUNDARY_VINTAGE,
        "levels": [
            {
                "level": artifact.level,
                "format": artifact.format,
                "url": sign_url(artifact.url) if artifact.requires_signing else artifact.url,
            }
            for artifact in _ARTIFACTS
        ],
    }
