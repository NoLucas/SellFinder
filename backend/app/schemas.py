from pydantic import BaseModel


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
