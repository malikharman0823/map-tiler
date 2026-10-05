from uuid import UUID

from pydantic import BaseModel


class RasterProcessOptionsRequest(BaseModel):
    target_crs: str = "EPSG:3857"
    resampling: str = "bilinear"


class RasterProcessRequest(RasterProcessOptionsRequest):
    dataset_id: UUID
