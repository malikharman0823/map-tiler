from uuid import UUID

from pydantic import BaseModel


class TileGenerationOptionsRequest(BaseModel):
    min_zoom: int = 0
    max_zoom: int = 18


class TileGenerationRequest(TileGenerationOptionsRequest):
    dataset_id: UUID
