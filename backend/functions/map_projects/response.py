from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

class MapProjectResponse(BaseModel):
    id: UUID
    name: str
    dataset_id: UUID | None
    configuration: dict
    created_at: datetime
    updated_at: datetime
