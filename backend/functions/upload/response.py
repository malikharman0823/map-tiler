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
    is_georeferenced: bool = False
    georeference_status: str = "not_started"
    imported_datasets: list[dict[str, Any]] | None = None


class UploadResponse(BaseModel):
    success: Literal[True] = True
    data: UploadData
