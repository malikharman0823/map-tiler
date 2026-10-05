from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class TileGenerationData(BaseModel):
    dataset_id: UUID
    min_zoom: int
    max_zoom: int
    tile_size: int
    format: str
    scheme: str
    tile_path: str
    tile_url_template: str
    status: str
    message: str


class TileGenerationResponse(BaseModel):
    success: Literal[True] = True
    data: TileGenerationData
