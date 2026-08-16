from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class BasemapManifestResponse(BaseModel):
    level: str
    boundary_vintage: str
    tile_url: str
    source_layer: str
    feature_id_property: str
    minzoom: int
    maxzoom: int
    attribution: str
    available_vintages: list[str]


class ExpectedRevenue(BaseModel):
    p10: int
    p50: int
    p90: int


class RegionScoreConfidence(BaseModel):
    level: str
    data_coverage: float


class RegionScoreItem(BaseModel):
    region_id: str
    region_name: str
    rank: int
    opportunity_score: float
    score_percentile: float
    expected_revenue_krw: ExpectedRevenue | None
    confidence: RegionScoreConfidence


class RegionScoresResponse(BaseModel):
    data: list[RegionScoreItem]
    next_cursor: str | None


class RegionFilter(BaseModel):
    sido: list[str] = []
    region_ids: list[str] = []


class PredictionRequest(BaseModel):
    """04_api_contract.yaml PredictionRequest. region_filter/scenario_id/
    exclude_own_store_regions are accepted (contract-valid) but not yet
    applied by the job body — same "accepted but not applied" note already
    on /scores' product_id/channel (routers/predictions.py) until DISPATCH-2
    C-2 wires in /intelligence's real predict_batch."""

    product_ids: list[str] = Field(min_length=1, max_length=50)
    objective: str = Field(pattern="^(store_expansion|distribution_push|ad_targeting)$")
    region_level: str = Field(pattern="^(sido|sigungu|adm_dong|custom_catchment)$")
    region_filter: RegionFilter | None = None
    channels: list[str] = []
    horizon_months: int = Field(default=6, ge=1, le=12)
    scenario_id: str | None = None
    exclude_own_store_regions: bool = False


class PredictionCreateResponse(BaseModel):
    # model_version isn't pydantic's namespaced "model_" convention - same
    # opt-out app.config.Settings already uses for basemap_signing_secret etc.
    model_config = ConfigDict(protected_namespaces=())

    run_id: str
    status: str
    estimated_seconds: int
    # No real value to report until DISPATCH-2 C-2 wires in /intelligence's
    # predict_batch — the job body is still the demo placeholder, so these
    # stay null rather than borrowing the contract example's illustrative
    # "factor-v1.3.0" / a made-up as_of date (that would be inventing a
    # value, exactly what DISPATCH-2 §9 warns against).
    model_version: str | None = None
    feature_as_of: str | None = None
    data_tier: str
