from typing import Literal

from pydantic import BaseModel


class ValidateFileData(BaseModel):
    valid: Literal[True] = True
    filename: str
    extension: str
    format: str
    category: str
    file_size: int
    content_type: str | None
    message: str


class ValidateFileResponse(BaseModel):
    success: Literal[True] = True
    data: ValidateFileData
