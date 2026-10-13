from uuid import UUID
from pydantic import BaseModel, Field


class DatasetIconPointsRequest(BaseModel):
    dataset_id: UUID


class IconPointRequest(BaseModel):
    icon_point_id: UUID


class CreateIconPointRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    icon_key: str | None = None
    description: str | None = Field(default=None, max_length=500)


class UpdateIconPointRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    icon_key: str | None = None
    description: str | None = Field(default=None, max_length=500)
