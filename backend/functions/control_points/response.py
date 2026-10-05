from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ControlPointData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    image_x: float
    image_y: float
    longitude: float
    latitude: float
    created_at: datetime
    updated_at: datetime


class ControlPointResponse(BaseModel):
    success: Literal[True] = True
    data: ControlPointData


class ControlPointListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    image_x: float
    image_y: float
    longitude: float
    latitude: float


class ControlPointListData(BaseModel):
    points: list[ControlPointListItem]
    count: int


class ControlPointListResponse(BaseModel):
    success: Literal[True] = True
    data: ControlPointListData
