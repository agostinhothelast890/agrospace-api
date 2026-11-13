import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("agrospace")

# Short machine-readable names, so the frontend doesn't depend on the text.
ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    422: "validation_error",
    429: "too_many_requests",
    500: "server_error",
    502: "bad_gateway",
    503: "service_unavailable",
}


def error_response(
    status_code: int,
    detail: str,
    errors: list | None = None,
    headers: dict | None = None,
) -> JSONResponse:
    body = {"detail": detail, "code": ERROR_CODES.get(status_code, "error")}
    if errors:
        body["errors"] = errors
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        # Covers every HTTPException we raise (401, 404, 502, 503...).
        return error_response(exc.status_code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Wrong or missing fields: one clear message per field.
        errors = []
        for err in exc.errors():
            field = ".".join(
                str(part) for part in err["loc"] if part not in ("body", "query", "path")
            )
            errors.append({"field": field, "message": err["msg"]})
        return error_response(422, "Invalid data sent", errors)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        # Anything we did not expect: log it, but never show internals to the user.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(500, "Something went wrong on the server")
