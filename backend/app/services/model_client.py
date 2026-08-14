"""Abstraction over the prediction backend.

`LiveModelClient` calls into /model's src/predict.py in-process. It requires:
  1. /model's runtime deps installed (see requirements-live.txt)
  2. a trained artifact at model/artifacts/sell_finder_model.joblib
     (produced by `python -m src.train` inside /model)

Until both exist, keep `settings.use_live_model` False so `MockModelClient`
serves requests instead.
"""

import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.config import settings
from app.schemas import ItemPrediction, PredictionItem

MODEL_DIR = Path(__file__).resolve().parents[3] / "model"


@lru_cache(maxsize=1)
def _load_live_model():
    """Load the trained SellFinderModel once per process."""
    if str(MODEL_DIR) not in sys.path:
        sys.path.insert(0, str(MODEL_DIR))

    try:
        from src.model import SellFinderModel
        from src.train import DEFAULT_MODEL_PATH
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Live /model integration requires its runtime dependencies "
            "(pandas, scikit-learn, numpy, joblib). Install "
            "backend/requirements-live.txt, or set "
            "SELLFINDER_USE_LIVE_MODEL=false to use the mock predictor."
        ) from exc

    if not DEFAULT_MODEL_PATH.exists():
        raise RuntimeError(
            f"No trained model artifact at {DEFAULT_MODEL_PATH}. Run "
            "`python -m src.train` inside /model first, or set "
            "SELLFINDER_USE_LIVE_MODEL=false to use the mock predictor."
        )

    return SellFinderModel.load(DEFAULT_MODEL_PATH)


class ModelClient(ABC):
    model_backend_name: str

    @abstractmethod
    def predict(self, items: list[PredictionItem]) -> tuple[list[ItemPrediction], str]:
        """Return (predictions, model_version)."""
        raise NotImplementedError


class MockModelClient(ModelClient):
    """Deterministic, dependency-free stand-in for the real /model logic.

    Values are derived from simple heuristics on the input so responses are
    stable and reproducible for frontend/integration testing, without
    claiming any real predictive accuracy.
    """

    model_backend_name = "mock"

    _CONDITION_SCORE = {
        "new": 0.9,
        "like_new": 0.8,
        "good": 0.65,
        "fair": 0.45,
        "poor": 0.25,
    }

    def predict(self, items: list[PredictionItem]) -> tuple[list[ItemPrediction], str]:
        predictions = [self._predict_one(item) for item in items]
        return predictions, settings.model_version_mock

    def _predict_one(self, item: PredictionItem) -> ItemPrediction:
        condition_score = self._CONDITION_SCORE[item.condition.value]
        days_listed = item.days_listed or 0

        # Longer an item sits, the lower its odds without a price change.
        staleness_penalty = min(days_listed / 100.0, 0.4)
        sell_probability = max(0.05, min(0.95, condition_score - staleness_penalty))

        estimated_days_to_sell = round((1 - sell_probability) * 30 + 1, 1)
        recommended_price = round(item.price * (0.85 + 0.15 * condition_score), 2)
        confidence = 0.5  # mock predictor never claims high confidence

        return ItemPrediction(
            item_id=item.item_id,
            sell_probability=round(sell_probability, 4),
            estimated_days_to_sell=estimated_days_to_sell,
            recommended_price=recommended_price,
            confidence=confidence,
        )


class LiveModelClient(ModelClient):
    """Calls /model's SellFinderModel + run_prediction in-process.

    /model's package root is `model/src` (no top-level `model/__init__.py`),
    so it's imported by putting `model/` on sys.path and importing `src.*` —
    matching how /model's own scripts (e.g. `python -m src.predict`) import
    themselves. This is an in-process call, not a network boundary.
    """

    model_backend_name = "live"

    def predict(self, items: list[PredictionItem]) -> tuple[list[ItemPrediction], str]:
        model = _load_live_model()

        from src.predict import run_prediction

        request = {"items": [item.model_dump(mode="json") for item in items]}
        response = run_prediction(model, request)

        predictions = [ItemPrediction(**p) for p in response["predictions"]]
        return predictions, response["model_version"]


def get_model_client() -> ModelClient:
    return LiveModelClient() if settings.use_live_model else MockModelClient()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
