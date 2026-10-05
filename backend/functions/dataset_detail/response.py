from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class DatasetDetailData(BaseModel):
    id: UUID
    filename: str
    file_size: int
    content_type: str | None
    file_hash: str
    storage_path: str
    metadata: dict[str, Any]
    georeferenced_path: str | None
    georeference_status: str
    processed_path: str | None
    process_status: str
    tile_path: str | None
    tile_min_zoom: int | None
    tile_max_zoom: int | None
    tile_status: str
    created_at: datetime


class DatasetDetailResponse(BaseModel):
    success: Literal[True] = True
    data: DatasetDetailData
