from uuid import UUID

from pydantic import BaseModel


class TileReadRequest(BaseModel):
    dataset_id: UUID
    z: int
    x: int
    y: int
