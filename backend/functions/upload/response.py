from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class UploadData(BaseModel):
    id: UUID
    filename: str
    file_size: int
    content_type: str | None
    file_hash: str
    storage_path: str
    metadata: dict[str, Any]
    existing: bool
    message: str


class UploadResponse(BaseModel):
    success: Literal[True] = True
    data: UploadData
