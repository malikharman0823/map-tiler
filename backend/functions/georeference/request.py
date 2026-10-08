from uuid import UUID

from typing import Literal

from pydantic import BaseModel


class GeoreferenceOptionsRequest(BaseModel):
    action: Literal["calculate", "save"] = "calculate"
    transformation: str = "auto"
    output_format: str = "tif"
    target_crs: str = "EPSG:4326"


class GeoreferenceRequest(GeoreferenceOptionsRequest):
    dataset_id: UUID
