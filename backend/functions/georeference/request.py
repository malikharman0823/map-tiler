from uuid import UUID

from pydantic import BaseModel


class GeoreferenceOptionsRequest(BaseModel):
    transformation: str = "affine"
    output_format: str = "tif"


class GeoreferenceRequest(GeoreferenceOptionsRequest):
    dataset_id: UUID
