import logging

from fastapi import APIRouter, HTTPException

from app.schemas import ErrorResponse, PredictionRequest, PredictionResponse
from app.services.model_client import get_model_client, utcnow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["predictions"])


@router.post(
    "/api/v1/predictions",
    response_model=PredictionResponse,
    responses={500: {"model": ErrorResponse}},
)
def create_predictions(request: PredictionRequest) -> PredictionResponse:
    client = get_model_client()
    try:
        predictions, model_version = client.predict(request.items)
    except (NotImplementedError, RuntimeError) as exc:
        logger.error("Model backend unavailable: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"code": "model_backend_unavailable", "message": str(exc)},
        ) from exc

    return PredictionResponse(
        predictions=predictions,
        model_version=model_version,
        generated_at=utcnow(),
        is_mock=client.model_backend_name == "mock",
    )
