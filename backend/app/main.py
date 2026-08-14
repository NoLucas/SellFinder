from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routers import health, predictions

app = FastAPI(
    title="SellFinder Prediction API",
    version="1.0.0",
    description="Implements /shared/contracts/prediction_api.json",
)

app.include_router(health.router)
app.include_router(predictions.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        error = detail
    else:
        error = {"code": "http_error", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": error})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": str(exc.errors()),
            }
        },
    )
