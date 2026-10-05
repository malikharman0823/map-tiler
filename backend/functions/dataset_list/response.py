from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class DatasetListItem(BaseModel):
    id: UUID
    filename: str
    file_size: int
    content_type: str | None
    file_hash: str
    metadata: dict[str, Any]
    georeference_status: str
    process_status: str
    tile_status: str
    created_at: datetime


class DatasetListData(BaseModel):
    datasets: list[DatasetListItem]
    count: int


class DatasetListResponse(BaseModel):
    success: Literal[True] = True
    data: DatasetListData
