from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class RasterBounds(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float


class RasterProcessData(BaseModel):
    dataset_id: UUID
    source_crs: str
    target_crs: str
    width: int
    height: int
    bands: int
    bounds: RasterBounds
    output_path: str
    resampling: str
    status: str
    message: str


class RasterProcessResponse(BaseModel):
    success: Literal[True] = True
    data: RasterProcessData
