"""In-process bridge into /intelligence's predict_batch (DISPATCH-2 C-2,
BRIEF-C 6). intelligence/README.md is the single source of truth this
module follows - every choice below cites the exact section that justifies
it, per D-10 (don't read another agent's code as if it were the contract,
but README.md *is* B's explicitly-published entry-point contract, not
implementation detail).

`intelligence/` has no top-level `__init__.py` - `scoring` and `synthetic`
are only importable once `intelligence/` itself is on sys.path (same
pattern intelligence's own tests and verification/fixtures/vf_*.py use).
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

_INTELLIGENCE_ROOT = Path(__file__).resolve().parents[3] / "intelligence"
if str(_INTELLIGENCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_INTELLIGENCE_ROOT))

from scoring import model  # noqa: E402
from scoring.feature_store import FeatureStore, SyntheticFeatureStore  # noqa: E402
from synthetic import generate  # noqa: E402

# README §2-1: SyntheticFeatureStore is "지금 당장 통합·데모에 쓸 수 있는
# 유일한 완전한 스토어" - RegionFeatureFileStore (§2-2) exists but its
# get_demand() still raises NotImplementedError (A hasn't published
# demand_signal yet). README §2: "predict_batch 호출마다 새로 하지 마라...
# 프로세스 시작 시 한 번 만들어 재사용" - built once at import time.
_DATASET = generate.generate_all(seed=42, start_period="2025-01", end_period="2026-06")
_STORE: FeatureStore = SyntheticFeatureStore.from_dataset(_DATASET)

# region_feature rows in this synthetic dataset only exist at adm_dong
# granularity (verified directly: sigungu/sido region_ids all resolve to
# None features -> every factor stays neutral (1.0), README §4-3's
# "지역이 저장소에 없으면 중립" case). Not a code bug to paper over - it's
# the real current depth of the synthetic data. region_ids_for_level below
# reports this honestly rather than aggregating fake sigungu/sido features.
_REGION_NAME_BY_ID: dict[str, str] = {r["region_id"]: r["name"] for r in _DATASET["regions"]}


def region_ids_for_level(region_level: str, limit: int = 5) -> list[str]:
    """region_ids that actually exist in this dataset for `region_level`.
    Scoring an id the store doesn't recognize isn't an error (README §4-3),
    but it's a meaningless, undifferentiated result - callers should use
    this instead of inventing their own candidate list."""
    matches = [r["region_id"] for r in _DATASET["regions"] if r["level"] == region_level]
    return matches[:limit]


def region_name_for(region_id: str) -> str | None:
    return _REGION_NAME_BY_ID.get(region_id)

# Backend has no product catalog yet (no POST /products, no stored Product
# rows - RECONCILIATION.md's open question on this predates DISPATCH-2), so
# PredictionRequest.product_ids are opaque strings backend cannot resolve
# to a real taxonomy_node_id/channel. TX-FOOD-BEV-COFFEE-RTD / "cvs" is not
# an invented pair - it's the exact example 04_api_contract.yaml itself
# uses throughout (PredictionDetail's RTD커피/편의점 worked example,
# 02_taxonomy.json's default_channels for that node includes "cvs"). Used
# here only because nothing in backend can pick a better one yet - see
# backend/RECONCILIATION.md for the open question this leaves.
PLACEHOLDER_TAXONOMY_NODE_ID = "TX-FOOD-BEV-COFFEE-RTD"
PLACEHOLDER_CHANNEL = "cvs"


class PredictionInputError(ValueError):
    """README §4-2: predict_batch raises KeyError/IndexError/
    ZeroDivisionError for a handful of bad inputs and expects the caller to
    guard against them. Wrapped here so nothing downstream has to know
    predict_batch's raw exception types."""


def run_prediction(
    region_ids: list[str],
    data_tier: str,
    channel: str | None = None,
    horizon_months: int = 6,
) -> list[model.PredictionResult]:
    """README §6's reference integration. `period`/`as_of` are derived from
    the current date, not invented - README §4-3 requires
    as_of == f"{period}-01" exactly (period's start date) to keep the
    leakage guard meaningful."""
    now = datetime.datetime.now(datetime.timezone.utc)
    period = now.strftime("%Y-%m")
    as_of = f"{period}-01"

    try:
        return model.predict_batch(
            region_ids=region_ids,
            taxonomy_node_id=PLACEHOLDER_TAXONOMY_NODE_ID,
            channel=channel or PLACEHOLDER_CHANNEL,
            period=period,
            as_of=as_of,
            data_tier=data_tier,
            store=_STORE,
            horizon_months=horizon_months,
        )
    except (KeyError, IndexError, ZeroDivisionError) as exc:
        raise PredictionInputError(f"invalid prediction request: {exc}") from exc
