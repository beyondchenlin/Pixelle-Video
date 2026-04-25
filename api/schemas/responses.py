from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.responses import JSONResponse


class APIErrorPayload(BaseModel):
    code: str
    details: Any = None


class APIErrorResponse(BaseModel):
    success: bool = False
    message: str
    error: APIErrorPayload


class APIEnvelope(BaseModel):
    success: bool = True
    message: str = "Success"
    data: Any = None


def success_envelope(data: Any = None, message: str = "Success") -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "success": True,
        "message": message,
    }
    if data is not None:
        envelope["data"] = data
    return envelope


def error_envelope(message: str, code: str, details: Any = None) -> dict[str, Any]:
    return APIErrorResponse(
        message=message,
        error=APIErrorPayload(code=code, details=details),
    ).model_dump()


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        details = None if isinstance(exc.detail, str) else exc.detail
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(
                message=message,
                code=f"http_{exc.status_code}",
                details=details,
            ),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                message="validation error",
                code="validation_error",
                details=jsonable_encoder(exc.errors()),
            ),
        )
