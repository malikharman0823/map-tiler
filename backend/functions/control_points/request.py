from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field


ImageCoordinate = Annotated[float, Field(ge=0)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Latitude = Annotated[float, Field(ge=-90, le=90)]


class CreateControlPointRequest(BaseModel):
    dataset_id: UUID
    image_x: ImageCoordinate
    image_y: ImageCoordinate
    longitude: Longitude
    latitude: Latitude


class UpdateControlPointRequest(BaseModel):
    image_x: ImageCoordinate
    image_y: ImageCoordinate
    longitude: Longitude
    latitude: Latitude


class DatasetControlPointsRequest(BaseModel):
    dataset_id: UUID


class ControlPointRequest(BaseModel):
    control_point_id: UUID
