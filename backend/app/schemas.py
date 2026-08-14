from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ItemCondition(str, Enum):
    new = "new"
    like_new = "like_new"
    good = "good"
    fair = "fair"
    poor = "poor"


class PredictionItem(BaseModel):
    item_id: str
    category: str
    price: float = Field(ge=0)
    condition: ItemCondition
    brand: Optional[str] = None
    days_listed: Optional[int] = Field(default=None, ge=0)
    attributes: Optional[dict[str, Any]] = None


class PredictionRequest(BaseModel):
    items: list[PredictionItem] = Field(min_length=1, max_length=100)


class ItemPrediction(BaseModel):
    item_id: str
    sell_probability: float = Field(ge=0, le=1)
    estimated_days_to_sell: float = Field(ge=0)
    recommended_price: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class PredictionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    predictions: list[ItemPrediction]
    model_version: str
    generated_at: datetime
    is_mock: bool


class HealthResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str = "ok"
    model_backend: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
