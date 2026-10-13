from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IconPointData(BaseModel):
    id: UUID
    dataset_id: UUID
    icon_key: str | None = None
    latitude: float
    longitude: float
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IconPointResponse(BaseModel):
    data: IconPointData


class IconPointListData(BaseModel):
    points: list[IconPointData]
    count: int


class IconPointListResponse(BaseModel):
    data: IconPointListData
