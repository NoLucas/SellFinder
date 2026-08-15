from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class BasemapLevelArtifact(BaseModel):
    level: str
    format: str
    url: str


class BasemapManifestResponse(BaseModel):
    boundary_vintage: str
    levels: list[BasemapLevelArtifact]


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
    boundary_vintage: str
