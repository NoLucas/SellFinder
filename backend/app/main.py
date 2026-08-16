import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import basemap, health, predictions

logger = logging.getLogger("sellfinder")


def create_app() -> FastAPI:
    application = FastAPI(
        title="SellFinder API",
        version="0.2.0",
        description="Implements /shared/contracts/04_api_contract.yaml",
    )

    application.include_router(health.router)
    application.include_router(basemap.router)
    application.include_router(predictions.router)

    # ADR-003 "개발 중 임시 조치": only registered in development. Not merely
    # 404ing at runtime — the route must not exist in a production build
    # (DECISIONS.md D-17, S1 if it does).
    if settings.env == "development":
        from app.routers import dev_auth

        application.include_router(dev_auth.router)

    @application.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            error = detail
        else:
            error = {"code": "http_error", "message": str(detail)}
        return JSONResponse(status_code=exc.status_code, content={"error": error})

    @application.exception_handler(RequestValidationError)
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

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Defense in depth for 06_governance.md §2.3 / VF-010's "error
        message" leg: never echo str(exc) to the client. A
        SuppressedValueError's own message is already safe by construction
        (app.services.privacy.SuppressedValueError), but this net catches
        any *other* exception type whose message happens to interpolate a
        value that must not reach the client — the guarantee shouldn't
        depend on every exception type remembering to redact itself.
        exc_info is logged (server-side only) for debugging."""
        logger.exception("unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "일시적인 오류가 발생했습니다."}},
        )

    return application


app = create_app()
