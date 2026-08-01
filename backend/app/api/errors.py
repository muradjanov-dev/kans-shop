from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import KansShopError
from app.core.logging import get_logger

log = get_logger(__name__)


def _error_response(
    status_code: int, code: str, message: str, details: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(KansShopError)
    async def handle_domain_error(request: Request, exc: KansShopError) -> JSONResponse:
        return _error_response(exc.http_status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            422, "VALIDATION_ERROR", "Invalid request data", {"errors": exc.errors()}
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_api_error", path=str(request.url), error=str(exc), exc_info=True)
        return _error_response(
            500, "INTERNAL_ERROR", "Xatolik yuz berdi, qaytadan urinib ko'ring."
        )
