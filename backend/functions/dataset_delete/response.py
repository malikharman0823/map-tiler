from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class DatasetDeleteData(BaseModel):
    id: UUID
    filename: str
    message: str


class DatasetDeleteResponse(BaseModel):
    success: Literal[True] = True
    data: DatasetDeleteData
