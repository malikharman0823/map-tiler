from typing import Literal

from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ApplicationError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: str,
        field: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.field = field
        super().__init__(message)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: str | None = None
    field: str | None = None


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    error: ErrorDetail


def make_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: str | None = None,
    field: str | None = None,
) -> JSONResponse:
    response = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details,
            field=field,
        )
    )
    return JSONResponse(status_code=status_code, content=response.model_dump())
