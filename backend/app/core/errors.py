from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        status_code: int = 400,
        message: str | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.status_code = status_code
        self.message = message or code
        self.details = details


def _envelope(code: str, message: str, details: Any, request_id: str) -> dict:
    return {"error": {"code": code, "message": message, "details": details, "request_id": request_id}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        request_id = uuid.uuid4().hex
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details, request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = uuid.uuid4().hex
        return JSONResponse(
            status_code=422,
            content=_envelope("validation_error", "validation error", exc.errors(), request_id),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = uuid.uuid4().hex
        return JSONResponse(
            status_code=500,
            content=_envelope("internal_error", "internal server error", None, request_id),
        )
