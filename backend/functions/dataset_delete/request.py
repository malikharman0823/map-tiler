from uuid import UUID

from pydantic import BaseModel


class DatasetDeleteRequest(BaseModel):
    dataset_id: UUID
