from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class GeoreferenceData(BaseModel):
    dataset_id: UUID
    georeference_config_id: UUID | None
    status: str
    transformation: str
    transformation_parameters: dict[str, Any]
    source_coordinate_system: dict[str, Any]
    control_point_count: int
    source_crs: str | None
    target_crs: str
    source_width: int
    source_height: int
    output_format: str
    output_path: str
    reusable: bool = False
    reuse_warning: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    message: str


class GeoreferenceResponse(BaseModel):
    success: Literal[True] = True
    data: GeoreferenceData


class GeoreferenceLookupData(BaseModel):
    configuration: GeoreferenceData | None


class GeoreferenceLookupResponse(BaseModel):
    success: Literal[True] = True
    data: GeoreferenceLookupData
