from uuid import UUID

from pydantic import BaseModel


class DatasetDetailRequest(BaseModel):
    dataset_id: UUID
