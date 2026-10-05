from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class GeoreferenceData(BaseModel):
    dataset_id: UUID
    transformation: str
    control_point_count: int
    crs: str
    output_path: str
    status: str
    message: str


class GeoreferenceResponse(BaseModel):
    success: Literal[True] = True
    data: GeoreferenceData
