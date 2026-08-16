import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import basemap, health, predictions

logger = logging.getLogger("sellfinder")
audit_logger = logging.getLogger("sellfinder.audit")


def _request_id(request: Request) -> str:
    """Every error envelope needs this (04_api_contract.yaml components.
    responses.BadRequest / schemas.Error: required: [code, message,
    request_id]). Set by the request_id_middleware below on request.state
    before any route or exception handler runs, so it's always present by
    the time an error is built - falls back to minting a fresh one only if
    something bypassed the middleware (defensive, shouldn't happen)."""
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def create_app() -> FastAPI:
    application = FastAPI(
        title="SellFinder API",
        version="0.2.0",
        description="Implements /shared/contracts/04_api_contract.yaml",
    )

    @application.middleware("http")
    async def request_id_and_audit_middleware(request: Request, call_next):
        """06_governance.md §4 감사(audit): who/when/what — DISPATCH-2 C-4.
        Assigns request_id before anything else runs (exception handlers
        and app.security.get_tenant_id's actor-level audit line both read
        request.state.request_id), and logs one request-level audit line
        per call regardless of outcome (status/duration/path) — the
        who=tenant_id half of "who/when/what" is logged separately, inside
        get_tenant_id, the one place identity is ever resolved (ADR-003
        §3's single verification point - this middleware deliberately does
        not re-parse Authorization itself)."""
        request.state.request_id = uuid.uuid4().hex
        started = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        response.headers["X-Request-Id"] = request.state.request_id
        audit_logger.info(
            "request method=%s path=%s status=%s duration_ms=%s request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request.state.request_id,
        )
        return response

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
            error = {**detail, "request_id": _request_id(request)}
        else:
            error = {"code": "http_error", "message": str(detail), "request_id": _request_id(request)}
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
                    "request_id": _request_id(request),
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
            content={
                "error": {
                    "code": "internal_error",
                    "message": "일시적인 오류가 발생했습니다.",
                    "request_id": _request_id(request),
                }
            },
        )

    return application


app = create_app()
