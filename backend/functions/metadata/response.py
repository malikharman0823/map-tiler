from typing import Any, Literal

from pydantic import BaseModel


class MetadataData(BaseModel):
    format: str
    category: str
    metadata: dict[str, Any]


class MetadataResponse(BaseModel):
    success: Literal[True] = True
    data: MetadataData
